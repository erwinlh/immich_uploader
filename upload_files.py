#!/usr/bin/env python3
"""
Script para subir archivos a Immich desde la base de datos
"""
import os
import requests
import pymysql
from dotenv import load_dotenv
import time
from tqdm import tqdm
import json
import exifread
from PIL import Image
from PIL.ExifTags import TAGS
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

def get_pending_files(connection):
    """Obtener archivos pendientes de subida"""
    cursor = connection.cursor()
    
    try:
        query = """
        SELECT id, filepath, hash, metadata_info
        FROM media_files 
        WHERE upload_status IN ('pending', 'error') 
        """
        cursor.execute(query)
        results = cursor.fetchall()
        
        # Ordenar por fecha de captura (de más nuevo a más antiguo)
        # Primero intentar con date_taken (fecha original de la foto), luego modified_time
        import json
        def extract_capture_time(row):
            try:
                metadata = json.loads(row[3]) if row[3] else {}
                date_taken = metadata.get('date_taken', None)
                
                # Si hay fecha de toma original, usarla
                if date_taken:
                    from datetime import datetime
                    # Convertir string de fecha a timestamp
                    try:
                        dt = datetime.strptime(date_taken, "%Y:%m:%d %H:%M:%S")
                        return dt.timestamp()
                    except ValueError:
                        # Si el formato no es compatible, probar otros formatos
                        try:
                            dt = datetime.strptime(date_taken.split('.')[0], "%Y:%m:%d %H:%M:%S")
                            return dt.timestamp()
                        except ValueError:
                            pass
                
                # Si no hay fecha de toma, usar modified_time como fallback
                modified_time = metadata.get('modified_time', 0)
                return modified_time
            except:
                # En caso de error, usar 0 como fallback
                return 0
        
        results = sorted(results, key=extract_capture_time, reverse=True)  # reverse=True para más nuevo primero
        return results
    except Exception as e:
        print(f"Error obteniendo archivos pendientes: {str(e)}")
        return []
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

