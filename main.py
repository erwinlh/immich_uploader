#!/usr/bin/env python3
"""
Script principal para coordinar el proceso de subida de fotos/videos a Immich
VERSIÓN MEJORADA con logging y mejor arquitectura
"""
import sys
import os
import argparse
from config import LOGO_FILE
from db_manager import DatabaseManager
from logger import logger
from scan_files import scan_and_populate_db
from upload_files import upload_pending_files
from sync_upload import sync_and_upload

# Variable global para número de hilos
THREADS = 1


def show_menu(folder_filter=None):
    """Mostrar menú de opciones"""
    # Leer y mostrar el logo ASCII
    try:
        if os.path.exists(LOGO_FILE):
            with open(LOGO_FILE, 'r', encoding='utf-8') as logo_file:
                logo = logo_file.read()
                print(logo)
    except Exception as e:
        logger.debug(f"No se pudo cargar el logo: {str(e)}")

    print("\n=== Gestor de Subida a Immich ===")
    print(f"⚙️  Hilos configurados: {THREADS}")
    if folder_filter:
        print(f"📁 Carpeta filtrada: {folder_filter}")
    print("1. Escanear directorios y poblar base de datos")
    print("2. Subir archivos pendientes a Immich")
    print("3. Mostrar resumen de estado")
    print("4. Escanear y subir en un solo proceso (Recomendado)")
    print("5. Verificar conexión con Immich (Diagnóstico)")
    print("6. Salir")
    choice = input("\nSeleccione una opción (1-6): ")
    return choice


def show_summary():
    """Mostrar resumen de estado de la base de datos"""
    try:
        db = DatabaseManager()
        stats = db.get_stats()

        print("\n" + "=" * 60)
        print("RESUMEN DE ESTADO")
        print("=" * 60)

        # Mostrar estadísticas por estado
        for status in ['pending', 'success', 'duplicate', 'error']:
            count = stats.get(status, 0)
            if status == 'pending':
                print(f"⏳ Pendientes:           {count}")
            elif status == 'success':
                print(f"✅ Exitosos:             {count}")
            elif status == 'duplicate':
                print(f"⚠️  Duplicados:           {count}")
            elif status == 'error':
                print(f"❌ Errores:              {count}")

        print("-" * 60)
        print(f"📊 Total de archivos:   {stats.get('total', 0)}")
        print(f"🔍 Con metadatos:       {stats.get('with_metadata', 0)}")
        print(f"📤 Pendientes subida:   {stats.get('pending_upload', 0)}")
        print("=" * 60 + "\n")

        db.close()

    except Exception as e:
        print(f"❌ Error obteniendo resumen: {str(e)}")
        logger.error(f"Error en show_summary: {str(e)}")


