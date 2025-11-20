#!/usr/bin/env python3
"""
Script para escanear directorios y poblar la base de datos con información de archivos
VERSIÓN MEJORADA con logging, conexión DB persistente y mejor manejo de errores
"""
import os
import signal
import sys
from pathlib import Path
from config import SOURCE_DIR, MAX_CONSECUTIVE_ERRORS
from db_manager import DatabaseManager
from utils import get_file_hash, get_file_type, extract_metadata
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


def scan_and_populate_db():
    """Escanear directorios y poblar la base de datos"""
    global interrupted

    # Configurar manejador de señales
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("=" * 60)
    logger.info("Iniciando escaneo de archivos")
    logger.info("=" * 60)

    # Conectar a la base de datos
    print("📊 Conectando a la base de datos...")
    try:
        db = DatabaseManager()
    except Exception as e:
        print(f"❌ Error: No se pudo conectar a la base de datos: {str(e)}")
        logger.error(f"Fallo al conectar a la base de datos: {str(e)}")
        return

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

            if file_type:  # Es imagen o video
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
        return

    # Inicializar tracker de progreso
    progress = ProgressTracker(total_files, "Escaneando")

    consecutive_errors = 0

    # Procesar archivos
    for i, filepath in enumerate(files_to_process, 1):
        if interrupted:
            break

        try:
            filename = os.path.basename(filepath)
            progress.update(filename, 'processing')

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
            else:
                consecutive_errors = 0

            # Extraer metadatos
            metadata = extract_metadata(filepath)

            # Insertar en la base de datos
            if db.insert_file_record(
                filepath, filename, directory, file_size, file_hash, extension, metadata
            ):
                progress.update(filename, 'success')
                progress.increment_counter('processed')
                progress.increment_counter('successful')
            else:
                progress.update(filename, 'error')
                progress.increment_counter('errors')
                consecutive_errors += 1

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"\n\n❌ Demasiados errores consecutivos ({consecutive_errors}). Deteniendo.")
                    logger.error(f"Proceso detenido por {consecutive_errors} errores consecutivos")
                    break

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
        logger.info("Escaneo completado exitosamente")

    progress.print_summary()

    # Cerrar conexión
    db.close()
    logger.info("Conexión a base de datos cerrada")


if __name__ == "__main__":
    scan_and_populate_db()
