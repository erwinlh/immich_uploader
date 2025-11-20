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

### Script Organization

- **main.py**: Interactive CLI menu coordinator with ASCII logo display and status summaries
- **scan_files.py**: File discovery, SHA-256 hashing, EXIF metadata extraction, and database population
- **upload_files.py**: Processes pending files from database and uploads to Immich API
- **sync_upload.py**: Combined workflow that scans and uploads in a single pass (recommended for continuous processing)

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

### Error Handling

- **Consecutive error tracking**: Both scan and upload phases stop after 5 consecutive errors to prevent infinite loops on systemic issues (e.g., database connection loss, API unavailability)
- **File-level errors**: Hash calculation failures, missing files, and upload errors are logged individually without stopping the process
- **Resumability**: Upload state persists in database, allowing interruption and continuation

### Progress Reporting

Uses colorama for terminal output:
- Green (✅): Successful uploads
- Yellow (⚠): Duplicates or skipped files
- Red (❌): Errors
- Real-time display of current file, upload speed (MB/s), and metadata (camera, lens, exposure settings)

## Configuration

All configuration is in `.env`:
- `IMMICH_URL`: Immich server base URL
- `IMMICH_API_KEY`: API authentication key
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT`: MySQL connection
- `SOURCE_DIR`: Root directory to scan
- `IMAGE_EXTENSIONS`, `VIDEO_EXTENSIONS`: Comma-separated file types to process

Note: `.env` contains sensitive credentials and should never be committed (hardcoded path in main.py:14 for ASCII logo should be made relative if distributing).

## Dependencies

Core libraries:
- **PyMySQL**: MySQL database driver
- **requests**: HTTP client for Immich API
- **exifread**: EXIF metadata extraction
- **Pillow (PIL)**: Image dimensions and additional metadata
- **tqdm**: Progress bars (legacy, currently using custom progress display)
- **colorama**: Cross-platform colored terminal output
- **python-dotenv**: Environment variable management
