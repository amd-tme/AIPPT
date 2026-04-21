#!/usr/bin/env bash
# backup.sh — Snapshot database info and working directories into backup/
#
# Usage:
#   ./backup.sh            # Copy to backup/ directory (existing behavior)
#   ./backup.sh --export   # Create portable tar.gz archive in backups/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

BACKUP_DIR="backup"
BACKUPS_DIR="backups"
VENV_PYTHON=""
EXPORT_MODE=false

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --export) EXPORT_MODE=true ;;
        *) echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done

# Find virtualenv Python
if [ -f venv/bin/python ]; then
    VENV_PYTHON=venv/bin/python
elif [ -f venv/Scripts/python.exe ]; then
    VENV_PYTHON=venv/Scripts/python.exe
else
    echo "Error: venv not found" >&2
    exit 1
fi

if [ "$EXPORT_MODE" = true ]; then
    # --- Export mode: create portable tar.gz archive ---
    echo "=== AIPPT Export ==="

    if [ ! -f slides.db ]; then
        echo "Error: slides.db not found. Nothing to export." >&2
        exit 1
    fi

    # Run migrate-paths to ensure all paths are relative before archiving
    echo "Migrating paths to relative..."
    $VENV_PYTHON aippt.py migrate-paths

    # Create backups directory
    mkdir -p "$BACKUPS_DIR"

    # Generate archive filename
    DATE=$(date +%Y-%m-%d)
    ARCHIVE="$BACKUPS_DIR/aippt-export-${DATE}.tar.gz"

    # Build list of files to include
    FILES_TO_ARCHIVE="slides.db"

    # Dump database info as JSON
    $VENV_PYTHON aippt.py db-info --json --output dbinfo.json
    FILES_TO_ARCHIVE="$FILES_TO_ARCHIVE dbinfo.json"

    # Include dirs.yaml if it exists
    if [ -f dirs.yaml ]; then
        FILES_TO_ARCHIVE="$FILES_TO_ARCHIVE dirs.yaml"
    fi

    # Include directories
    for dir in images uploads; do
        if [ -d "$dir" ]; then
            FILES_TO_ARCHIVE="$FILES_TO_ARCHIVE $dir"
        fi
    done

    echo "Creating archive: $ARCHIVE"
    echo "Contents: $FILES_TO_ARCHIVE"
    tar -czf "$ARCHIVE" $FILES_TO_ARCHIVE

    # Clean up temporary dbinfo.json
    rm -f dbinfo.json

    ARCHIVE_SIZE=$(du -h "$ARCHIVE" | cut -f1)
    echo "Archive created: $ARCHIVE ($ARCHIVE_SIZE)"
    echo "=== Export complete ==="
else
    # --- Standard backup mode (existing behavior) ---
    echo "=== AIPPT Backup ==="
    echo "Backup dir: $BACKUP_DIR/"

    # Create backup directory
    mkdir -p "$BACKUP_DIR"

    # Dump database info (text + JSON)
    if [ -f slides.db ]; then
        echo "Dumping database info..."
        $VENV_PYTHON aippt.py db-info --output "$BACKUP_DIR/dbinfo.txt"
        $VENV_PYTHON aippt.py db-info --json --output "$BACKUP_DIR/dbinfo.json"
        cp slides.db "$BACKUP_DIR/slides.db"
        echo "  slides.db, dbinfo.txt, dbinfo.json saved"
    else
        echo "  No slides.db found, skipping database backup"
    fi

    # Copy working directories
    for dir in outlines output templates uploads; do
        if [ -d "$dir" ]; then
            echo "Copying $dir/..."
            rm -rf "$BACKUP_DIR/$dir"
            cp -a "$dir" "$BACKUP_DIR/$dir"
        else
            echo "  $dir/ not found, skipping"
        fi
    done

    echo "=== Backup complete ==="
fi
