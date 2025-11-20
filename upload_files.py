#!/usr/bin/env python3
"""
Script para subir archivos a Immich desde la base de datos
VERSIÓN MEJORADA con logging, conexión persistente y mejor manejo de errores
"""
import os
import json
import signal
import time
from colorama import Fore, Style
from config import UPLOAD_DELAY, MAX_CONSECUTIVE_ERRORS, UploadStatus
from db_manager import DatabaseManager
from immich_client import ImmichClient
from utils import format_metadata_display
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


def upload_pending_files():
    """Subir archivos pendientes a Immich"""
    global interrupted

    # Configurar manejador de señales
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("=" * 60)
    logger.info("Iniciando proceso de subida a Immich")
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

    # Obtener archivos pendientes
    print("🔍 Obteniendo archivos pendientes...")
    pending_files = db.get_pending_files()
    total_files = len(pending_files)

    print(f"📦 Se encontraron {total_files} archivos pendientes para subir\n")
    logger.info(f"Total de archivos pendientes: {total_files}")

    if total_files == 0:
        print("ℹ️  No hay archivos pendientes para subir")
        db.close()
        immich.close()
        return

    # Inicializar tracker de progreso
    progress = ProgressTracker(total_files, "Subiendo")

    consecutive_errors = 0

    # Subir archivos
    for i, (file_id, filepath, file_hash, metadata_str) in enumerate(pending_files, 1):
        if interrupted:
            break

        try:
            filename = os.path.basename(filepath)

            # Verificar que el archivo existe
            if not os.path.exists(filepath):
                logger.warning(f"Archivo no encontrado: {filepath}")
                db.update_file_status(file_id, UploadStatus.ERROR, {'error': 'File not found'})
                progress.update(filename, 'error')
                progress.increment_counter('errors')
                consecutive_errors += 1

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"\n\n❌ Demasiados errores consecutivos ({consecutive_errors}). Deteniendo.")
                    logger.error(f"Proceso detenido por {consecutive_errors} errores consecutivos")
                    break
                continue

            # Actualizar progreso
            progress.update(filename, 'processing')

            # Obtener tamaño del archivo
            file_size = os.path.getsize(filepath)

            # Subir archivo a Immich
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
                    # Si no se puede parsear, asumir éxito
                    db.update_file_status(file_id, UploadStatus.SUCCESS, response)
                    progress.update(filename, 'success', file_size, upload_time)
                    progress.increment_counter('processed')
                    progress.increment_counter('successful')
                    consecutive_errors = 0

            elif status_code == 409:
                # Duplicado
                db.update_file_status(file_id, UploadStatus.DUPLICATE, response)
                progress.update(filename, 'duplicate')
                progress.increment_counter('duplicates')
                consecutive_errors = 0

            else:
                # Error
                db.update_file_status(file_id, UploadStatus.ERROR, response)
                progress.update(filename, 'error')
                progress.increment_counter('errors')
                consecutive_errors += 1

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"\n\n❌ Demasiados errores consecutivos ({consecutive_errors}). Deteniendo.")
                    logger.error(f"Proceso detenido por {consecutive_errors} errores consecutivos")
                    logger.error(f"Último error: {response.get('response_text', 'Unknown')[:200]}")
                    break

            # Mostrar metadatos en la siguiente línea si están disponibles
            if metadata_str and status_code in [200, 201]:
                try:
                    metadata = json.loads(metadata_str)
                    print(f"\n   📋 {format_metadata_display(metadata)}")
                except:
                    pass

            # Pequeño delay para no saturar el servidor
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
        logger.info("Subida completada exitosamente")

    progress.print_summary()

    # Cerrar conexiones
    db.close()
    immich.close()
    logger.info("Conexiones cerradas")


if __name__ == "__main__":
    upload_pending_files()
