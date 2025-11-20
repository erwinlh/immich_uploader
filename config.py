#!/usr/bin/env python3
"""
Configuración centralizada para el Immich Uploader
"""
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de Immich
IMMICH_URL = os.getenv('IMMICH_URL')
IMMICH_API_KEY = os.getenv('IMMICH_API_KEY')

# Configuración de la base de datos
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'immich_uploader'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'charset': 'utf8mb4',
    'autocommit': False,
}

# Directorio de origen
SOURCE_DIR = os.getenv('SOURCE_DIR', '/Users/erwin/Desktop/desde-nas')

# Extensiones permitidas
IMAGE_EXTENSIONS = set(
    os.getenv('IMAGE_EXTENSIONS', 'jpg,jpeg,png,webp,tiff,tif,bmp,heic,heif')
    .lower()
    .split(',')
)
VIDEO_EXTENSIONS = set(
    os.getenv('VIDEO_EXTENSIONS', 'mp4,mov,avi,mkv,wmv,flv,webm,m4v')
    .lower()
    .split(',')
)

# Configuración de procesamiento
MAX_CONSECUTIVE_ERRORS = int(os.getenv('MAX_CONSECUTIVE_ERRORS', '5'))
UPLOAD_DELAY = float(os.getenv('UPLOAD_DELAY', '0.1'))  # segundos
HASH_CHUNK_SIZE = int(os.getenv('HASH_CHUNK_SIZE', '4096'))  # bytes

# Configuración de logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'logs/immich_uploader.log')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Rutas de archivos
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_FILE = os.path.join(SCRIPT_DIR, 'ansi-logo.utf.ans')

# Estados de upload
class UploadStatus:
    PENDING = 'pending'
    SUCCESS = 'success'
    DUPLICATE = 'duplicate'
    ERROR = 'error'
