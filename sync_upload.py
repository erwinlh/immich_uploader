#!/usr/bin/env python3
"""
Script combinado para escanear, poblar base de datos e inmediatamente intentar subir archivos a Immich
"""
import os
import hashlib
import json
from pathlib import Path
import pymysql
from dotenv import load_dotenv
import time
import requests
import exifread
from PIL import Image
from tqdm import tqdm
from colorama import init, Fore, Style
init()  # Inicializar colorama

# Cargar variables de entorno
load_dotenv()

# Configuración de Immich
IMMICH_URL = os.getenv('IMMICH_URL')
IMMICH_API_KEY = os.getenv('IMMICH_API_KEY')

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
                for tag, value in tags.items():
                    if 'GPS' in tag or 'Image' in tag or 'EXIF' in tag:
                        metadata[tag] = str(value)
        
        # Obtener dimensiones si es una imagen
        if ext in ['.jpg', '.jpeg', '.tiff', '.tif', '.png', '.webp', '.bmp']:
            with Image.open(filepath) as img:
                metadata['image_width'], metadata['image_height'] = img.size
                metadata['image_mode'] = img.mode
        
    except Exception as e:
        metadata['error'] = f"Error leyendo metadatos: {str(e)}"
    
    return metadata

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

def insert_or_update_file_record(connection, filepath, filename, directory, file_size, file_hash, extension, metadata):
    """Insertar o actualizar registro de archivo en la base de datos"""
    cursor = connection.cursor()
    
    try:
        # Verificar si el archivo ya existe
        query = """
        SELECT id, upload_status FROM media_files WHERE filepath = %s
        """
        cursor.execute(query, (filepath,))
        result = cursor.fetchone()
        
        metadata_json = json.dumps(metadata)
        
        if result:
            # Si el archivo ya existe, verificar si ya fue subido exitosamente
            file_id, current_status = result
            if current_status in ['success', 'duplicate']:
                # Archivo ya fue subido exitosamente, no hacer nada
                return current_status, file_id
            else:
                # Archivo existe pero no fue subido exitosamente, actualizar registro
                query = """
                UPDATE media_files 
                SET filename=%s, directory=%s, file_size=%s, hash=%s, extension=%s, metadata_info=%s
                WHERE filepath = %s
                """
                cursor.execute(query, (filename, directory, file_size, file_hash, extension, metadata_json, filepath))
                connection.commit()
                return 'pending', file_id
        
        # Insertar nuevo registro
        query = """
        INSERT INTO media_files (filepath, filename, directory, file_size, hash, extension, metadata_info)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (filepath, filename, directory, file_size, file_hash, extension, metadata_json))
        file_id = cursor.lastrowid
        connection.commit()
        return 'pending', file_id
        
    except Exception as e:
        print(f"Error insertando/actualizando registro para {filepath}: {str(e)}")
        connection.rollback()
        return None, None
    finally:
        cursor.close()

def upload_file_to_immich(filepath):
    """Subir un archivo a Immich"""
    url = f"{IMMICH_URL}/api/assets"
    
    import os
    from datetime import datetime
    
    stats = os.stat(filepath)
    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY,
    }
    
    data = {
        'deviceAssetId': f'{os.path.basename(filepath)}-{stats.st_mtime}',
        'deviceId': 'immich-uploader-script',
        'fileCreatedAt': datetime.fromtimestamp(stats.st_mtime).isoformat(),
        'fileModifiedAt': datetime.fromtimestamp(stats.st_mtime).isoformat(),
        'isFavorite': 'false',
    }
    
    try:
        with open(filepath, 'rb') as file:
            files = {
                'assetData': (os.path.basename(filepath), file, 'application/octet-stream')
            }
            
            response = requests.post(url, headers=headers, data=data, files=files)
            
            return {
                'status_code': response.status_code,
                'response_text': response.text,
                'headers': dict(response.headers)
            }
    except Exception as e:
        return {
            'status_code': 0,
            'error': str(e),
            'response_text': None
        }

def update_file_status(connection, file_id, status, api_response=None):
    """Actualizar el estado de un archivo en la base de datos"""
    cursor = connection.cursor()
    
    try:
        query = """
        UPDATE media_files 
        SET upload_status = %s, api_response = %s, upload_date = NOW()
        WHERE id = %s
        """
        cursor.execute(query, (status, json.dumps(api_response) if api_response else None, file_id))
        connection.commit()
        return True
    except Exception as e:
        print(f"Error actualizando estado para ID {file_id}: {str(e)}")
        connection.rollback()
        return False
    finally:
        cursor.close()

def sync_and_upload():
    """Escanear directorios, poblar base de datos e intentar subir cada archivo"""
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
    uploaded = 0
    duplicates = 0
    errors = 0
    skipped = 0
    consecutive_errors = 0
    max_consecutive_errors = 5  # Número máximo de errores consecutivos antes de detener
    
    import time
    start_time = time.time()
    
    # Procesar cada archivo: escanear, poblar DB, intentar subida
    for i, filepath in enumerate(files_to_process, 1):
        try:
            # Mostrar archivo actual que se está procesando
            print(f"\rProcesando {i}/{len(files_to_process)}: {os.path.basename(filepath)}", end='', flush=True)
            
            if not os.path.exists(filepath):
                errors += 1
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    print(f"\n\nDemasiados errores consecutivos ({consecutive_errors}). Deteniendo el proceso.")
                    break
                continue
            else:
                consecutive_errors = 0  # Reiniciar contador de errores consecutivos
            
            # Obtener información del archivo
            path_obj = Path(filepath)
            filename = path_obj.name
            directory = str(path_obj.parent)
            file_size = os.path.getsize(filepath)
            extension = path_obj.suffix.lower().lstrip('.')
            
            # Calcular hash
            file_hash = get_file_hash(filepath)
            if not file_hash:
                errors += 1
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    print(f"\n\nDemasiados errores consecutivos ({consecutive_errors}). Deteniendo el proceso.")
                    break
                continue
            else:
                consecutive_errors = 0  # Reiniciar contador de errores consecutivos
            
            # Extraer metadatos
            metadata = extract_metadata(filepath)
            
            # Insertar o actualizar registro en la base de datos
            status, file_id = insert_or_update_file_record(
                connection, filepath, filename, directory, 
                file_size, file_hash, extension, metadata
            )
            
            if status is None:
                errors += 1
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    print(f"\n\nDemasiados errores consecutivos ({consecutive_errors}). Deteniendo el proceso.")
                    break
                continue
            else:
                consecutive_errors = 0  # Reiniciar contador de errores consecutivos
            
            # Si el archivo ya fue subido exitosamente, omitir
            if status in ['success', 'duplicate']:
                skipped += 1
                print(f"\r{' ' * 100}")  # Limpiar línea
                if status == 'duplicate':
                    print(f"\rProcesando {i}/{len(files_to_process)}: {os.path.basename(filepath)} - {Fore.YELLOW}⚠ Saltado (ya subido){Style.RESET_ALL}")
                else:  # success
                    print(f"\rProcesando {i}/{len(files_to_process)}: {os.path.basename(filepath)} - {Fore.YELLOW}⚠ Saltado (ya subido){Style.RESET_ALL}")
                continue
            
            # Intentar subir archivo a Immich
            start_upload_time = time.time()
            response = upload_file_to_immich(filepath)
            upload_time = time.time() - start_upload_time
            speed_mbps = (file_size / upload_time / 1024 / 1024) if upload_time > 0 else 0
            
            # Manejar respuesta y actualizar estado
            if response['status_code'] in [200, 201]:  # 200 OK o 201 Created
                # Analizar respuesta para determinar si es duplicado
                try:
                    response_data = json.loads(response['response_text']) if response['response_text'] else {}
                    if response_data.get('status') == 'duplicate':
                        # Es un duplicado
                        update_file_status(connection, file_id, 'duplicate', response)
                        duplicates += 1
                        status_msg = f"{Fore.YELLOW}⚠ Duplicado ({response['status_code']}){Style.RESET_ALL}"
                        consecutive_errors = 0  # Reiniciar contador de errores consecutivos
                    else:
                        # Es un archivo nuevo subido exitosamente
                        update_file_status(connection, file_id, 'success', response)
                        uploaded += 1
                        status_msg = f"{Fore.GREEN}✅ Subido OK ({response['status_code']}) - {upload_time:.2f}s ({speed_mbps:.2f}MB/s){Style.RESET_ALL}"
                        consecutive_errors = 0  # Reiniciar contador de errores consecutivos
                except:
                    # Si no se puede parsear JSON, asumir éxito normal
                    update_file_status(connection, file_id, 'success', response)
                    uploaded += 1
                    status_msg = f"{Fore.GREEN}✅ Subido OK ({response['status_code']}) - {upload_time:.2f}s ({speed_mbps:.2f}MB/s){Style.RESET_ALL}"
                    consecutive_errors = 0  # Reiniciar contador de errores consecutivos
            elif response['status_code'] == 409:  # Conflict - archivo duplicado
                update_file_status(connection, file_id, 'duplicate', response)
                duplicates += 1
                status_msg = f"{Fore.YELLOW}⚠ Duplicado ({response['status_code']}){Style.RESET_ALL}"
                consecutive_errors = 0  # Reiniciar contador de errores consecutivos
            else:
                update_file_status(connection, file_id, 'error', response)
                errors += 1
                consecutive_errors += 1
                status_msg = f"{Fore.RED}❌ Error ({response['status_code']}){Style.RESET_ALL}"
                
                # Si hay demasiados errores consecutivos, detener el proceso
                if consecutive_errors >= max_consecutive_errors:
                    print(f"\n\nDemasiados errores consecutivos en la API ({consecutive_errors}). Deteniendo el proceso.")
                    print(f"Último error: {response.get('response_text', 'Unknown error')[:200]}")
                    break
            
            # Limpiar línea y mostrar resultado detallado
            print(f"\r{' ' * 100}")  # Limpiar línea
            print(f"\rProcesando {i}/{len(files_to_process)}: {os.path.basename(filepath)} - {status_msg}")
            
            # Mostrar información de metadatos si es una imagen
            try:
                meta_parts = []
                
                # Añadir dimensiones
                if 'image_width' in metadata and 'image_height' in metadata:
                    meta_parts.append(f"{metadata['image_width']}x{metadata['image_height']}")
                else:
                    meta_parts.append("Dimensiones: N/A")
                
                # Añadir información de cámara
                camera_info = []
                if 'camera_make' in metadata:
                    camera_info.append(str(metadata['camera_make']))
                if 'camera_model' in metadata:
                    camera_info.append(str(metadata['camera_model']))
                
                if camera_info:
                    meta_parts.append(f"Cámara: {' '.join(camera_info)}")
                else:
                    meta_parts.append("Cámara: N/A")
                
                # Añadir información de lente
                if 'lens_model' in metadata:
                    meta_parts.append(f"Lente: {metadata['lens_model']}")
                else:
                    meta_parts.append("Lente: N/A")
                
                # Manejar datos de configuración de disparo
                f_number_display = ""
                if 'f_number' in metadata:
                    f_val = str(metadata['f_number'])
                    if f_val.startswith("FNumber "):
                        f_val = f_val[8:]
                    elif f_val.startswith("f/"):
                        f_val = f_val[2:]
                    f_number_display = f"f/{f_val}"
                elif 'f_number' in metadata:
                    f_val = str(metadata['f_number'])
                    if f_val.startswith("FNumber "):
                        f_val = f_val[8:]
                    f_number_display = f"f/{f_val}"
                    
                exp_time_display = ""
                if 'exposure_time' in metadata:
                    exp_val = str(metadata['exposure_time'])
                    if exp_val.startswith("ExposureTime "):
                        exp_val = exp_val[13:]
                    exp_time_display = f"{exp_val}"
                
                iso_display = ""
                if 'iso' in metadata:
                    iso_val = str(metadata['iso'])
                    if iso_val.startswith("ISOSpeedRatings "):
                        iso_val = iso_val[16:]
                    elif iso_val.startswith("ISO"):
                        iso_val = iso_val[3:]
                    iso_display = f"ISO{iso_val}"
                
                # Crear string de configuración de disparo
                config_parts = []
                if f_number_display:
                    config_parts.append(f_number_display)
                if exp_time_display:
                    config_parts.append(exp_time_display)
                if iso_display:
                    config_parts.append(iso_display)
                
                if config_parts:
                    meta_parts.append(f"Config: {', '.join(config_parts)}")
                else:
                    meta_parts.append("Config: N/A")
                
                print(f"   Metadatos: {', '.join(meta_parts)}")
            except Exception as e:
                # En caso de error, mostrar mensaje básico
                print("   Metadatos: No disponibles")
            
            # Mostrar detalles de la subida exitosa
            if response['status_code'] in [200, 201]:
                # Solo mostrar detalles de velocidad para archivos nuevos, no para duplicados
                try:
                    response_data = json.loads(response['response_text']) if response['response_text'] else {}
                    if response_data.get('status') != 'duplicate':
                        print(f"   Detalles: {file_size / (1024*1024):.2f}MB en {upload_time:.2f}s a {speed_mbps:.2f}MB/s")
                except:
                    # Si no se puede parsear JSON, mostrar detalles normalmente
                    print(f"   Detalles: {file_size / (1024*1024):.2f}MB en {upload_time:.2f}s a {speed_mbps:.2f}MB/s")
            
            # Mostrar respuesta de la API si no es exitosa o duplicado
            if response['status_code'] not in [200, 201, 409] and response.get('response_text'):
                print(f"   Respuesta API: {response['response_text'][:100]}{'...' if len(response['response_text']) > 100 else ''}")
            elif response['status_code'] in [200, 201]:
                # Para 200/201, mostrar solo si es un error o información adicional
                try:
                    response_data = json.loads(response['response_text']) if response['response_text'] else {}
                    if response_data.get('status') == 'duplicate':
                        print(f"   Detalles: Duplicado - archivo ya existente en Immich")
                except:
                    # Si no se puede parsear JSON, no mostrar nada adicional
                    pass
            
            processed += 1
            
            # Pequeña pausa para no sobrecargar el servidor
            time.sleep(0.1)
            
        except KeyboardInterrupt:
            print("\n\nProceso interrumpido por el usuario.")
            break
        except Exception as e:
            print(f"\nError procesando archivo {filepath}: {str(e)}")
            errors += 1
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                print(f"\n\nDemasiados errores consecutivos ({consecutive_errors}). Deteniendo el proceso.")
                break
    
    total_time = time.time() - start_time
    avg_speed = processed / total_time if total_time > 0 else 0
    
    connection.close()
    
    print(f"\nResumen del proceso:")
    print(f"- Archivos procesados: {processed}")
    print(f"- Subidas exitosas: {uploaded}")
    print(f"- Duplicados encontrados: {duplicates}")
    print(f"- Ya subidos previamente: {skipped}")
    print(f"- Errores: {errors}")
    print(f"- Tiempo total: {total_time:.2f}s")
    print(f"- Velocidad promedio: {avg_speed:.2f} archivos/s")

if __name__ == "__main__":
    sync_and_upload()