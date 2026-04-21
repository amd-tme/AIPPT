#!/usr/bin/env bash
# restore.sh — Import an AIPPT export archive
#
# Usage:
#   ./restore.sh <archive.tar.gz> [target-dir]
#
# Extracts a portable export archive created by `backup.sh --export`
# and sets up a working library directory. After restore, run:
#   python aippt.py serve
set -euo pipefail

# --- Parse arguments ---
if [ $# -lt 1 ]; then
    echo "Usage: $0 <archive.tar.gz> [target-dir]" >&2
    exit 1
fi

ARCHIVE="$1"
TARGET="${2:-.}"

# --- Validate archive ---
if [ ! -f "$ARCHIVE" ]; then
    echo "Error: Archive not found: $ARCHIVE" >&2
    exit 1
fi

# Check it looks like a tar.gz
case "$ARCHIVE" in
    *.tar.gz|*.tgz) ;;
    *) echo "Error: Expected a .tar.gz file: $ARCHIVE" >&2; exit 1 ;;
esac

echo "=== AIPPT Restore ==="
echo "Archive: $ARCHIVE"
echo "Target:  $TARGET"

# --- Create target directory ---
mkdir -p "$TARGET"
cd "$TARGET"

# --- Extract ---
echo "Extracting..."
tar -xzf "$ARCHIVE"

# --- Verify required files ---
if [ ! -f slides.db ]; then
    echo "Error: slides.db not found in archive" >&2
    exit 1
fi

# Create dirs.yaml with defaults if not in archive
if [ ! -f dirs.yaml ]; then
    cat > dirs.yaml << 'YAML'
# AIPPT directory configuration
# All paths are relative to the directory containing this file.
# Absolute paths are also supported for advanced use cases.
directories:
  outlines: outlines/
  templates: templates/
  uploads: uploads/
  output: output/
  backups: backups/
  images: images/
  db: slides.db
YAML
    echo "Created default dirs.yaml"
fi

# --- Print summary ---
echo ""
echo "=== Restore Summary ==="

# Count decks and slides from dbinfo.json if available
if [ -f dbinfo.json ]; then
    if command -v python3 &>/dev/null; then
        python3 -c "
import json, sys
try:
    with open('dbinfo.json') as f:
        info = json.load(f)
    stats = info.get('statistics', {})
    print(f\"  Decks:  {stats.get('total_decks', 'unknown')}\")
    print(f\"  Slides: {stats.get('total_slides', 'unknown')}\")
except Exception:
    pass
" 2>/dev/null || true
    fi
fi

# Show directory sizes
for dir in images uploads; do
    if [ -d "$dir" ]; then
        SIZE=$(du -sh "$dir" | cut -f1)
        echo "  $dir/: $SIZE"
    fi
done

TOTAL_SIZE=$(du -sh . | cut -f1)
echo "  Total: $TOTAL_SIZE"

echo ""
echo "To start the server:"
echo "  cd $TARGET"
echo "  python aippt.py serve"
echo ""
echo "=== Restore complete ==="
