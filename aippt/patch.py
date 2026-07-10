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

# JSON patch format: ```json { "patch": { "script": "...", "old": "...", "new": "...", ... } } ```
_JSON_PATCH_BLOCK_RE = re.compile(
    r"```json\s*\n(\{.*?\})\s*```",
    re.DOTALL,
)

_EDIT_HISTORY_DIR = ".aippt"
_EDIT_HISTORY_FILE = "edit-history.jsonl"

PATCHABLE_FIELDS = {"title", "content_text", "notes"}


@dataclass
class Patch:
    # Script-file patch fields (new format)
    script_path: Optional[str] = None
    anchor: Optional[str] = None
    old: Optional[str] = None
    new: Optional[str] = None
    summary: Optional[str] = None
    # Legacy SQLite-field patch fields (old format)
    slide_id: Optional[int] = None
    field: Optional[str] = None
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    conversation_id: Optional[int] = None
    message_id: Optional[int] = None

    @property
    def is_script_patch(self) -> bool:
        return self.script_path is not None


def extract_patches(text: str) -> List[Patch]:
    """Parse all patch blocks from *text* and return :class:`Patch` objects.

    Supports both the legacy ```patch format and the new ```json format.
    Blocks that are malformed are logged and skipped.
    """
    patches: List[Patch] = []

    # New JSON format
    for m in _JSON_PATCH_BLOCK_RE.finditer(text):
        try:
            data = json.loads(m.group(1))
            p_data = data.get("patch", {})
            if not p_data.get("script") or not p_data.get("old") or "new" not in p_data:
                logger.warning("Skipping JSON patch block: missing required keys")
                continue
            patches.append(Patch(
                script_path=p_data["script"],
                anchor=p_data.get("anchor", ""),
                old=p_data["old"],
                new=p_data["new"],
                summary=p_data.get("summary", ""),
            ))
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Skipping malformed JSON patch block: %s", exc)

    # Legacy ```patch format (fallback)
    for m in _PATCH_BLOCK_RE.finditer(text):
        body = m.group(1)
        try:
            p = _parse_legacy_patch_block(body)
            patches.append(p)
        except ValueError as exc:
            logger.warning("Skipping malformed patch block: %s", exc)

    return patches


def _parse_legacy_patch_block(body: str) -> Patch:
    """Parse a single legacy ```patch block body."""
    if "===" not in body:
        raise ValueError("missing '===' separator between old and new text")
    if "---\n" not in body:
        raise ValueError("missing '---' separator between header and diff body")

    header_part, diff_part = body.split("---\n", 1)

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


# Quoted string literals inside a code snippet: 'x', "x", or `x`.
_QUOTED_LITERAL_RE = re.compile(r"""(['"`])(.*?)\1""", re.DOTALL)


def _extract_literals(text: Optional[str]) -> set[str]:
    """Return the non-empty quoted string literals in *text*."""
    if not text:
        return set()
    return {
        m.group(2).strip()
        for m in _QUOTED_LITERAL_RE.finditer(text)
        if m.group(2).strip()
    }


