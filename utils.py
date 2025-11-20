#!/usr/bin/env python3
"""
Utilidades compartidas para procesamiento de archivos
"""
import hashlib
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
import exifread
from PIL import Image
from config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, HASH_CHUNK_SIZE
from logger import logger


def get_file_hash(filepath: str) -> Optional[str]:
    """Calcular hash SHA-256 de un archivo"""
    hash_sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    except Exception as e:
        logger.error(f"Error calculando hash para {filepath}: {str(e)}")
        return None


def get_file_type(filepath: str) -> Optional[str]:
    """Determinar si es imagen o video basado en la extensión"""
    ext = Path(filepath).suffix.lower().lstrip('.')
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    elif ext in VIDEO_EXTENSIONS:
        return 'video'
    return None


def extract_metadata(filepath: str) -> Dict[str, Any]:
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
            try:
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
                    if 'EXIF ISOSpeedRatings' in tags:
                        metadata['iso'] = str(tags['EXIF ISOSpeedRatings']).strip()
                    if 'EXIF FocalLength' in tags:
                        metadata['focal_length'] = str(tags['EXIF FocalLength']).strip()
                    if 'EXIF Flash' in tags:
                        metadata['flash'] = str(tags['EXIF Flash']).strip()
                    if 'GPS GPSLatitude' in tags:
                        metadata['gps_latitude'] = str(tags['GPS GPSLatitude']).strip()
                    if 'GPS GPSLongitude' in tags:
                        metadata['gps_longitude'] = str(tags['GPS GPSLongitude']).strip()
            except Exception as e:
                logger.debug(f"No se pudieron extraer metadatos EXIF de {filepath}: {str(e)}")

        # Obtener dimensiones si es una imagen
        if ext in ['.jpg', '.jpeg', '.tiff', '.tif', '.png', '.webp', '.bmp']:
            try:
                with Image.open(filepath) as img:
                    metadata['image_width'], metadata['image_height'] = img.size
                    metadata['image_mode'] = img.mode
            except Exception as e:
                logger.debug(f"No se pudieron extraer dimensiones de {filepath}: {str(e)}")

    except Exception as e:
        logger.error(f"Error leyendo metadatos de {filepath}: {str(e)}")
        metadata['error'] = str(e)

    return metadata


def format_metadata_display(metadata: Dict[str, Any]) -> str:
    """Formatear metadatos para visualización"""
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

    # Configuración de disparo
    config_parts = []

    if 'f_number' in metadata:
        f_val = str(metadata['f_number'])
        if f_val.startswith("FNumber "):
            f_val = f_val[8:]
        elif f_val.startswith("f/"):
            f_val = f_val[2:]
        config_parts.append(f"f/{f_val}")

    if 'exposure_time' in metadata:
        exp_val = str(metadata['exposure_time'])
        if exp_val.startswith("ExposureTime "):
            exp_val = exp_val[13:]
        config_parts.append(exp_val)

    if 'iso' in metadata:
        iso_val = str(metadata['iso'])
        if iso_val.startswith("ISOSpeedRatings "):
            iso_val = iso_val[16:]
        elif iso_val.startswith("ISO"):
            iso_val = iso_val[3:]
        config_parts.append(f"ISO{iso_val}")

    if config_parts:
        meta_parts.append(f"Config: {', '.join(config_parts)}")
    else:
        meta_parts.append("Config: N/A")

    return ', '.join(meta_parts)


def format_size(bytes_size: int) -> str:
    """Formatear tamaño de archivo de forma legible"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f}{unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f}PB"


def format_time(seconds: float) -> str:
    """Formatear tiempo de forma legible"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