def check_endpoints():
    """Verificar conexión con Immich y mostrar diagnóstico detallado"""
    from config import IMMICH_URL, IMMICH_API_KEY
    from colorama import Fore, Style
    import requests

    print("\n" + "=" * 60)
    print("🔍 DIAGNÓSTICO DE CONEXIÓN CON IMMICH")
    print("=" * 60)

    # Verificar configuración
    print(f"\n📝 Configuración:")
    print(f"   URL: {IMMICH_URL}")
    print(f"   API Key: {'*' * (len(IMMICH_API_KEY) - 4) + IMMICH_API_KEY[-4:] if IMMICH_API_KEY else 'NO CONFIGURADA'}")

    if not IMMICH_URL or not IMMICH_API_KEY:
        print(f"\n{Fore.RED}❌ Error: Configuración incompleta en .env{Style.RESET_ALL}")
        return

    # Lista de endpoints para probar (varias versiones de la API)
    endpoints_to_test = [
        # Endpoints de información del servidor (varias variantes)
        ("/api/server-info/ping", "GET", "Ping del servidor (API v1)"),
        ("/api/server-info/version", "GET", "Versión del servidor (API v1)"),
        ("/api/server-info", "GET", "Información del servidor (API v1)"),
        ("/server-info/ping", "GET", "Ping del servidor (sin /api)"),
        ("/api/server/ping", "GET", "Ping del servidor (API alternativa)"),

        # Endpoints de assets (varias variantes)
        ("/api/assets", "GET", "Endpoint de assets (API v1)"),
        ("/api/asset", "GET", "Endpoint de asset (singular)"),
        ("/api/asset/upload", "GET", "Endpoint de upload (legacy)"),
        ("/asset/upload", "GET", "Endpoint de upload (sin /api)"),
        ("/api/upload", "GET", "Endpoint de upload (directo)"),

        # Otros endpoints útiles
        ("/api/auth/validateToken", "POST", "Validar token de API"),
        ("/api/user/me", "GET", "Información del usuario actual"),
        ("/api/users/me", "GET", "Información del usuario (plural)"),
        ("/api/albums", "GET", "Listado de álbumes"),
        ("/api/library", "GET", "Biblioteca de medios"),
    ]

    print(f"\n🔌 Probando endpoints...\n")

    session = requests.Session()
    session.headers.update({
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY,
    })

    working_endpoints = 0

    for endpoint, method, description in endpoints_to_test:
        url = f"{IMMICH_URL}{endpoint}"
        try:
            if method == "GET":
                response = session.get(url, timeout=5)
            elif method == "POST":
                # POST con body vacío o mínimo
                response = session.post(url, json={}, timeout=5)
            else:
                response = session.request(method, url, timeout=5)

            status = response.status_code

            # Colorear según resultado
            if status == 200:
                color = Fore.GREEN
                icon = "✅"
                working_endpoints += 1
            elif status == 401:
                color = Fore.YELLOW
                icon = "🔐"
            elif status == 404:
                color = Fore.YELLOW
                icon = "⚠️"
            elif status >= 500:
                color = Fore.RED
                icon = "❌"
            else:
                color = Fore.CYAN
                icon = "ℹ️"
                working_endpoints += 1

            print(f"{color}{icon} {endpoint}{Style.RESET_ALL}")
            print(f"   {description}")
            print(f"   Status: {status}")

            # Mostrar respuesta si es pequeña y útil
            if status == 200 and len(response.text) < 200:
                print(f"   Respuesta: {response.text[:100]}")

            print()

        except requests.exceptions.Timeout:
            print(f"{Fore.RED}❌ {endpoint}{Style.RESET_ALL}")
            print(f"   {description}")
            print(f"   Error: Timeout (servidor no responde)\n")
        except requests.exceptions.ConnectionError:
            print(f"{Fore.RED}❌ {endpoint}{Style.RESET_ALL}")
            print(f"   {description}")
            print(f"   Error: No se pudo conectar al servidor\n")
        except Exception as e:
            print(f"{Fore.RED}❌ {endpoint}{Style.RESET_ALL}")
            print(f"   {description}")
            print(f"   Error: {str(e)}\n")

    session.close()

    # Resumen
    print("=" * 60)
    if working_endpoints > 0:
        print(f"{Fore.GREEN}✅ Resultado: {working_endpoints}/{len(endpoints_to_test)} endpoints respondieron{Style.RESET_ALL}")
        print(f"{Fore.GREEN}   El servidor Immich parece estar accesible{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}❌ Resultado: Ningún endpoint respondió correctamente{Style.RESET_ALL}")
        print(f"{Fore.RED}   Verifica que Immich esté corriendo y la URL sea correcta{Style.RESET_ALL}")
    print("=" * 60 + "\n")