def slides_touched_by_patch(patch: Patch, conn: sqlite3.Connection) -> List[int]:
    """Return the slide ids whose rendered content this patch changes.

    Used to invalidate exactly those slides' thumbnails after an apply/revert,
    so the deck view falls back to a placeholder card instead of showing a
    stale image.

    - Legacy field patches: just the patch's ``slide_id``.
    - Script patches: real LLM patches wrap the changed text in code, e.g.
      ``addBulletSlide(deck, 'Benefits', [``, so the raw ``old`` string is
      almost never a substring of a rendered slide field. We therefore build a
      set of candidate text fragments — the string *literals* that differ
      between ``old`` and ``new`` (the actual changed values), plus the raw
      ``old``/``new`` to still catch bare-text patches — and match those against
      title / content_text / notes for the decks sourced from this script
      (**precise**, option B). When nothing matches (structural edits, or decks
      whose rendered text isn't captured in any field), we fall back to
      invalidating every slide of those decks (**coarse**, option A) so a script
      edit never leaves a stale thumbnail behind.

    Over-matching within the script's own deck is safe (an extra placeholder
    that repopulates on the next Save); only a *miss* would show a stale image,
    and the coarse fallback prevents that.

    Always safe: any query error yields an empty list rather than raising.
    """
    try:
        if patch.is_script_patch:
            deck_rows = conn.execute(
                "SELECT id FROM decks WHERE source_script_path = ?",
                (patch.script_path,),
            ).fetchall()
            deck_ids = [r[0] for r in deck_rows]
            if not deck_ids:
                return []
            deck_ph = ",".join("?" for _ in deck_ids)

            # Candidate fragments: changed string literals (symmetric difference
            # so unchanged shared literals don't over-match) + raw old/new.
            changed = _extract_literals(patch.old) ^ _extract_literals(patch.new)
            candidates = {c for c in changed if c}
            for raw in (patch.old, patch.new):
                if raw and raw.strip():
                    candidates.add(raw.strip())

            matched: set[int] = set()
            for frag in candidates:
                like = f"%{frag}%"
                rows = conn.execute(
                    f"SELECT s.id FROM slides s "  # noqa: S608
                    f"WHERE s.deck_id IN ({deck_ph}) "
                    f"AND (s.title LIKE ? OR s.content_text LIKE ? OR s.notes LIKE ?)",
                    (*deck_ids, like, like, like),
                ).fetchall()
                matched.update(r[0] for r in rows)

            if matched:
                return sorted(matched)

            # Coarse fallback: can't locate the changed slide → invalidate the
            # whole deck so we never show a stale thumbnail after a script edit.
            rows = conn.execute(
                f"SELECT id FROM slides WHERE deck_id IN ({deck_ph})",  # noqa: S608
                deck_ids,
            ).fetchall()
            return sorted(r[0] for r in rows)
        if patch.slide_id is not None:
            return [int(patch.slide_id)]
    except sqlite3.Error:
        logger.exception("slides_touched_by_patch failed")
    return []


def _sync_script_patch_to_slides(patch: Patch, conn: sqlite3.Connection) -> None:
    """Mirror a script-file patch into the SQLite slides table.

    Finds every deck whose ``source_script_path`` matches the patched file and
    applies a search-and-replace across ``title``, ``content_text``, and ``notes``
    so the slide grid reflects the change without a full re-catalog.

    Opens a fresh connection on the same database file to avoid cross-thread
    SQLite errors when called from a FastAPI thread-pool worker.
    """
    # Use a fresh connection so this function is thread-safe regardless of
    # which thread the caller's conn was created in.
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    sync_conn = sqlite3.connect(db_file, timeout=30, check_same_thread=False)
    sync_conn.row_factory = sqlite3.Row
    try:
        decks = sync_conn.execute(
            "SELECT id FROM decks WHERE source_script_path = ?",
            (patch.script_path,),
        ).fetchall()
        for deck in decks:
            for field in ("title", "content_text", "notes"):
                sync_conn.execute(
                    f"UPDATE slides SET {field} = replace({field}, ?, ?), "  # noqa: S608
                    f"updated_at = datetime('now') "
                    f"WHERE deck_id = ? AND {field} LIKE ?",
                    (patch.old, patch.new, deck["id"], f"%{patch.old}%"),
                )
        sync_conn.commit()
    finally:
        sync_conn.close()


def _sync_script_revert_to_slides(old: str, new: str, script_path: str, conn: sqlite3.Connection) -> None:
    """Reverse a previously synced script patch in SQLite (swap old↔new)."""
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    sync_conn = sqlite3.connect(db_file, timeout=30, check_same_thread=False)
    sync_conn.row_factory = sqlite3.Row
    try:
        decks = sync_conn.execute(
            "SELECT id FROM decks WHERE source_script_path = ?",
            (script_path,),
        ).fetchall()
        for deck in decks:
            for field in ("title", "content_text", "notes"):
                sync_conn.execute(
                    f"UPDATE slides SET {field} = replace({field}, ?, ?), "  # noqa: S608
                    f"updated_at = datetime('now') "
                    f"WHERE deck_id = ? AND {field} LIKE ?",
                    (new, old, deck["id"], f"%{new}%"),
                )
        sync_conn.commit()
    finally:
        sync_conn.close()