def upload_pending_files():
    """Subir archivos pendientes a Immich"""
    print("Conectando a la base de datos...")
    connection = connect_db()
    if not connection:
        print("No se pudo conectar a la base de datos")
        return
    
    print("Obteniendo archivos pendientes...")
    pending_files = get_pending_files(connection)
    print(f"Se encontraron {len(pending_files)} archivos pendientes para subir")
    
    successful_uploads = 0
    duplicate_uploads = 0
    failed_uploads = 0
    consecutive_errors = 0
    max_consecutive_errors = 5  # Número máximo de errores consecutivos antes de detener
    
    import time
    start_time = time.time()
    
    # Subir archivos mostrando en tiempo real el archivo que se está subiendo
    for i, (file_id, filepath, file_hash, metadata_str) in enumerate(pending_files, 1):
        start_upload_time = time.time()
        
        # Mostrar archivo actual que se está subiendo
        print(f"\rSubiendo {i}/{len(pending_files)}: {os.path.basename(filepath)}", end='', flush=True)
        
        if not os.path.exists(filepath):
            print(f"\nArchivo no encontrado: {filepath}")
            update_file_status(connection, file_id, 'error', {'error': 'File not found'})
            failed_uploads += 1
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                print(f"\n\nDemasiados errores consecutivos ({consecutive_errors}). Deteniendo el proceso.")
                break
            continue
        else:
            consecutive_errors = 0  # Reiniciar contador de errores consecutivos
        
        # Subir archivo a Immich
        response = upload_file_to_immich(filepath)
        
        # Calcular tiempo de subida
        upload_time = time.time() - start_upload_time
        file_size = os.path.getsize(filepath)
        speed_mbps = (file_size / upload_time / 1024 / 1024) if upload_time > 0 else 0
        
        # Manejar respuesta
        if response['status_code'] in [200, 201]:  # 200 OK o 201 Created
            # Analizar respuesta para determinar si es duplicado
            try:
                response_data = json.loads(response['response_text']) if response['response_text'] else {}
                if response_data.get('status') == 'duplicate':
                    # Es un duplicado
                    update_file_status(connection, file_id, 'duplicate', response)
                    duplicate_uploads += 1
                    status_msg = f"{Fore.YELLOW}⚠ Duplicado ({response['status_code']}){Style.RESET_ALL}"
                    consecutive_errors = 0  # Reiniciar contador de errores consecutivos
                else:
                    # Es un archivo nuevo subido exitosamente
                    update_file_status(connection, file_id, 'success', response)
                    successful_uploads += 1
                    status_msg = f"{Fore.GREEN}✅ Subido OK ({response['status_code']}) - {upload_time:.2f}s ({speed_mbps:.2f}MB/s){Style.RESET_ALL}"
                    consecutive_errors = 0  # Reiniciar contador de errores consecutivos
            except:
                # Si no se puede parsear JSON, asumir éxito normal
                update_file_status(connection, file_id, 'success', response)
                successful_uploads += 1
                status_msg = f"{Fore.GREEN}✅ Subido OK ({response['status_code']}) - {upload_time:.2f}s ({speed_mbps:.2f}MB/s){Style.RESET_ALL}"
                consecutive_errors = 0  # Reiniciar contador de errores consecutivos
        elif response['status_code'] == 409:  # Conflict - archivo duplicado
            update_file_status(connection, file_id, 'duplicate', response)
            duplicate_uploads += 1
            status_msg = f"{Fore.YELLOW}⚠ Duplicado ({response['status_code']}){Style.RESET_ALL}"
            consecutive_errors = 0  # Reiniciar contador de errores consecutivos
        else:
            # Error en la subida
            update_file_status(connection, file_id, 'error', response)
            failed_uploads += 1
            consecutive_errors += 1
            status_msg = f"{Fore.RED}❌ Error ({response['status_code']}){Style.RESET_ALL}"
            
            # Si hay demasiados errores consecutivos, detener el proceso
            if consecutive_errors >= max_consecutive_errors:
                print(f"\n\nDemasiados errores consecutivos en la API ({consecutive_errors}). Deteniendo el proceso.")
                print(f"Último error: {response.get('response_text', 'Unknown error')[:200]}")
                break
        
        # Limpiar línea y mostrar resultado detallado
        print(f"\r{' ' * 100}")  # Limpiar línea
        print(f"\rSubiendo {i}/{len(pending_files)}: {os.path.basename(filepath)} - {status_msg}")
        
        # Mostrar información de metadatos si están disponibles
        try:
            metadata = json.loads(metadata_str) if metadata_str else {}
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
        
        # Mostrar respuesta de la API si no es exitosa o duplicado
        if response['status_code'] not in [200, 201, 409] and response.get('response_text'):
            print(f"   Respuesta API: {response['response_text'][:100]}{'...' if len(response['response_text']) > 100 else ''}")
        elif response['status_code'] in [200, 201]:
            # Para 200/201, mostrar solo si es un duplicado
            try:
                response_data = json.loads(response['response_text']) if response['response_text'] else {}
                if response_data.get('status') == 'duplicate':
                    print(f"   Detalles: Duplicado - archivo ya existente en Immich")
            except:
                # Si no se puede parsear JSON, no mostrar nada adicional
                pass
        elif response['status_code'] in [200, 201]:
            # Mostrar detalles de la subida exitosa
            # Solo mostrar detalles de velocidad para archivos nuevos, no para duplicados
            try:
                response_data = json.loads(response['response_text']) if response['response_text'] else {}
                if response_data.get('status') != 'duplicate':
                    print(f"   Detalles: {file_size / (1024*1024):.2f}MB en {upload_time:.2f}s a {speed_mbps:.2f}MB/s")
            except:
                # Si no se puede parsear JSON, mostrar detalles normalmente
                print(f"   Detalles: {file_size / (1024*1024):.2f}MB en {upload_time:.2f}s a {speed_mbps:.2f}MB/s")
            
        # Pequeña pausa para no sobrecargar el servidor
        time.sleep(0.1)
    
    total_time = time.time() - start_time
    avg_speed = (successful_uploads + duplicate_uploads) / total_time if total_time > 0 else 0
    
    connection.close()
    print(f"\nResumen de la subida:")
    print(f"- Subidas exitosas: {successful_uploads}")
    print(f"- Duplicados encontrados: {duplicate_uploads}")
    print(f"- Errores: {failed_uploads}")
    print(f"- Tiempo total: {total_time:.2f}s")
    print(f"- Velocidad promedio: {avg_speed:.2f} archivos/s")

if __name__ == "__main__":
    upload_pending_files()