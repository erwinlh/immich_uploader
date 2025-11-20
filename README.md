# Gestor de Subida a Immich

Este proyecto permite subir fotos y videos a Immich de forma organizada, manteniendo un registro de estado y permitiendo continuar desde donde se dejó.

## Características

- Escanea directorios recursivamente para encontrar fotos y videos
- Calcula hash SHA-256 de cada archivo para detectar duplicados
- Mantiene un registro en base de datos del estado de cada archivo
- Permite subir archivos de forma continua, retomando desde donde se dejó
- Registra respuestas de la API de Immich
- Detecta archivos ya subidos (duplicados)
- Muestra en tiempo real el archivo que se está procesando durante el escaneo
- Muestra en tiempo real el archivo que se está subiendo durante la subida
- Muestra estadísticas de velocidad durante ambos procesos
- Muestra detalles de la respuesta de la API durante la subida
- Muestra tiempos de procesamiento y velocidades de subida
- Extrae y almacena metadatos de imágenes (EXIF, dimensiones, etc.)
- Verifica que los metadatos se preservan durante la subida
- Modo combinado: escanea y sube en un solo proceso (recomendado)
- Verifica estado previo antes de intentar subir archivos ya procesados
- Manejo inteligente de errores: detiene el proceso tras varios errores consecutivos
- Utiliza el endpoint correcto de la API de Immich
- Visualización con colores y emojis: verde para éxito (✅), naranja para duplicados (⚠), rojo para errores (❌)
- Muestra información detallada de cámara, lente y configuración de disparo desde los metadatos EXIF
- Procesa archivos ordenados por fecha de captura o modificación (de más nuevo a más antiguo)
- Maneja adecuadamente archivos sin metadatos EXIF, mostrando "N/A" cuando no están disponibles

## Requisitos

- Python 3.7+
- MySQL
- Servidor Immich con API habilitada

## Instalación

1. **Preparar el entorno virtual:**

```bash
cd /ruta/al/proyecto
python3 -m venv venv
source venv/bin/activate
```

2. **Instalar dependencias:**

```bash
pip install -r requirements.txt
```

3. **Configurar variables de entorno:**

El archivo `.env` ya está configurado con tus datos. Verifica que tenga la siguiente información:

```env
# Configuración de Immich
IMMICH_URL=http://100.87.51.69:30041
IMMICH_API_KEY=npU7APfQ3PFrtJJo7yNXrtyE5clzWRJsO6EVdpRgAY

# Configuración de la base de datos MySQL
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=
DB_NAME=immich_uploader
DB_PORT=3306

# Directorio de origen de las fotos
SOURCE_DIR=/Users/erwin/Desktop/desde-nas

# Extensiones de archivos a procesar
IMAGE_EXTENSIONS=jpg,jpeg,png,webp,tiff,tif,bmp,heic,heif
VIDEO_EXTENSIONS=mp4,mov,avi,mkv,wmv,flv,webm,m4v
```

## Uso

### Método 1: Usar el menú interactivo

```bash
source venv/bin/activate
python main.py
```

### Método 2: Ejecutar scripts individuales

1. **Escanear y poblar base de datos:**

```bash
source venv/bin/activate
python scan_files.py
```

2. **Subir archivos pendientes:**

```bash
source venv/bin/activate
python upload_files.py
```

## Scripts

- `scan_files.py`: Escanea el directorio fuente y registra los archivos en la base de datos
- `upload_files.py`: Sube los archivos pendientes a Immich
- `sync_upload.py`: Escanea y sube en un solo proceso (recomendado)
- `main.py`: Menú interactivo para gestionar todo el proceso
- `requirements.txt`: Dependencias del proyecto

## Estructura de la base de datos

La tabla `media_files` contiene:

- `id`: Identificador único
- `filepath`: Ruta completa del archivo
- `filename`: Nombre del archivo
- `directory`: Directorio del archivo
- `file_size`: Tamaño en bytes
- `hash`: Hash SHA-256 del archivo
- `extension`: Extensión del archivo
- `upload_status`: Estado (pending, success, duplicate, error)
- `api_response`: Respuesta de la API de Immich
- `upload_date`: Fecha de subida
- `created_at`: Fecha de registro en DB
- `updated_at`: Última actualización

## Flujo de trabajo

1. Ejecutar `scan_files.py` para detectar y registrar todos los archivos multimedia
2. Ejecutar `upload_files.py` para subir los archivos pendientes a Immich
3. El sistema retiene el estado, por lo que puede interrumpirse y reanudarse

## Estados de subida

- `pending`: Archivo detectado pero no subido aún
- `success`: Archivo subido exitosamente
- `duplicate`: El archivo ya existe en Immich
- `error`: Error durante la subida

## Notas

- El script detecta automáticamente archivos ya subidos basándose en el hash SHA-256
- Se recomienda hacer backup de la base de datos periódicamente
- El sistema maneja archivos grandes mediante lectura en bloques
- Cada subida tiene un pequeño delay para no sobrecargar el servidor

## Solución de problemas

Si experimentas problemas con la base de datos, verifica que el servicio MySQL esté corriendo:

```bash
mysql -u root -e "SHOW DATABASES;"
```

Si el problema persiste, recrea la base de datos:

```bash
mysql -u root -e "DROP DATABASE IF EXISTS immich_uploader; CREATE DATABASE immich_uploader;"
mysql -u root -e "
USE immich_uploader;
CREATE TABLE IF NOT EXISTS media_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filepath VARCHAR(1000) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    directory VARCHAR(745),
    file_size BIGINT,
    hash VARCHAR(64) NOT NULL,
    extension VARCHAR(10),
    upload_status ENUM('pending', 'success', 'duplicate', 'error') DEFAULT 'pending',
    api_response TEXT,
    upload_date TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_filepath (filepath(255)),
    INDEX idx_hash (hash),
    INDEX idx_status (upload_status),
    UNIQUE KEY uk_filepath (filepath(768))
);"
```