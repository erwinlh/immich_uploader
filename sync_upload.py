#!/usr/bin/env python3
"""
Script combinado para escanear y subir archivos a Immich en un solo proceso
VERSIÓN MEJORADA con logging, conexión persistente y mejor manejo de errores
"""
import os
import json
import signal
import time
from pathlib import Path
from colorama import Fore, Style
from config import (
    SOURCE_DIR, UPLOAD_DELAY, MAX_CONSECUTIVE_ERRORS, UploadStatus
)
from db_manager import DatabaseManager
from immich_client import ImmichClient
from utils import (
    get_file_hash, get_file_type, extract_metadata, format_metadata_display
)
from logger import logger
from progress import ProgressTracker


# Bandera para manejo de interrupciones
interrupted = False


def signal_handler(sig, frame):
    """Manejar señal de interrupción (Ctrl+C)"""
    global interrupted
    interrupted = True
    print("\n\n⚠️  Interrupción detectada. Finalizando de forma segura...")
    logger.info("Proceso interrumpido por el usuario")


def sync_and_upload(threads=1):
    """Escanear directorios y subir archivos en un solo proceso"""
    global interrupted

    logger.info(f"Modo combinado con {threads} hilo(s) para subida")

    # Configurar manejador de señales
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("=" * 60)
    logger.info("Iniciando proceso combinado: Escaneo + Subida")
    logger.info("=" * 60)

    # Conectar a la base de datos
    print("📊 Conectando a la base de datos...")
    try:
        db = DatabaseManager()
    except Exception as e:
        print(f"❌ Error: No se pudo conectar a la base de datos: {str(e)}")
        logger.error(f"Fallo al conectar a la base de datos: {str(e)}")
        return

    # Inicializar cliente de Immich
    print("🌐 Inicializando cliente de Immich...")
    immich = ImmichClient()

    # Verificar conexión con Immich
    print("🔌 Verificando conexión con Immich...")
    if not immich.verify_connection():
        print("❌ Error: No se pudo conectar con el servidor de Immich")
        logger.error("Fallo al verificar conexión con Immich")
        db.close()
        immich.close()
        return

    print("✅ Conexión con Immich verificada\n")

    print(f"📁 Escaneando directorio: {SOURCE_DIR}")
    logger.info(f"Directorio de origen: {SOURCE_DIR}")

    # Obtener lista de archivos con fecha de modificación (en un solo paso)
    files_to_process = []
    print("🔍 Buscando archivos multimedia...")

    file_count = 0
    for root, dirs, files in os.walk(SOURCE_DIR):
        if interrupted:
            break
        for file in files:
            filepath = os.path.join(root, file)
            file_type = get_file_type(filepath)

            if file_type:
                try:
                    # Obtener mtime una sola vez mientras recorremos
                    mtime = os.path.getmtime(filepath)
                    files_to_process.append((filepath, mtime))
                    file_count += 1
                    # Mostrar progreso cada 1000 archivos
                    if file_count % 1000 == 0:
                        print(f"\r   Encontrados: {file_count} archivos...", end='', flush=True)
                except OSError:
                    # Si no podemos leer el archivo, lo saltamos
                    continue

    print(f"\r   Encontrados: {file_count} archivos... ¡Listo!")

    if interrupted:
        print("\n⚠️  Escaneo cancelado por el usuario")
        db.close()
        immich.close()
        return

    # Ordenar por fecha de modificación (ya tenemos los mtimes, no necesitamos leerlos de nuevo)
    print("📋 Ordenando archivos por fecha...")
    files_to_process.sort(key=lambda x: x[1])

    # Extraer solo los paths (ya están ordenados)
    files_to_process = [fp for fp, _ in files_to_process]

    total_files = len(files_to_process)
    print(f"✅ Se encontraron {total_files} archivos multimedia para procesar\n")
    logger.info(f"Total de archivos encontrados: {total_files}")

    if total_files == 0:
        print("ℹ️  No hay archivos para procesar")
        db.close()
        immich.close()
        return

    # Inicializar tracker de progreso
    progress = ProgressTracker(total_files, "Procesando y subiendo")

    consecutive_errors = 0

    # Procesar cada archivo: escanear, poblar DB, intentar subida
    for i, filepath in enumerate(files_to_process, 1):
        if interrupted:
            break

        try:
            filename = os.path.basename(filepath)
            progress.update(filename, 'processing')

            # Verificar existencia
            if not os.path.exists(filepath):
                progress.update(filename, 'error')
                progress.increment_counter('errors')
                consecutive_errors += 1

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"\n\n❌ Demasiados errores consecutivos ({consecutive_errors}). Deteniendo.")
                    logger.error(f"Proceso detenido por {consecutive_errors} errores consecutivos")
                    break
                continue

            # Obtener información del archivo
            path_obj = Path(filepath)
            directory = str(path_obj.parent)
            file_size = os.path.getsize(filepath)
            extension = path_obj.suffix.lower().lstrip('.')

            # Calcular hash
            file_hash = get_file_hash(filepath)
            if not file_hash:
                progress.update(filename, 'error')
                progress.increment_counter('errors')
                consecutive_errors += 1

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"\n\n❌ Demasiados errores consecutivos ({consecutive_errors}). Deteniendo.")
                    logger.error(f"Proceso detenido por {consecutive_errors} errores consecutivos")
                    break
                continue

            # Extraer metadatos
            metadata = extract_metadata(filepath)

            # Insertar o actualizar en DB
            status, file_id = db.insert_or_update_file_record(
                filepath, filename, directory, file_size, file_hash, extension, metadata
            )

            if status is None:
                progress.update(filename, 'error')
                progress.increment_counter('errors')
                consecutive_errors += 1

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"\n\n❌ Demasiados errores consecutivos ({consecutive_errors}). Deteniendo.")
                    logger.error(f"Proceso detenido por {consecutive_errors} errores consecutivos")
                    break
                continue

            # Si ya fue subido previamente, saltar
            if status in [UploadStatus.SUCCESS, UploadStatus.DUPLICATE]:
                progress.update(filename, 'skipped')
                progress.increment_counter('skipped')
                consecutive_errors = 0
                continue

            # Intentar subir a Immich
            start_upload_time = time.time()
            response = immich.upload_file(filepath)
            upload_time = time.time() - start_upload_time

            # Procesar respuesta
            status_code = response['status_code']

            if status_code in [200, 201]:
                # Verificar si es duplicado
                try:
                    response_data = json.loads(response['response_text']) if response['response_text'] else {}
                    if response_data.get('status') == 'duplicate':
                        db.update_file_status(file_id, UploadStatus.DUPLICATE, response)
                        progress.update(filename, 'duplicate')
                        progress.increment_counter('duplicates')
                        consecutive_errors = 0
                    else:
                        db.update_file_status(file_id, UploadStatus.SUCCESS, response)
                        progress.update(filename, 'success', file_size, upload_time)
                        progress.increment_counter('processed')
                        progress.increment_counter('successful')
                        consecutive_errors = 0
                except:
                    db.update_file_status(file_id, UploadStatus.SUCCESS, response)
                    progress.update(filename, 'success', file_size, upload_time)
                    progress.increment_counter('processed')
                    progress.increment_counter('successful')
                    consecutive_errors = 0

            elif status_code == 409:
                db.update_file_status(file_id, UploadStatus.DUPLICATE, response)
                progress.update(filename, 'duplicate')
                progress.increment_counter('duplicates')
                consecutive_errors = 0

            else:
                db.update_file_status(file_id, UploadStatus.ERROR, response)
                progress.update(filename, 'error')
                progress.increment_counter('errors')
                consecutive_errors += 1

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"\n\n❌ Demasiados errores consecutivos ({consecutive_errors}). Deteniendo.")
                    logger.error(f"Proceso detenido por {consecutive_errors} errores consecutivos")
                    logger.error(f"Último error: {response.get('response_text', 'Unknown')[:200]}")
                    break

            # Mostrar metadatos si disponibles y fue exitoso
            if status_code in [200, 201] and metadata:
                try:
                    print(f"\n   📋 {format_metadata_display(metadata)}")
                except:
                    pass

            # Pequeño delay
            time.sleep(UPLOAD_DELAY)

        except Exception as e:
            logger.error(f"Error procesando archivo {filepath}: {str(e)}")
            progress.update(filepath, 'error')
            progress.increment_counter('errors')
            consecutive_errors += 1

            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f"\n\n❌ Demasiados errores consecutivos ({consecutive_errors}). Deteniendo.")
                logger.error(f"Proceso detenido por {consecutive_errors} errores consecutivos")
                break

    # Limpiar línea de progreso
    print()

    # Imprimir resumen
    if interrupted:
        print("\n⚠️  Proceso interrumpido por el usuario")
        logger.info("Proceso interrumpido - resumen parcial")
    else:
        logger.info("Proceso combinado completado exitosamente")

    progress.print_summary()

    # Cerrar conexiones
    db.close()
    immich.close()
    logger.info("Conexiones cerradas")


if __name__ == "__main__":
    sync_and_upload()
