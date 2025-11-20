# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Immich uploader tool that scans directories for media files (photos and videos), tracks them in a MySQL database, and uploads them to an Immich server. The system maintains upload state, handles duplicates via SHA-256 hashing, extracts EXIF metadata, and provides detailed progress reporting with colored output.

## Core Commands

### Development Environment Setup

```bash
# Activate virtual environment (always required before running scripts)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application

```bash
# Interactive menu (recommended entry point)
python main.py

# Individual scripts
python scan_files.py         # Scan and populate database only
python upload_files.py       # Upload pending files only
python sync_upload.py        # Scan and upload in one process (recommended)
```

### Database Management

```bash
# Check MySQL service
mysql -u root -e "SHOW DATABASES;"

# Recreate database from scratch
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

## Architecture

### Module Organization (REFACTORED - v2.0)

**Core Modules:**
- **config.py**: Centralized configuration from environment variables
- **logger.py**: Structured logging to file and console
- **db_manager.py**: Database manager with persistent connection and auto-reconnect
- **immich_client.py**: Immich API client with session management
- **utils.py**: Shared utilities (hashing, metadata extraction, formatting)
- **progress.py**: Progress tracking with ETA, speed metrics, and colored output

**Scripts:**
- **main.py**: Interactive CLI menu coordinator
- **scan_files.py**: File discovery and database population (uses new modules)
- **upload_files.py**: Upload pending files (uses new modules)
- **sync_upload.py**: Combined scan+upload workflow (recommended)

### Data Flow

1. **Scanning Phase** (`scan_files.py`):
   - Recursively walks SOURCE_DIR for files matching IMAGE_EXTENSIONS or VIDEO_EXTENSIONS
   - Calculates SHA-256 hash in 4KB chunks for memory efficiency
   - Extracts EXIF metadata (camera, lens, exposure settings, GPS, dimensions) using exifread and PIL
   - Stores file records in MySQL with status='pending'
   - Skips files already in database

2. **Upload Phase** (`upload_files.py`):
   - Queries database for files with status='pending' or 'error'
   - Sorts by capture date (date_taken from EXIF) or modified_time, newest first
   - POSTs to `/api/assets` endpoint with multipart form data
   - Updates status to 'success', 'duplicate', or 'error' based on API response
   - Implements consecutive error detection (stops after 5 consecutive failures)

3. **Sync Mode** (`sync_upload.py`):
   - Combines scanning and uploading in one pass
   - Checks upload_status before attempting upload (skips 'success'/'duplicate' files)
   - Reduces database round-trips and provides immediate feedback

### Database Schema

The `media_files` table uses:
- `filepath` (VARCHAR 1000): Unique constraint for deduplication
- `hash` (VARCHAR 64): SHA-256 for content-based duplicate detection
- `upload_status` (ENUM): Tracks lifecycle ('pending', 'success', 'duplicate', 'error')
- `metadata_info` (TEXT/JSON): Stores extracted EXIF data (camera_make, camera_model, lens_model, f_number, exposure_time, iso, focal_length, GPS coordinates, dimensions)
- `api_response` (TEXT/JSON): Stores full Immich API response for debugging

### API Integration

- **Endpoint**: `POST {IMMICH_URL}/api/assets`
- **Authentication**: x-api-key header
- **Form data**: deviceAssetId, deviceId, fileCreatedAt, fileModifiedAt, isFavorite
- **File field**: assetData (multipart upload)
- **Response codes**:
  - 200/201: Success (check response body for status='duplicate')
  - 409: Conflict/duplicate
  - Other: Error (logged to api_response)

### Error Handling (v2.0 IMPROVED)

- **Signal handling**: Graceful SIGINT (Ctrl+C) handling - cleans up DB/API connections before exit
- **Persistent connections**: Database connection with auto-reconnect via ping mechanism
- **Consecutive error tracking**: Configurable via MAX_CONSECUTIVE_ERRORS env var (default: 5)
- **File-level errors**: Logged to file (logs/immich_uploader.log) with full stack traces
- **Resumability**: State persists in database - can interrupt and resume at any time
- **Connection verification**: Immich connection tested before upload batch starts

### Progress Reporting (v2.0 ENHANCED)

New ProgressTracker class provides:
- **Real-time progress**: [current/total] (X%) with ETA calculation
- **Color-coded status**: Green (✅ success), Yellow (⚠ duplicate/skipped), Red (❌ error), Cyan (⏳ processing)
- **Speed metrics**: MB/s for uploads, files/s for scanning
- **Detailed summary**: Total processed, successful, duplicates, errors, skipped, time, throughput
- **Metadata display**: Camera, lens, dimensions, EXIF settings shown inline during upload

## Configuration

All configuration is in `.env` (loaded via config.py):

**Required:**
- `IMMICH_URL`: Immich server base URL
- `IMMICH_API_KEY`: API authentication key
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT`: MySQL connection
- `SOURCE_DIR`: Root directory to scan

**Optional (with defaults):**
- `IMAGE_EXTENSIONS`: Comma-separated (default: jpg,jpeg,png,webp,tiff,tif,bmp,heic,heif)
- `VIDEO_EXTENSIONS`: Comma-separated (default: mp4,mov,avi,mkv,wmv,flv,webm,m4v)
- `MAX_CONSECUTIVE_ERRORS`: Stop after N errors (default: 5)
- `UPLOAD_DELAY`: Seconds between uploads (default: 0.1)
- `HASH_CHUNK_SIZE`: Bytes for hashing (default: 4096)
- `LOG_LEVEL`: DEBUG/INFO/WARNING/ERROR (default: INFO)
- `LOG_FILE`: Log file path (default: logs/immich_uploader.log)

Note: `.env` is in .gitignore to protect credentials.

## Dependencies

Core libraries (requirements.txt):
- **PyMySQL**: MySQL database driver with connection pooling
- **requests**: HTTP client for Immich API (uses Session for connection reuse)
- **ExifRead**: EXIF metadata extraction from images
- **Pillow (PIL)**: Image dimensions and format detection
- **colorama**: Cross-platform colored terminal output
- **python-dotenv**: Environment variable management

## Key Improvements in v2.0

1. **Modular architecture**: Separated concerns into config, db, api, utils, logging, progress modules
2. **Persistent connections**: Database auto-reconnects, HTTP session reuse
3. **Signal handling**: Graceful Ctrl+C with cleanup
4. **Structured logging**: All operations logged to file with timestamps and levels
5. **Better progress reporting**: ETA, speed metrics, color-coded status, detailed summaries
6. **Configuration centralized**: All settings in config.py loaded from .env
7. **Type safety**: Better function signatures and return types
8. **Error resilience**: Connection verification, auto-reconnect, configurable error thresholds