def main():
    """Función principal"""
    global THREADS

    # Parsear argumentos
    parser = argparse.ArgumentParser(
        description='Gestor de Subida a Immich',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Ejemplos:
  python main.py                    # Todo con 1 hilo
  python main.py --threads=5        # Todo con 5 hilos
  python main.py -t 10              # Todo con 10 hilos
  python main.py -f 2019            # Solo carpeta 2019
  python main.py -t 5 -f 2019       # Carpeta 2019 con 5 hilos
  python main.py -f "2019/2019-04"  # Subcarpeta específica
        '''
    )
    parser.add_argument(
        '-t', '--threads',
        type=int,
        default=1,
        metavar='N',
        help='Número de hilos para subidas paralelas (default: 1)'
    )
    parser.add_argument(
        '-f', '--folder',
        type=str,
        default=None,
        metavar='PATH',
        help='Carpeta específica a procesar (relativa a SOURCE_DIR, ej: "2019" o "2019/2019-04-06")'
    )

    args = parser.parse_args()
    THREADS = args.threads
    folder_filter = args.folder

    # Validar número de hilos
    if THREADS < 1:
        print("❌ Error: El número de hilos debe ser mayor o igual a 1")
        sys.exit(1)
    if THREADS > 20:
        print("⚠️  Advertencia: Usar más de 20 hilos puede sobrecargar el servidor")
        response = input("¿Continuar de todas formas? (s/n): ")
        if response.lower() != 's':
            sys.exit(0)

    # Validar carpeta si se especificó
    if folder_filter:
        from config import SOURCE_DIR
        import os
        full_path = os.path.join(SOURCE_DIR, folder_filter)
        if not os.path.exists(full_path):
            print(f"❌ Error: La carpeta '{folder_filter}' no existe en {SOURCE_DIR}")
            sys.exit(1)
        if not os.path.isdir(full_path):
            print(f"❌ Error: '{folder_filter}' no es una carpeta")
            sys.exit(1)
        logger.info(f"Aplicación iniciada con {THREADS} hilo(s) - Carpeta: {folder_filter}")
        print(f"🚀 Gestor de Subida a Immich - Carpeta: {folder_filter}\n")
    else:
        logger.info(f"Aplicación iniciada con {THREADS} hilo(s)")
        print("🚀 Gestor de Subida a Immich\n")

    while True:
        try:
            choice = show_menu(folder_filter)

            if choice == '1':
                logger.info(f"Usuario seleccionó: Escanear directorios - Carpeta: {folder_filter or 'todas'}")
                print("\n📁 Escaneando directorios y poblando base de datos...")
                scan_and_populate_db(folder_filter=folder_filter)
                input("\n✅ Presione Enter para continuar...")

            elif choice == '2':
                logger.info(f"Usuario seleccionó: Subir archivos pendientes ({THREADS} hilos)")
                print(f"\n📤 Subiendo archivos pendientes a Immich con {THREADS} hilo(s)...")
                upload_pending_files(threads=THREADS)
                input("\n✅ Presione Enter para continuar...")

            elif choice == '3':
                logger.info("Usuario seleccionó: Mostrar resumen")
                show_summary()
                input("✅ Presione Enter para continuar...")

            elif choice == '4':
                logger.info(f"Usuario seleccionó: Modo combinado ({THREADS} hilos) - Carpeta: {folder_filter or 'todas'}")
                print(f"\n🔄 Escaneando y subiendo en un solo proceso con {THREADS} hilo(s)...")
                sync_and_upload(threads=THREADS, folder_filter=folder_filter)
                input("\n✅ Presione Enter para continuar...")

            elif choice == '5':
                logger.info("Usuario seleccionó: Verificar conexión")
                check_endpoints()
                input("✅ Presione Enter para continuar...")

            elif choice == '6':
                print("\n👋 Saliendo...")
                logger.info("Aplicación cerrada por el usuario")
                sys.exit(0)

            else:
                print("⚠️  Opción no válida. Por favor seleccione 1-6.")

        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupción detectada. Saliendo...")
            logger.info("Aplicación interrumpida por el usuario")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ Error inesperado: {str(e)}")
            logger.error(f"Error en main: {str(e)}", exc_info=True)
            input("\nPresione Enter para continuar...")


if __name__ == "__main__":
    main()
