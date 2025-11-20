# Changelog - Immich Uploader

## v2.0 - Refactorización Mayor (2025-11-20)

### 🎉 Nuevas Características

- **Arquitectura modular**: Código separado en módulos especializados
  - `config.py`: Configuración centralizada
  - `logger.py`: Sistema de logging estructurado
  - `db_manager.py`: Gestor de base de datos con conexión persistente
  - `immich_client.py`: Cliente HTTP para API de Immich
  - `utils.py`: Utilidades compartidas
  - `progress.py`: Sistema de progreso mejorado

- **Manejo de interrupciones**: Ctrl+C ahora cierra conexiones limpiamente
- **Logging a archivo**: Todos los eventos se registran en `logs/immich_uploader.log`
- **Verificación de conexión**: Valida conectividad con Immich antes de iniciar
- **Progreso mejorado**: ETA, porcentaje, velocidad de transferencia, colores

### ⚡ Mejoras de Performance

- **Conexión DB persistente**: Una sola conexión reutilizada con auto-reconexión
- **Sesión HTTP reutilizable**: requests.Session para reducir overhead de conexiones
- **Configuración optimizada**: Variables de entorno cargadas una sola vez

### 🐛 Correcciones

- Rutas hardcodeadas eliminadas (ahora usa rutas relativas)
- Manejo robusto de errores de conexión
- Metadata display mejorado para archivos sin EXIF

### 📝 Cambios de Configuración

Nuevas variables opcionales en `.env`:
```
MAX_CONSECUTIVE_ERRORS=5
UPLOAD_DELAY=0.1
HASH_CHUNK_SIZE=4096
LOG_LEVEL=INFO
LOG_FILE=logs/immich_uploader.log
```

### 🔄 Migración desde v1.0

1. Hacer backup de tu `.env` actual
2. Los scripts anteriores están en `backup/` por seguridad
3. Instalar nuevas dependencias: `pip install -r requirements.txt`
4. El programa es **retrocompatible** - la base de datos no necesita cambios
5. Simplemente ejecuta `python main.py` como siempre

### 📦 Dependencias Actualizadas

- Añadido: `Pillow>=10.0.0` (antes implícito)
- Añadido: `ExifRead>=3.0.0` (antes implícito)
- Removido: `tqdm` (reemplazado por sistema de progreso custom)

## v1.0 - Versión Inicial

- Escaneo de archivos multimedia
- Cálculo de hash SHA-256
- Extracción de metadatos EXIF
- Subida a Immich con detección de duplicados
- Menú interactivo
- Base de datos MySQL para seguimiento