def validate_patch(patch: Patch, conn: sqlite3.Connection) -> Tuple[bool, str]:
    """Check that *patch* can be applied.

    For script-file patches, verifies the file exists and contains the old text.
    For legacy SQLite patches, verifies the slide field contains the old text.
    Returns *(ok, reason)*.
    """
    if patch.is_script_patch:
        script = Path(patch.script_path)
        if not script.exists():
            return False, f"script file not found: {patch.script_path}"
        content = script.read_text(encoding="utf-8")
        occurrences = content.count(patch.old)
        if occurrences == 0:
            return False, (
                "old text not found in script — the file may have changed since the patch was proposed"
            )
        # The file write replaces only the first occurrence, but the SQLite grid
        # mirror replaces every occurrence. Requiring a unique match keeps the two
        # in sync and forces the LLM to widen the anchor when the text is ambiguous.
        if occurrences > 1:
            return False, (
                f"old text appears {occurrences} times in the script — the patch is ambiguous; "
                "include more surrounding context so it matches exactly once"
            )
        return True, ""

    # Legacy SQLite path
    row = conn.execute(
        f"SELECT {patch.field} FROM slides WHERE id = ?",  # noqa: S608
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
    """Apply *patch* and record it in edit_history.

    For script-file patches: writes the replacement directly to the .js file on disk.
    For legacy patches: updates the SQLite slides table.

    Returns the ``edit_history.id`` of the new row.
    Raises ``ValueError`` if validation fails.
    """
    ok, reason = validate_patch(patch, conn)
    if not ok:
        raise ValueError(f"Patch validation failed: {reason}")

    if patch.is_script_patch:
        script = Path(patch.script_path)
        content = script.read_text(encoding="utf-8")
        new_content = content.replace(patch.old, patch.new, 1)
        try:
            script.write_text(new_content, encoding="utf-8")
        except OSError as exc:
            # e.g. the script lives on a read-only filesystem. Surface a clean
            # ValueError (→ 400) instead of an uncaught 500. Preview-cataloged
            # decks stage a writable copy (see _stage_writable_script); this
            # guards decks whose source_script_path is still read-only.
            raise ValueError(
                f"Cannot write patch to script (is it on a read-only path?): {exc}"
            ) from exc

        # Mirror the change into SQLite so the slide grid updates immediately.
        _sync_script_patch_to_slides(patch, conn)

        cur = conn.execute(
            """INSERT INTO edit_history (slide_id, field, old_value, new_value, source)
               VALUES (NULL, 'script', ?, ?, ?)""",
            (patch.old, patch.new, source),
        )
        history_id: int = cur.lastrowid
        conn.commit()
        logger.info("Applied script patch to %s", patch.script_path)
        return history_id

    # Legacy SQLite path
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
    cur = conn.execute(
        """INSERT INTO edit_history (slide_id, field, old_value, new_value, source)
           VALUES (?, ?, ?, ?, ?)""",
        (patch.slide_id, patch.field, current, new_value, source),
    )
    history_id = cur.lastrowid
    conn.commit()

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

    if field == "script":
        # Script-file revert: find the script path from the conversation's script_path
        # The script path is stored implicitly — we find the chat_messages row that
        # references this history_id to get the conversation's script_path.
        msg_row = conn.execute(
            """SELECT cc.script_path FROM chat_messages cm
               JOIN chat_conversations cc ON cm.conversation_id = cc.id
               WHERE cm.edit_history_id = ?""",
            (history_id,),
        ).fetchone()
        if msg_row and msg_row["script_path"]:
            script = Path(msg_row["script_path"])
            if script.exists():
                content = script.read_text(encoding="utf-8")
                try:
                    script.write_text(content.replace(new_value, old_value, 1), encoding="utf-8")
                except OSError as exc:
                    # Read-only script path — report cleanly instead of 500ing.
                    return False, f"Cannot revert patch (script on a read-only path?): {exc}"
            # Mirror the revert into SQLite so the slide grid updates immediately.
            _sync_script_revert_to_slides(old_value, new_value, msg_row["script_path"], conn)
        conn.execute("DELETE FROM edit_history WHERE id = ?", (history_id,))
        conn.commit()
        logger.info("Reverted script patch id=%d", history_id)
        return True, "Reverted script edit"

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
