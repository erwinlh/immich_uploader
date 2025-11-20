#!/usr/bin/env python3
"""
Script para subir archivos a Immich desde la base de datos
VERSIÓN MEJORADA con logging, conexión persistente y mejor manejo de errores
Soporta subidas multi-hilo para mejor performance
"""
import os
import json
import signal
import time
import threading
from queue import Queue
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


def upload_worker(worker_id, file_queue, db, progress, results, lock):
    """Worker thread para subir archivos en paralelo"""
    global interrupted

    # Cada worker tiene su propio cliente de Immich
    immich = ImmichClient()
    consecutive_errors = 0

    while not interrupted:
        try:
            # Obtener archivo de la cola
            item = file_queue.get(timeout=1)
            if item is None:  # Señal de terminación
                break

            file_id, filepath, file_hash, metadata_str = item
            filename = os.path.basename(filepath)

            # Verificar que el archivo existe
            if not os.path.exists(filepath):
                logger.warning(f"Archivo no encontrado: {filepath}")
                with lock:
                    db.update_file_status(file_id, UploadStatus.ERROR, {'error': 'File not found'})
                    progress.update(filename, 'error')
                    progress.increment_counter('errors')
                    results['consecutive_errors'] += 1
                file_queue.task_done()
                continue

            # Actualizar progreso
            with lock:
                progress.update(filename, 'processing')

            # Obtener tamaño del archivo
            file_size = os.path.getsize(filepath)

            # Subir archivo a Immich
            start_upload_time = time.time()
            response = immich.upload_file(filepath)
            upload_time = time.time() - start_upload_time

            # Procesar respuesta
            status_code = response['status_code']

            with lock:
                if status_code in [200, 201]:
                    # Verificar si es duplicado
                    try:
                        response_data = json.loads(response['response_text']) if response['response_text'] else {}
                        if response_data.get('status') == 'duplicate':
                            db.update_file_status(file_id, UploadStatus.DUPLICATE, response)
                            progress.update(filename, 'duplicate')
                            progress.increment_counter('duplicates')
                            results['consecutive_errors'] = 0
                        else:
                            db.update_file_status(file_id, UploadStatus.SUCCESS, response)
                            progress.update(filename, 'success', file_size, upload_time)
                            progress.increment_counter('processed')
                            progress.increment_counter('successful')
                            results['consecutive_errors'] = 0
                    except:
                        db.update_file_status(file_id, UploadStatus.SUCCESS, response)
                        progress.update(filename, 'success', file_size, upload_time)
                        progress.increment_counter('processed')
                        progress.increment_counter('successful')
                        results['consecutive_errors'] = 0

                elif status_code == 409:
                    db.update_file_status(file_id, UploadStatus.DUPLICATE, response)
                    progress.update(filename, 'duplicate')
                    progress.increment_counter('duplicates')
                    results['consecutive_errors'] = 0

                else:
                    db.update_file_status(file_id, UploadStatus.ERROR, response)
                    progress.update(filename, 'error')
                    progress.increment_counter('errors')
                    results['consecutive_errors'] += 1

                    if results['consecutive_errors'] >= MAX_CONSECUTIVE_ERRORS:
                        logger.error(f"Proceso detenido por {results['consecutive_errors']} errores consecutivos")
                        logger.error(f"Último error: {response.get('response_text', 'Unknown')[:200]}")
                        results['stop'] = True

            # Pequeño delay para no saturar el servidor
            time.sleep(UPLOAD_DELAY)

        except Exception as e:
            logger.error(f"Error en worker {worker_id}: {str(e)}")
        finally:
            file_queue.task_done()

    immich.close()


def upload_pending_files(threads=1):
    """Subir archivos pendientes a Immich con soporte multi-hilo"""
    global interrupted

    # Configurar manejador de señales
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("=" * 60)
    logger.info(f"Iniciando proceso de subida a Immich ({threads} hilo(s))")
    logger.info("=" * 60)

    # Conectar a la base de datos
    print("📊 Conectando a la base de datos...")
    try:
        db = DatabaseManager()
    except Exception as e:
        print(f"❌ Error: No se pudo conectar a la base de datos: {str(e)}")
        logger.error(f"Fallo al conectar a la base de datos: {str(e)}")
        return

    # Verificar conexión con Immich (solo una vez)
    print("🌐 Verificando conexión con Immich...")
    immich_test = ImmichClient()
    if not immich_test.verify_connection():
        print("❌ Error: No se pudo conectar con el servidor de Immich")
        logger.error("Fallo al verificar conexión con Immich")
        db.close()
        immich_test.close()
        return
    immich_test.close()
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
        return

    # Inicializar tracker de progreso
    progress = ProgressTracker(total_files, "Subiendo")

    # Si solo hay 1 hilo, usar el método original (más simple)
    if threads == 1:
        _upload_sequential(db, pending_files, progress)
    else:
        _upload_parallel(db, pending_files, progress, threads)

    # Cerrar conexión a BD
    db.close()
    logger.info("Conexiones cerradas")


def _upload_sequential(db, pending_files, progress):
    """Subida secuencial (1 hilo) - método original"""
    global interrupted

    immich = ImmichClient()
    consecutive_errors = 0

    for i, (file_id, filepath, file_hash, metadata_str) in enumerate(pending_files, 1):
        if interrupted:
            break

        try:
            filename = os.path.basename(filepath)

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

            progress.update(filename, 'processing')
            file_size = os.path.getsize(filepath)

            start_upload_time = time.time()
            response = immich.upload_file(filepath)
            upload_time = time.time() - start_upload_time

            status_code = response['status_code']

            if status_code in [200, 201]:
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

    print()
    if interrupted:
        print("\n⚠️  Proceso interrumpido por el usuario")
        logger.info("Proceso interrumpido - resumen parcial")
    else:
        logger.info("Subida completada exitosamente")

    progress.print_summary()
    immich.close()


def _upload_parallel(db, pending_files, progress, threads):
    """Subida paralela con múltiples hilos"""
    global interrupted

    # Cola de trabajo y lock para sincronización
    file_queue = Queue()
    lock = threading.Lock()
    results = {'consecutive_errors': 0, 'stop': False}

    # Crear workers
    workers = []
    for i in range(threads):
        worker = threading.Thread(
            target=upload_worker,
            args=(i, file_queue, db, progress, results, lock),
            daemon=True
        )
        worker.start()
        workers.append(worker)

    # Agregar archivos a la cola
    for item in pending_files:
        if interrupted or results['stop']:
            break
        file_queue.put(item)

    # Señal de terminación para los workers
    for _ in range(threads):
        file_queue.put(None)

    # Esperar a que todos los workers terminen
    for worker in workers:
        worker.join()

    print()
    if interrupted:
        print("\n⚠️  Proceso interrumpido por el usuario")
        logger.info("Proceso interrumpido - resumen parcial")
    elif results['stop']:
        print(f"\n\n❌ Demasiados errores consecutivos. Proceso detenido.")
    else:
        logger.info("Subida completada exitosamente")

    progress.print_summary()


if __name__ == "__main__":
    upload_pending_files()
