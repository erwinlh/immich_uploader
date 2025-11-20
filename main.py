#!/usr/bin/env python3
"""
Script principal para coordinar el proceso de subida de fotos/videos a Immich
VERSIÓN MEJORADA con logging y mejor arquitectura
"""
import sys
import os
from config import LOGO_FILE
from db_manager import DatabaseManager
from logger import logger
from scan_files import scan_and_populate_db
from upload_files import upload_pending_files
from sync_upload import sync_and_upload


def show_menu():
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
    print("1. Escanear directorios y poblar base de datos")
    print("2. Subir archivos pendientes a Immich")
    print("3. Mostrar resumen de estado")
    print("4. Escanear y subir en un solo proceso (Recomendado)")
    print("5. Salir")
    choice = input("\nSeleccione una opción (1-5): ")
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


def main():
    """Función principal"""
    logger.info("Aplicación iniciada")
    print("🚀 Gestor de Subida a Immich\n")

    while True:
        try:
            choice = show_menu()

            if choice == '1':
                logger.info("Usuario seleccionó: Escanear directorios")
                print("\n📁 Escaneando directorios y poblando base de datos...")
                scan_and_populate_db()
                input("\n✅ Presione Enter para continuar...")

            elif choice == '2':
                logger.info("Usuario seleccionó: Subir archivos pendientes")
                print("\n📤 Subiendo archivos pendientes a Immich...")
                upload_pending_files()
                input("\n✅ Presione Enter para continuar...")

            elif choice == '3':
                logger.info("Usuario seleccionó: Mostrar resumen")
                show_summary()
                input("✅ Presione Enter para continuar...")

            elif choice == '4':
                logger.info("Usuario seleccionó: Modo combinado")
                print("\n🔄 Escaneando y subiendo en un solo proceso...")
                sync_and_upload()
                input("\n✅ Presione Enter para continuar...")

            elif choice == '5':
                print("\n👋 Saliendo...")
                logger.info("Aplicación cerrada por el usuario")
                sys.exit(0)

            else:
                print("⚠️  Opción no válida. Por favor seleccione 1-5.")

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
