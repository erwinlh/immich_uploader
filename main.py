#!/usr/bin/env python3
"""
Script principal para coordinar el proceso de subida de fotos/videos a Immich
"""
import sys
import os
from scan_files import scan_and_populate_db
from upload_files import upload_pending_files

def show_menu():
    """Mostrar menú de opciones"""
    # Leer y mostrar el logo ASCII
    try:
        with open('/Users/erwin/Desktop/desde-nas/ansi-logo.utf.ans', 'r', encoding='utf-8') as logo_file:
            logo = logo_file.read()
            print(logo)
    except:
        # Si no se puede leer el logo, mostrar el encabezado normal
        print("\n=== Gestor de Subida a Immich ===")
    
    print("=== Gestor de Subida a Immich ===")
    print("1. Escanear directorios y poblar base de datos")
    print("2. Subir archivos pendientes a Immich")
    print("3. Mostrar resumen de estado")
    print("4. Escanear y subir en un solo proceso")
    print("5. Salir")
    choice = input("\nSeleccione una opción (1-5): ")
    return choice

def show_summary():
    """Mostrar resumen de estado de la base de datos"""
    import pymysql
    from dotenv import load_dotenv
    import json
    
    load_dotenv()
    
    # Configuración de la base de datos
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_NAME = os.getenv('DB_NAME', 'immich_uploader')
    DB_PORT = int(os.getenv('DB_PORT', 3306))
    
    try:
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            charset='utf8mb4'
        )
        
        cursor = connection.cursor()
        
        # Contar archivos por estado
        cursor.execute("SELECT upload_status, COUNT(*) FROM media_files GROUP BY upload_status")
        results = cursor.fetchall()
        
        print("\n=== Resumen de estado ===")
        total = 0
        for status, count in results:
            print(f"- {status}: {count}")
            total += count
        
        print(f"Total: {total} archivos")
        
        # Contar pendientes
        cursor.execute("SELECT COUNT(*) FROM media_files WHERE upload_status IN ('pending', 'error')")
        pending_count = cursor.fetchone()[0]
        print(f"Pendientes para subir: {pending_count}")
        
        # Contar archivos con metadatos
        cursor.execute("SELECT COUNT(*) FROM media_files WHERE metadata_info IS NOT NULL AND metadata_info != 'null'")
        metadata_count = cursor.fetchone()[0]
        print(f"Archivos con metadatos: {metadata_count}")
        
        # Estadísticas de subida
        cursor.execute("SELECT COUNT(*) FROM media_files WHERE upload_status = 'success'")
        success_count = cursor.fetchone()[0]
        print(f"Subidas exitosas: {success_count}")
        
        cursor.execute("SELECT COUNT(*) FROM media_files WHERE upload_status = 'duplicate'")
        duplicate_count = cursor.fetchone()[0]
        print(f"Duplicados detectados: {duplicate_count}")
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"Error obteniendo resumen: {str(e)}")

def main():
    """Función principal"""
    print("Gestor de Subida a Immich")
    
    while True:
        choice = show_menu()
        
        if choice == '1':
            print("\nEscaneando directorios y poblando base de datos...")
            scan_and_populate_db()
        elif choice == '2':
            print("\nSubiendo archivos pendientes a Immich...")
            upload_pending_files()
        elif choice == '3':
            print("\nObteniendo resumen de estado...")
            show_summary()
        elif choice == '4':
            print("\nEscaneando y subiendo en un solo proceso...")
            from sync_upload import sync_and_upload
            sync_and_upload()
        elif choice == '5':
            print("Saliendo...")
            sys.exit(0)
        else:
            print("Opción no válida. Por favor seleccione 1-5.")

if __name__ == "__main__":
    main()