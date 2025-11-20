#!/usr/bin/env python3
"""
Script para escanear directorios y poblar la base de datos con información de archivos
"""
import os
import hashlib
import mimetypes
from pathlib import Path
import pymysql
from dotenv import load_dotenv
import sys
from tqdm import tqdm
import json
import exifread
from PIL import Image
from PIL.ExifTags import TAGS

# Cargar variables de entorno
load_dotenv()

# Configuración de la base de datos
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'immich_uploader')
DB_PORT = int(os.getenv('DB_PORT', 3306))

# Directorio de origen
SOURCE_DIR = os.getenv('SOURCE_DIR', '/Users/erwin/Desktop/desde-nas')

# Extensiones permitidas
IMAGE_EXTENSIONS = set(os.getenv('IMAGE_EXTENSIONS', 'jpg,jpeg,png,webp,tiff,tif,bmp,heic,heif').lower().split(','))
VIDEO_EXTENSIONS = set(os.getenv('VIDEO_EXTENSIONS', 'mp4,mov,avi,mkv,wmv,flv,webm,m4v').lower().split(','))

def get_file_hash(filepath):
    """Calcular hash SHA-256 de un archivo"""
    hash_sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            # Leer el archivo en bloques para manejar archivos grandes
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    except Exception as e:
        print(f"Error calculando hash para {filepath}: {str(e)}")
        return None

def get_file_type(filepath):
    """Determinar si es imagen o video basado en la extensión"""
    ext = Path(filepath).suffix.lower().lstrip('.')
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    elif ext in VIDEO_EXTENSIONS:
        return 'video'
    return None

def connect_db():
    """Conectar a la base de datos"""
    try:
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            charset='utf8mb4'
        )
        return connection
    except Exception as e:
        print(f"Error conectando a la base de datos: {str(e)}")
        return None

def extract_metadata(filepath):
    """Extraer metadatos de un archivo de imagen o video"""
    metadata = {}
    
    try:
        # Obtener metadatos básicos del sistema de archivos
        stat_info = os.stat(filepath)
        metadata['file_size'] = stat_info.st_size
        metadata['created_time'] = stat_info.st_ctime
        metadata['modified_time'] = stat_info.st_mtime
        
        # Extraer metadatos EXIF si es una imagen
        ext = Path(filepath).suffix.lower()
        if ext in ['.jpg', '.jpeg', '.tiff', '.tif', '.png']:
            # Usar exifread para obtener metadatos EXIF
            with open(filepath, 'rb') as f:
                tags = exifread.process_file(f)
                
                # Extraer información específica de cámara
                if 'Image Make' in tags:
                    metadata['camera_make'] = str(tags['Image Make']).strip()
                if 'Image Model' in tags:
                    metadata['camera_model'] = str(tags['Image Model']).strip()
                if 'EXIF LensModel' in tags:
                    metadata['lens_model'] = str(tags['EXIF LensModel']).strip()
                if 'EXIF DateTimeOriginal' in tags:
                    metadata['date_taken'] = str(tags['EXIF DateTimeOriginal']).strip()
                if 'EXIF ExposureTime' in tags:
                    metadata['exposure_time'] = str(tags['EXIF ExposureTime']).strip()
                if 'EXIF FNumber' in tags:
                    metadata['f_number'] = str(tags['EXIF FNumber']).strip()
                if 'EXIF ISO' in tags:
                    metadata['iso'] = str(tags['EXIF ISO']).strip()
                if 'EXIF FocalLength' in tags:
                    metadata['focal_length'] = str(tags['EXIF FocalLength']).strip()
                if 'EXIF Flash' in tags:
                    metadata['flash'] = str(tags['EXIF Flash']).strip()
                if 'GPS GPSLatitude' in tags:
                    metadata['gps_latitude'] = str(tags['GPS GPSLatitude']).strip()
                if 'GPS GPSLongitude' in tags:
                    metadata['gps_longitude'] = str(tags['GPS GPSLongitude']).strip()
        
        # Obtener dimensiones si es una imagen
        if ext in ['.jpg', '.jpeg', '.tiff', '.tif', '.png', '.webp', '.bmp']:
            with Image.open(filepath) as img:
                metadata['image_width'], metadata['image_height'] = img.size
                metadata['image_mode'] = img.mode
        
    except Exception as e:
        metadata['error'] = f"Error leyendo metadatos: {str(e)}"
    
    return metadata

