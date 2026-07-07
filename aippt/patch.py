"""Patch engine for Chat-with-a-Deck: extract, validate, apply, and revert
text edits proposed by the LLM.

A *patch* is a targeted find-and-replace on a single field of a single slide.
The LLM emits patches inside fenced blocks::

    ```patch
    slide: 3
    field: content_text
    ---
    old text to find (verbatim)
    ===
    new text to replace it with
    ```

Each applied patch is appended to ``.aippt/edit-history.jsonl`` in the
current working directory so that any edit can be reverted later.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_PATCH_BLOCK_RE = re.compile(
    r"```patch\s*\n(.*?)```",
    re.DOTALL,
)

_EDIT_HISTORY_DIR = ".aippt"
_EDIT_HISTORY_FILE = "edit-history.jsonl"

PATCHABLE_FIELDS = {"title", "content_text", "notes"}


@dataclass
class Patch:
    slide_id: int
    field: str
    old_text: str
    new_text: str
    conversation_id: Optional[int] = None
    message_id: Optional[int] = None


def extract_patches(text: str) -> List[Patch]:
    """Parse all patch blocks from *text* and return :class:`Patch` objects.

    Blocks that are malformed (missing required keys, unknown field) are
    logged and skipped rather than raising.
    """
    patches: List[Patch] = []
    for m in _PATCH_BLOCK_RE.finditer(text):
        body = m.group(1)
        try:
            p = _parse_patch_block(body)
            patches.append(p)
        except ValueError as exc:
            logger.warning("Skipping malformed patch block: %s", exc)
    return patches


def _parse_patch_block(body: str) -> Patch:
    """Parse a single patch block body (the text inside the fences)."""
    if "===" not in body:
        raise ValueError("missing '===' separator between old and new text")

    # Split header (key: value lines) from the diff body at the first "---"
    if "---\n" not in body:
        raise ValueError("missing '---' separator between header and diff body")

    header_part, diff_part = body.split("---\n", 1)

    # Parse header key-value pairs
    header: dict = {}
    for line in header_part.splitlines():
        line = line.strip()
        if ":" in line:
            k, _, v = line.partition(":")
            header[k.strip()] = v.strip()

    slide_raw = header.get("slide", "")
    field = header.get("field", "").strip()

    if not slide_raw:
        raise ValueError("missing 'slide' key in patch header")
    if not field:
        raise ValueError("missing 'field' key in patch header")
    if field not in PATCHABLE_FIELDS:
        raise ValueError(f"unknown patchable field '{field}'; allowed: {PATCHABLE_FIELDS}")

    try:
        slide_id = int(slide_raw)
    except ValueError:
        raise ValueError(f"slide id must be an integer, got '{slide_raw}'")

    old_text, new_text = diff_part.split("===", 1)

    return Patch(
        slide_id=slide_id,
        field=field,
        old_text=old_text.strip("\n"),
        new_text=new_text.strip("\n"),
    )


def validate_patch(patch: Patch, conn: sqlite3.Connection) -> Tuple[bool, str]:
    """Check that *patch* can be applied to the database.

    Returns *(ok, reason)* — if ``ok`` is False, *reason* explains why.
    """
    row = conn.execute(
        f"SELECT {patch.field} FROM slides WHERE id = ?",  # noqa: S608 — field validated above
        (patch.slide_id,),
    ).fetchone()

    if row is None:
        return False, f"slide id {patch.slide_id} not found"

    current: str = row[0] or ""
    if patch.old_text not in current:
        return False, (
            f"old_text not found in slides.{patch.field} for slide {patch.slide_id}; "
            "the slide may have changed since the patch was generated"
        )

    return True, ""


def apply_patch(
    patch: Patch,
    conn: sqlite3.Connection,
    *,
    source: str = "chat",
    cwd: Optional[str] = None,
) -> int:
    """Apply *patch* to the database and append an entry to the edit-history log.

    Returns:
        The ``edit_history.id`` of the new row, so callers can link a specific
        message to the exact history entry it created.

    Raises:
        ValueError: If the patch fails validation.
    """
    ok, reason = validate_patch(patch, conn)
    if not ok:
        raise ValueError(f"Patch validation failed: {reason}")

    row = conn.execute(
        f"SELECT {patch.field} FROM slides WHERE id = ?",
        (patch.slide_id,),
    ).fetchone()
    current: str = row[0] or ""
    new_value = current.replace(patch.old_text, patch.new_text, 1)

    conn.execute(
        f"UPDATE slides SET {patch.field} = ?, updated_at = datetime('now') WHERE id = ?",
        (new_value, patch.slide_id),
    )

    # Record in edit_history table and capture the row id
    cur = conn.execute(
        """INSERT INTO edit_history (slide_id, field, old_value, new_value, source)
           VALUES (?, ?, ?, ?, ?)""",
        (patch.slide_id, patch.field, current, new_value, source),
    )
    history_id: int = cur.lastrowid
    conn.commit()

    # Append to .aippt/edit-history.jsonl
    _append_history(patch, current, new_value, cwd=cwd)
    logger.info("Applied patch to slides.%s for slide %d", patch.field, patch.slide_id)
    return history_id


def revert_by_id(
    history_id: int,
    conn: sqlite3.Connection,
    *,
    source: str = "chat",
    cwd: Optional[str] = None,
) -> Tuple[bool, str]:
    """Revert a specific edit_history row by its id.

    This is the precise form used by message-level Undo so that clicking Undo
    on a specific message reverts exactly that patch, not "the most recent one
    for the same slide+field."

    Returns *(ok, message)*.
    """
    row = conn.execute(
        "SELECT slide_id, field, old_value, new_value FROM edit_history WHERE id = ?",
        (history_id,),
    ).fetchone()

    if row is None:
        return False, f"No edit history row with id={history_id}"

    slide_id, field = row["slide_id"], row["field"]
    old_value, new_value = row["old_value"], row["new_value"]

    conn.execute(
        f"UPDATE slides SET {field} = ?, updated_at = datetime('now') WHERE id = ?",
        (old_value, slide_id),
    )
    conn.execute("DELETE FROM edit_history WHERE id = ?", (history_id,))
    conn.commit()

    revert_patch = Patch(slide_id=slide_id, field=field, old_text=new_value or "", new_text=old_value or "")
    _append_history(revert_patch, new_value or "", old_value or "", cwd=cwd, action="revert")
    logger.info("Reverted edit_history id=%d on slides.%s for slide %d", history_id, field, slide_id)
    return True, f"Reverted slide {slide_id} field '{field}' to previous value"


def revert_last(
    slide_id: int,
    field: str,
    conn: sqlite3.Connection,
    *,
    source: str = "chat",
    cwd: Optional[str] = None,
) -> Tuple[bool, str]:
    """Revert the most recent edit for *(slide_id, field)* using edit_history.

    Returns *(ok, message)*.
    """
    row = conn.execute(
        """SELECT id, old_value, new_value FROM edit_history
           WHERE slide_id = ? AND field = ?
           ORDER BY id DESC LIMIT 1""",
        (slide_id, field),
    ).fetchone()

    if row is None:
        return False, f"No edit history found for slide {slide_id}, field '{field}'"

    history_id, old_value, new_value = row["id"], row["old_value"], row["new_value"]

    conn.execute(
        f"UPDATE slides SET {field} = ?, updated_at = datetime('now') WHERE id = ?",
        (old_value, slide_id),
    )
    conn.execute("DELETE FROM edit_history WHERE id = ?", (history_id,))
    conn.commit()

    revert_patch = Patch(slide_id=slide_id, field=field, old_text=new_value or "", new_text=old_value or "")
    _append_history(revert_patch, new_value or "", old_value or "", cwd=cwd, action="revert")
    logger.info("Reverted last edit on slides.%s for slide %d", field, slide_id)
    return True, f"Reverted slide {slide_id} field '{field}' to previous value"


def _append_history(
    patch: Patch,
    old_value: str,
    new_value: str,
    *,
    cwd: Optional[str] = None,
    action: str = "apply",
) -> None:
    """Append a JSON line to ``.aippt/edit-history.jsonl``."""
    base = Path(cwd) if cwd else Path.cwd()
    history_dir = base / _EDIT_HISTORY_DIR
    history_dir.mkdir(exist_ok=True)
    entry = {
        "action": action,
        "ts": datetime.now(timezone.utc).isoformat(),
        "slide_id": patch.slide_id,
        "field": patch.field,
        "old_value": old_value,
        "new_value": new_value,
        "conversation_id": patch.conversation_id,
        "message_id": patch.message_id,
    }
    with (history_dir / _EDIT_HISTORY_FILE).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
