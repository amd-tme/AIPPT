"""Resolve deck identifiers to source script paths for the /edit-deck skill.

Handles three resolution strategies:
1. Direct file path — if the identifier is an existing file, use it directly
2. Catalog ID — if integer, look up deck by ID
3. Catalog name — partial name match
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from aippt.catalog import resolve_deck, display_name, detect_source_engine

logger = logging.getLogger(__name__)


def _detect_engine(script_path: str) -> Optional[str]:
    """Detect engine from script content, falling back to extension heuristics."""
    # Try catalog's content-based detection first
    engine = detect_source_engine(script_path)
    if engine:
        return engine

    # Fallback: extension-based detection for ES module style imports
    ext = Path(script_path).suffix.lower()
    if ext in (".js", ".mjs"):
        return "pptxgenjs"
    elif ext == ".py":
        return "python-pptx"
    return None


def resolve_source(
    identifier: str,
    db_path: str = "slides.db",
) -> dict:
    """Resolve a deck identifier to its source script path.

    Args:
        identifier: Script file path, deck ID (integer string), or deck name substring
        db_path: Path to the SQLite database

    Returns:
        dict with keys:
        - script_path: str (path to the source script)
        - engine: str or None ('pptxgenjs' or 'python-pptx')
        - theme: str or None
        - deck_name: str or None (display name if resolved from catalog)
        - resolved_from: 'path' or 'catalog'
        - error: str or None (set if resolution failed)
        - choices: list of dicts (set if multiple matches found)
    """
    result = {
        "script_path": None,
        "engine": None,
        "theme": None,
        "deck_name": None,
        "resolved_from": None,
        "error": None,
        "choices": [],
    }

    # Strategy 1: Direct file path
    if os.path.isfile(identifier):
        result["script_path"] = identifier
        result["engine"] = _detect_engine(identifier)
        result["resolved_from"] = "path"
        return result

    # Strategy 2 & 3: Catalog lookup (by ID or name)
    deck = resolve_deck(identifier, db_path=db_path)

    if deck is None:
        result["error"] = f"No deck found matching '{identifier}'"
        return result

    if isinstance(deck, list):
        result["error"] = f"Multiple decks match '{identifier}'"
        result["choices"] = [
            {"id": d["id"], "name": display_name(d["name"])}
            for d in deck
        ]
        return result

    # Single match — extract source info
    script_path = deck.get("source_script_path")
    if not script_path:
        deck_name = display_name(deck["name"])
        result["error"] = (
            f"No source script tracked for '{deck_name}'. "
            "Provide a direct script path instead, or re-ingest with --source."
        )
        return result

    result["script_path"] = script_path
    result["engine"] = deck.get("source_engine")
    result["theme"] = deck.get("source_theme")
    result["deck_name"] = display_name(deck["name"])
    result["resolved_from"] = "catalog"
    return result


def create_backup(script_path: str) -> Optional[str]:
    """Create a .bak backup of the script if one doesn't already exist.

    Returns the backup path if created, None if skipped (already exists).
    """
    bak_path = script_path + ".bak"
    if os.path.exists(bak_path):
        logger.info("Backup already exists at %s, skipping", bak_path)
        return None
    shutil.copy2(script_path, bak_path)
    logger.info("Created backup: %s", bak_path)
    return bak_path


def has_backup(script_path: str) -> bool:
    """Check if a .bak backup exists for this script."""
    return os.path.exists(script_path + ".bak")


def restore_backup(script_path: str) -> bool:
    """Restore the script from its .bak backup.

    Returns True if restored, False if no backup found.
    The .bak file is preserved (not deleted) so the user
    can restore again if needed.
    """
    bak_path = script_path + ".bak"
    if not os.path.exists(bak_path):
        return False
    shutil.copy2(bak_path, script_path)
    logger.info("Restored %s from backup", script_path)
    return True


def run_script(script_path: str, engine: str, timeout: int = 120) -> dict:
    """Execute a deck generation script and return the result.

    Args:
        script_path: Path to the JS or Python script
        engine: 'pptxgenjs' or 'python-pptx'
        timeout: Max execution time in seconds

    Returns:
        dict with keys:
        - success: bool
        - stdout: str
        - stderr: str
        - file_locked: bool (True if failure looks like a file-in-use error)
    """
    if engine == "pptxgenjs":
        cmd = ["node", script_path]
    else:
        cmd = [sys.executable, script_path]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(os.path.abspath(script_path)) or ".",
        )
        stderr = proc.stderr or ""
        file_locked = any(
            marker in stderr
            for marker in ("PermissionError", "EBUSY", "being used by another process")
        )
        return {
            "success": proc.returncode == 0,
            "stdout": proc.stdout or "",
            "stderr": stderr,
            "file_locked": file_locked and proc.returncode != 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Script timed out after {timeout} seconds",
            "file_locked": False,
        }
    except FileNotFoundError as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "file_locked": False,
        }
