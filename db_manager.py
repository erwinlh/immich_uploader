#!/usr/bin/env python3
"""
Gestor de base de datos con conexión persistente y pooling
"""
import pymysql
import json
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime
from contextlib import contextmanager
from config import DB_CONFIG, UploadStatus
from logger import logger


class DatabaseManager:
    """Gestor de conexión a base de datos con pooling simple"""

    def __init__(self):
        self.connection = None
        self._connect()

    def _connect(self):
        """Establecer conexión a la base de datos"""
        try:
            self.connection = pymysql.connect(**DB_CONFIG)
            logger.info("Conexión a base de datos establecida")
        except Exception as e:
            logger.error(f"Error conectando a la base de datos: {str(e)}")
            raise

    def ensure_connection(self):
        """Verificar y restablecer conexión si es necesario"""
        try:
            if self.connection is None:
                self._connect()
            else:
                # Ping para verificar que la conexión está activa
                self.connection.ping(reconnect=True)
        except Exception as e:
            logger.warning(f"Conexión perdida, reconectando: {str(e)}")
            self._connect()

    @contextmanager
    def get_cursor(self):
        """Context manager para obtener cursor con manejo automático"""
        self.ensure_connection()
        cursor = self.connection.cursor()
        try:
            yield cursor
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            logger.error(f"Error en transacción de base de datos: {str(e)}")
            raise
        finally:
            cursor.close()

    def insert_file_record(
        self,
        filepath: str,
        filename: str,
        directory: str,
        file_size: int,
        file_hash: str,
        extension: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """Insertar nuevo registro de archivo en la base de datos"""
        with self.get_cursor() as cursor:
            try:
                # Verificar si el archivo ya existe
                query = "SELECT id FROM media_files WHERE filepath = %s"
                cursor.execute(query, (filepath,))
                result = cursor.fetchone()

                if result:
                    logger.debug(f"Archivo ya existe en DB: {filepath}")
                    return True

                # Insertar nuevo registro
                metadata_json = json.dumps(metadata)
                query = """
                INSERT INTO media_files
                (filepath, filename, directory, file_size, hash, extension, metadata_info)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(
                    query,
                    (filepath, filename, directory, file_size, file_hash, extension, metadata_json)
                )
                logger.debug(f"Archivo insertado en DB: {filepath}")
                return True

            except Exception as e:
                logger.error(f"Error insertando registro para {filepath}: {str(e)}")
                return False

    def insert_or_update_file_record(
        self,
        filepath: str,
        filename: str,
        directory: str,
        file_size: int,
        file_hash: str,
        extension: str,
        metadata: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[int]]:
        """
        Insertar o actualizar registro de archivo
        Retorna (status, file_id)
        """
        with self.get_cursor() as cursor:
            try:
                # Verificar si el archivo ya existe
                query = "SELECT id, upload_status FROM media_files WHERE filepath = %s"
                cursor.execute(query, (filepath,))
                result = cursor.fetchone()

                metadata_json = json.dumps(metadata)

                if result:
                    file_id, current_status = result
                    if current_status in [UploadStatus.SUCCESS, UploadStatus.DUPLICATE]:
                        logger.debug(f"Archivo ya subido previamente: {filepath}")
                        return current_status, file_id
                    else:
                        # Actualizar registro existente
                        query = """
                        UPDATE media_files
                        SET filename=%s, directory=%s, file_size=%s, hash=%s,
                            extension=%s, metadata_info=%s
                        WHERE filepath = %s
                        """
                        cursor.execute(
                            query,
                            (filename, directory, file_size, file_hash, extension, metadata_json, filepath)
                        )
                        logger.debug(f"Registro actualizado: {filepath}")
                        return UploadStatus.PENDING, file_id

                # Insertar nuevo registro
                query = """
                INSERT INTO media_files
                (filepath, filename, directory, file_size, hash, extension, metadata_info)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(
                    query,
                    (filepath, filename, directory, file_size, file_hash, extension, metadata_json)
                )
                file_id = cursor.lastrowid
                logger.debug(f"Nuevo registro insertado: {filepath}")
                return UploadStatus.PENDING, file_id

            except Exception as e:
                logger.error(f"Error insertando/actualizando registro para {filepath}: {str(e)}")
                return None, None

    def update_file_status(
        self,
        file_id: int,
        status: str,
        api_response: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Actualizar el estado de un archivo en la base de datos"""
        with self.get_cursor() as cursor:
            try:
                query = """
                UPDATE media_files
                SET upload_status = %s, api_response = %s, upload_date = NOW()
                WHERE id = %s
                """
                cursor.execute(
                    query,
                    (status, json.dumps(api_response) if api_response else None, file_id)
                )
                logger.debug(f"Estado actualizado para ID {file_id}: {status}")
                return True

            except Exception as e:
                logger.error(f"Error actualizando estado para ID {file_id}: {str(e)}")
                return False

    def get_pending_files(self) -> List[Tuple[int, str, str, str]]:
        """
        Obtener archivos pendientes de subida ordenados por fecha de captura
        Retorna lista de (id, filepath, hash, metadata_info)
        """
        with self.get_cursor() as cursor:
            try:
                query = """
                SELECT id, filepath, hash, metadata_info
                FROM media_files
                WHERE upload_status IN (%s, %s)
                """
                cursor.execute(query, (UploadStatus.PENDING, UploadStatus.ERROR))
                results = cursor.fetchall()

                # Ordenar por fecha de captura (más nuevo primero)
                def extract_capture_time(row):
                    try:
                        metadata = json.loads(row[3]) if row[3] else {}
                        date_taken = metadata.get('date_taken', None)

                        if date_taken:
                            try:
                                dt = datetime.strptime(date_taken, "%Y:%m:%d %H:%M:%S")
                                return dt.timestamp()
                            except ValueError:
                                try:
                                    dt = datetime.strptime(date_taken.split('.')[0], "%Y:%m:%d %H:%M:%S")
                                    return dt.timestamp()
                                except ValueError:
                                    pass

                        # Fallback a modified_time
                        return metadata.get('modified_time', 0)
                    except:
                        return 0

                results = sorted(results, key=extract_capture_time, reverse=True)
                logger.info(f"Encontrados {len(results)} archivos pendientes")
                return results

            except Exception as e:
                logger.error(f"Error obteniendo archivos pendientes: {str(e)}")
                return []

    def get_stats(self) -> Dict[str, int]:
        """Obtener estadísticas de la base de datos"""
        with self.get_cursor() as cursor:
            try:
                stats = {}

                # Contar por estado
                cursor.execute("SELECT upload_status, COUNT(*) FROM media_files GROUP BY upload_status")
                for status, count in cursor.fetchall():
                    stats[status] = count

                # Total
                cursor.execute("SELECT COUNT(*) FROM media_files")
                stats['total'] = cursor.fetchone()[0]

                # Pendientes para subir
                cursor.execute(
                    "SELECT COUNT(*) FROM media_files WHERE upload_status IN (%s, %s)",
                    (UploadStatus.PENDING, UploadStatus.ERROR)
                )
                stats['pending_upload'] = cursor.fetchone()[0]

                # Archivos con metadatos
                cursor.execute(
                    "SELECT COUNT(*) FROM media_files WHERE metadata_info IS NOT NULL AND metadata_info != 'null'"
                )
                stats['with_metadata'] = cursor.fetchone()[0]

                return stats

            except Exception as e:
                logger.error(f"Error obteniendo estadísticas: {str(e)}")
                return {}

    def close(self):
        """Cerrar conexión a la base de datos"""
        if self.connection:
            try:
                self.connection.close()
                logger.info("Conexión a base de datos cerrada")
            except Exception as e:
                logger.error(f"Error cerrando conexión: {str(e)}")