def insert_file_record(connection, filepath, filename, directory, file_size, file_hash, extension):
    """Insertar o actualizar registro de archivo en la base de datos"""
    cursor = connection.cursor()
    
    try:
        # Verificar si el archivo ya existe
        query = """
        SELECT id FROM media_files WHERE filepath = %s
        """
        cursor.execute(query, (filepath,))
        result = cursor.fetchone()
        
        if result:
            # Si el archivo ya existe, no hacer nada
            return True
        
        # Extraer metadatos
        metadata = extract_metadata(filepath)
        metadata_json = json.dumps(metadata)
        
        # Insertar nuevo registro
        query = """
        INSERT INTO media_files (filepath, filename, directory, file_size, hash, extension, metadata_info)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (filepath, filename, directory, file_size, file_hash, extension, metadata_json))
        connection.commit()
        return True
    except Exception as e:
        print(f"Error insertando registro para {filepath}: {str(e)}")
        connection.rollback()
        return False
    finally:
        cursor.close()

def scan_and_populate_db():
    """Escanear directorios y poblar la base de datos"""
    print("Conectando a la base de datos...")
    connection = connect_db()
    if not connection:
        print("No se pudo conectar a la base de datos")
        return
    
    print(f"Escaneando directorio: {SOURCE_DIR}")
    
    # Obtener lista de archivos
    files_to_process = []
    for root, dirs, files in os.walk(SOURCE_DIR):
        for file in files:
            filepath = os.path.join(root, file)
            file_type = get_file_type(filepath)
            
            if file_type:  # Es imagen o video
                files_to_process.append(filepath)
    
    # Ordenar por fecha de modificación (de más antiguo a más reciente)
    files_to_process.sort(key=lambda x: os.path.getmtime(x))
    
    print(f"Se encontraron {len(files_to_process)} archivos multimedia para procesar")
    
    processed = 0
    skipped = 0
    consecutive_errors = 0
    max_consecutive_errors = 5  # Número máximo de errores consecutivos antes de detener
    
    import time
    start_time = time.time()
    
    # Procesar archivos mostrando en tiempo real el archivo que se está procesando
    for i, filepath in enumerate(files_to_process, 1):
        start_process_time = time.time()
        
        # Mostrar archivo actual que se está procesando
        print(f"\rProcesando {i}/{len(files_to_process)}: {os.path.basename(filepath)}", end='', flush=True)
        
        try:
            # Obtener información del archivo
            path_obj = Path(filepath)
            filename = path_obj.name
            directory = str(path_obj.parent)
            file_size = os.path.getsize(filepath)
            extension = path_obj.suffix.lower().lstrip('.')
            
            # Calcular hash
            file_hash = get_file_hash(filepath)
            if not file_hash:
                skipped += 1
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    print(f"\n\nDemasiados errores consecutivos ({consecutive_errors}). Deteniendo el proceso.")
                    break
                continue
            else:
                consecutive_errors = 0  # Reiniciar contador de errores consecutivos
            
            # Calcular tiempo de procesamiento
            process_time = time.time() - start_process_time
            
            # Insertar en la base de datos
            if insert_file_record(connection, filepath, filename, directory, file_size, file_hash, extension):
                processed += 1
                status_msg = f"✓ Procesado ({process_time:.2f}s)"
                consecutive_errors = 0  # Reiniciar contador de errores consecutivos
            else:
                skipped += 1
                consecutive_errors += 1
                status_msg = f"✗ Error al insertar"
                
                # Si hay demasiados errores consecutivos, detener el proceso
                if consecutive_errors >= max_consecutive_errors:
                    print(f"\n\nDemasiados errores consecutivos ({consecutive_errors}). Deteniendo el proceso.")
                    break
            
            # Limpiar línea y mostrar resultado detallado
            print(f"\r{' ' * 100}")  # Limpiar línea
            print(f"\rProcesando {i}/{len(files_to_process)}: {os.path.basename(filepath)} - {status_msg}")
            
        except KeyboardInterrupt:
            print(f"\n\nProceso interrumpido por el usuario.")
            break
        except Exception as e:
            print(f"\nError procesando archivo {filepath}: {str(e)}")
            skipped += 1
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                print(f"\n\nDemasiados errores consecutivos ({consecutive_errors}). Deteniendo el proceso.")
                break
    
    total_time = time.time() - start_time
    avg_speed = processed / total_time if total_time > 0 else 0
    
    connection.close()
    print(f"\nProceso completado: {processed} archivos procesados, {skipped} archivos con errores")
    print(f"- Tiempo total: {total_time:.2f}s")
    print(f"- Velocidad promedio: {avg_speed:.2f} archivos/s")

if __name__ == "__main__":
    scan_and_populate_db()