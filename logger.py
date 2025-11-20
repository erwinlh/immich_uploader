#!/usr/bin/env python3
"""
Sistema de logging centralizado
"""
import logging
import os
from pathlib import Path
from config import LOG_LEVEL, LOG_FILE, LOG_FORMAT, LOG_DATE_FORMAT

def setup_logger(name='immich_uploader'):
    """
    Configurar logger con salida a archivo y consola
    """
    # Crear directorio de logs si no existe
    log_dir = Path(LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # Crear logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL))

    # Evitar duplicar handlers si ya existen
    if logger.handlers:
        return logger

    # Formato
    formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)

    # Handler para archivo
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Handler para consola (solo WARNING y superiores)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

# Logger global
logger = setup_logger()
