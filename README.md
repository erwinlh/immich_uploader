# Gestor de Subida a Immich v2.0

Este proyecto permite subir fotos y videos a Immich de forma organizada, manteniendo un registro de estado y permitiendo continuar desde donde se dejó.

**⚠️ IMPORTANTE:** Versión 2.0 completamente refactorizada con arquitectura modular, logging estructurado, y mejor manejo de errores. El código v1.0 está respaldado en `/backup/`.

## Características v2.0

### Nuevas Características
- ✅ **Arquitectura modular**: Código organizado en módulos especializados (db_manager, immich_client, utils, progress, logger, config)
- ✅ **Logging estructurado**: Todos los eventos se registran en `logs/immich_uploader.log` con timestamps
- ✅ **Conexión DB persistente**: Una única conexión reutilizable con auto-reconexión
- ✅ **Manejo de interrupciones**: Ctrl+C cierra conexiones limpiamente y muestra resumen parcial
- ✅ **Menú de diagnóstico**: Opción 5 prueba múltiples endpoints para identificar versión de API de Immich
- ✅ **Timestamps en progreso**: Cada línea muestra `[HH:MM:SS]` para seguimiento temporal
- ✅ **Optimización de escaneo**: Pre-carga mtimes para ordenación rápida (de minutos a segundos)
- ✅ **Progreso mejorado**: ETA, velocidad, porcentaje, colores, y resumen detallado

### Características Heredadas
- Escanea directorios recursivamente para encontrar fotos y videos
- Calcula hash SHA-256 de cada archivo para detectar duplicados
- Mantiene registro en MySQL del estado de cada archivo
- Reanudable: retoma desde donde se dejó tras interrupciones
- Extrae y almacena metadatos EXIF (cámara, lente, exposición, GPS, dimensiones)
- Detecta automáticamente archivos ya subidos (duplicados)
- Modo combinado: escanea y sube en un solo proceso (recomendado)
- Manejo inteligente de errores: detiene tras N errores consecutivos (configurable)
- Visualización con colores: ✅ éxito, ⚠️ duplicado/saltado, ❌ error
- Compatible con versiones antiguas de Immich (usa `/asset/upload`)

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

### Menú Interactivo (Recomendado)

```bash
source venv/bin/activate
python main.py
```

**Opciones del menú:**
1. **Escanear directorios** - Solo escanea y registra archivos en BD
2. **Subir archivos pendientes** - Solo sube lo que está marcado como pendiente
3. **Mostrar resumen** - Estadísticas de la base de datos
4. **Modo combinado** - Escanea y sube en un solo proceso ⭐ **RECOMENDADO**
5. **Diagnóstico** - Verifica conectividad con Immich y prueba endpoints
6. **Salir**

### Scripts Individuales

```bash
# Solo escanear
python scan_files.py

# Solo subir pendientes
python upload_files.py

# Escanear y subir (equivalente a opción 4)
python sync_upload.py
```

## Estructura del Proyecto v2.0

### Scripts Principales
- **`main.py`** - Menú interactivo con 6 opciones
- **`scan_files.py`** - Escanea y registra archivos en BD
- **`upload_files.py`** - Sube archivos pendientes
- **`sync_upload.py`** - Modo combinado: escanea + sube

### Módulos Core (v2.0)
- **`config.py`** - Configuración centralizada desde .env
- **`logger.py`** - Logging estructurado a archivo
- **`db_manager.py`** - Gestor de BD con conexión persistente
- **`immich_client.py`** - Cliente HTTP para API de Immich
- **`utils.py`** - Utilidades (hash, metadata, formato)
- **`progress.py`** - Sistema de progreso con ETA y métricas

### Otros Archivos
- **`requirements.txt`** - Dependencias Python
- **`CLAUDE.md`** - Documentación para Claude Code
- **`CHANGELOG.md`** - Historial de cambios v1.0 → v2.0
- **`backup/`** - Código original v1.0

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

## Configuración Avanzada (v2.0)

Variables opcionales en `.env`:

```bash
# Límites y performance
MAX_CONSECUTIVE_ERRORS=5        # Detener tras N errores consecutivos
UPLOAD_DELAY=0.1                # Segundos entre uploads
HASH_CHUNK_SIZE=4096            # Bytes para cálculo de hash

# Logging
LOG_LEVEL=INFO                  # DEBUG, INFO, WARNING, ERROR
LOG_FILE=logs/immich_uploader.log
```

## Solución de Problemas

### 1. Verificar Logs
```bash
tail -f logs/immich_uploader.log
```

### 2. Diagnóstico de Conexión
Usa la **Opción 5** del menú para verificar endpoints.

### 3. Problema con MySQL
Verifica que el servicio esté corriendo:

```bash
mysql -u root -e "SHOW DATABASES;"
```

Recrea la base de datos si es necesario:

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

### 4. Archivos en iCloud Drive
⚠️ **IMPORTANTE**: Si tus archivos están en iCloud Drive con "Optimizar almacenamiento", el sistema descargará archivos bajo demanda, lo que puede ralentizar el proceso significativamente.

**Soluciones:**
- Descarga todos los archivos localmente antes de ejecutar el script
- Usa `brctl download /ruta/a/carpeta` para forzar descarga desde iCloud
- Considera mover archivos a almacenamiento local durante la migración

### 5. Endpoint Incorrecto (404 errores)
Si los uploads fallan con 404, tu versión de Immich usa una API diferente.

**Solución:**
1. Ejecuta **Opción 5** (Diagnóstico) del menú
2. Identifica qué endpoint responde (ej: `/asset/upload`)
3. El código ya está configurado para `/asset/upload` (versiones antiguas)

## Changelog v2.0

Ver `CHANGELOG.md` para detalles completos de cambios entre v1.0 y v2.0.

**Mejoras principales:**
- 🏗️ Arquitectura modular (6 módulos nuevos)
- 📝 Logging a archivo con timestamps
- 🔌 Conexión DB persistente con auto-reconexión
- ⚡ Optimización de escaneo (107K archivos: de ~5min a ~30s)
- 🎯 Menú de diagnóstico para troubleshooting
- ⏱️ Timestamps en progreso y resumen detallado
- 🛑 Manejo limpio de interrupciones (Ctrl+C)

## Repositorio

GitHub: `git@github.com:erwinlh/immich_uploader.git`

```bash
git clone git@github.com:erwinlh/immich_uploader.git
cd immich_uploader
```

## Licencia

Proyecto personal para migración a Immich.