"""Chat-with-a-Deck service layer.

Provides :class:`ChatService` which manages multi-turn conversations scoped to
a cataloged deck, with optional per-slide context (image + metadata).  The
service streams LLM responses and surfaces patch blocks proposed by the model
as ``[PATCH_PROPOSED:...]`` events for the caller to present to the user — no
patch is written to disk without explicit user confirmation.

Conversations and messages are persisted in the catalog SQLite database
(tables: ``chat_conversations``, ``chat_messages``).
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Generator, Iterator, List, Optional

import sqlite3

from aippt.llm import LLMClient
from aippt.patch import (
    extract_patches,
    apply_patch,
    revert_by_id,
    revert_last,
    slides_touched_by_patch,
    Patch,
)
from aippt.thumbnails import invalidate_slides

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_BASE = """\
You are an expert presentation designer helping the user improve a PowerPoint deck.

The slide content is provided directly in each user message inside a context block that
starts with "[Deck context —" or "[Slide context —". Use that block as your sole source
of truth for what is on the slides. Do NOT ask the user to share slides or screenshots —
the text content is already there.
"""

_EDIT_MODE_ADDENDUM_TEMPLATE = """\
When the user asks you to make a specific text change, emit exactly one fenced JSON block:

```json
{{
  "patch": {{
    "script": "{script_path}",
    "anchor": "<unique function name or line substring near the change>",
    "old": "<exact text to replace — copy verbatim from the script above>",
    "new": "<replacement text>",
    "summary": "<one line: what and why>"
  }}
}}
```

Rules for patches:
- Use the exact script path shown in the [Script: ...] header above — copy it verbatim.
- The "old" text MUST match the script verbatim — copy it exactly.
- Make one focused change per block.
- Do not emit a patch block if the user is only asking a question or requesting analysis.
- After the block, briefly explain what you changed and why.
"""

_EDIT_MODE_ADDENDUM_SLIDE = """\
This deck has no source script — edits are applied directly to the slide's
stored text. When the user asks you to make a specific text change, emit
exactly one fenced patch block in this format:

```patch
slide: <slide id from the context block>
field: <title | content_text | notes>
---
<exact text to replace — copy verbatim from the slide content above>
===
<replacement text>
```

Rules for patches:
- Use the numeric slide id shown as "id=" / "slide id:" in the context block above.
- "field" must be one of: title, content_text, notes.
- The old text (before "===") MUST match the slide content verbatim — copy it exactly.
- Make one focused change per block.
- Do NOT emit a ```json script patch — this deck has no script file to patch.
- Do not emit a patch block if the user is only asking a question or requesting analysis.
- After the block, briefly explain what you changed and why.
"""

_ASK_MODE_ADDENDUM = """\
You are in read-only Ask mode. Provide analysis, explanations, summaries, and
suggestions in plain text only. Do NOT emit any patch blocks — the user has not
requested edits in this turn.
"""


def _system_prompt(mode: str, script_path: Optional[str] = None) -> str:
    if mode == "edit":
        if script_path:
            addendum = _EDIT_MODE_ADDENDUM_TEMPLATE.format(script_path=script_path)
        else:
            addendum = _EDIT_MODE_ADDENDUM_SLIDE
    else:
        addendum = _ASK_MODE_ADDENDUM
    return _SYSTEM_PROMPT_BASE + "\n" + addendum


class CancelToken:
    """Simple cancellation flag threadsafe for SSE / background tasks."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()


class ChatService:
    """Manages chat conversations scoped to a deck.

    Args:
        conn: Open SQLite connection to the catalog database.
        llm: Configured :class:`~aippt.llm.LLMClient` for the model to use.
        db_cwd: Working directory used when writing the edit-history log.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        llm: LLMClient,
        db_cwd: Optional[str] = None,
    ) -> None:
        self.conn = conn
        self.llm = llm
        self.db_cwd = db_cwd

    # ------------------------------------------------------------------
    # Conversation CRUD
    # ------------------------------------------------------------------

    def create_conversation(self, deck_id: int, title: str = "New conversation", script_path: Optional[str] = None) -> int:
        """Create a new conversation for *deck_id* and return its id."""
        cur = self.conn.execute(
            "INSERT INTO chat_conversations (deck_id, title, script_path) VALUES (?, ?, ?)",
            (deck_id, title, script_path),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_conversations(self, deck_id: int) -> list:
        """Return all conversations for *deck_id* ordered by most recently updated."""
        rows = self.conn.execute(
            """SELECT id, title, created_at, updated_at
               FROM chat_conversations
               WHERE deck_id = ?
               ORDER BY updated_at DESC""",
            (deck_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conversation_id: int) -> Optional[dict]:
        """Return conversation metadata or None."""
        row = self.conn.execute(
            "SELECT id, deck_id, title, script_path, created_at, updated_at FROM chat_conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        return dict(row) if row else None

    def delete_conversation(self, conversation_id: int) -> bool:
        """Delete a conversation and all its messages. Returns True if deleted."""
        cur = self.conn.execute(
            "DELETE FROM chat_conversations WHERE id = ?", (conversation_id,)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def rename_conversation(self, conversation_id: int, title: str) -> bool:
        """Rename a conversation title. Returns True on success."""
        cur = self.conn.execute(
            "UPDATE chat_conversations SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (title, conversation_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def get_messages(self, conversation_id: int) -> list:
        """Return all messages in a conversation in chronological order."""
        rows = self.conn.execute(
            """SELECT id, role, content, slide_id, mode, patch_json,
                      patch_applied_at, patch_reverted_at, created_at
               FROM chat_messages
               WHERE conversation_id = ?
               ORDER BY id ASC""",
            (conversation_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _save_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        slide_id: Optional[int] = None,
        mode: str = "ask",
        patch_json: Optional[str] = None,
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO chat_messages
               (conversation_id, role, content, slide_id, mode, patch_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (conversation_id, role, content, slide_id, mode, patch_json),
        )
        self.conn.execute(
            "UPDATE chat_conversations SET updated_at = datetime('now') WHERE id = ?",
            (conversation_id,),
        )
        self.conn.commit()
        return cur.lastrowid

    def apply_message_patch(self, message_id: int) -> tuple[bool, str]:
        """Apply the patch stored on *message_id*. Returns (ok, reason)."""
        row = self.conn.execute(
            "SELECT patch_json, patch_applied_at, conversation_id FROM chat_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if not row:
            return False, "Message not found"
        if row["patch_applied_at"]:
            return False, "Patch already applied"
        if not row["patch_json"]:
            return False, "No patch on this message"

        patches = [Patch(**p) for p in json.loads(row["patch_json"])]
        errors = []
        history_ids = []
        touched: list[int] = []
        for patch in patches:
            patch.conversation_id = row["conversation_id"]
            patch.message_id = message_id
            # Collect affected slide ids *before* the write, while the old text
            # is still present to match, so we can invalidate their thumbnails.
            touched.extend(slides_touched_by_patch(patch, self.conn))
            try:
                history_id = apply_patch(patch, self.conn, source="chat", cwd=self.db_cwd)
                history_ids.append(history_id)
            except ValueError as exc:
                errors.append(str(exc))

        if errors:
            return False, "; ".join(errors)

        # Store the first (usually only) history_id so Undo reverts the exact row.
        self.conn.execute(
            "UPDATE chat_messages SET patch_applied_at = datetime('now'), edit_history_id = ? WHERE id = ?",
            (history_ids[0] if history_ids else None, message_id),
        )
        self.conn.commit()

        # Invalidate the changed slides' thumbnails so the UI falls back to a
        # placeholder instead of a stale image. Best-effort: never fails apply.
        self._invalidate_thumbnails(touched)
        return True, "ok"

    def revert_message_patch(self, message_id: int) -> tuple[bool, str]:
        """Revert the patch stored on *message_id*. Returns (ok, reason).

        Uses the stored edit_history_id to revert the exact row created when
        this message's patch was applied, avoiding the "reverts the wrong patch"
        bug that occurred when multiple patches touched the same slide+field.
        """
        row = self.conn.execute(
            "SELECT patch_json, patch_applied_at, edit_history_id FROM chat_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if not row:
            return False, "Message not found"
        if not row["patch_applied_at"]:
            return False, "Patch has not been applied yet"
        if not row["patch_json"]:
            return False, "No patch on this message"

        # Collect the slides this revert will change *before* the write. After
        # apply, the slide content holds the patch's ``new`` text; matching on
        # that finds the same rows the revert rewrites back to ``old``.
        touched: list[int] = []
        try:
            for p in json.loads(row["patch_json"]):
                patch = Patch(**p)
                if patch.is_script_patch:
                    probe = Patch(script_path=patch.script_path, old=patch.new, new=patch.old)
                    touched.extend(slides_touched_by_patch(probe, self.conn))
                elif patch.slide_id is not None:
                    touched.append(int(patch.slide_id))
        except (ValueError, TypeError, json.JSONDecodeError):
            touched = []

        history_id = row["edit_history_id"]
        if history_id is not None:
            # Precise revert: target the exact edit_history row this message created.
            ok, reason = revert_by_id(history_id, self.conn, source="chat-revert", cwd=self.db_cwd)
            if not ok:
                return False, reason
        else:
            # Fallback for messages applied before edit_history_id tracking was added.
            patches = [Patch(**p) for p in json.loads(row["patch_json"])]
            errors = []
            for patch in patches:
                ok, reason = revert_last(
                    patch.slide_id, patch.field, self.conn, source="chat-revert", cwd=self.db_cwd
                )
                if not ok:
                    errors.append(reason)
            if errors:
                return False, "; ".join(errors)

        self.conn.execute(
            "UPDATE chat_messages SET patch_reverted_at = datetime('now') WHERE id = ?",
            (message_id,),
        )
        self.conn.commit()

        # Invalidate the reverted slides' thumbnails (best-effort).
        self._invalidate_thumbnails(touched)
        return True, "ok"

    def _invalidate_thumbnails(self, slide_ids: list[int]) -> None:
        """Null image_path/hash for changed slides so the UI drops to a
        placeholder rather than showing a stale thumbnail. Never raises."""
        if not slide_ids:
            return
        try:
            db_file = self.conn.execute("PRAGMA database_list").fetchone()[2]
        except sqlite3.Error:
            return
        if not db_file:
            return
        invalidate_slides(slide_ids, db_path=db_file)

    # ------------------------------------------------------------------
    # Slide / deck context helpers
    # ------------------------------------------------------------------

    def _build_script_context(self, script_path: str) -> str:
        """Return the full .js script content so the LLM can produce verbatim patches."""
        from pathlib import Path
        try:
            content = Path(script_path).read_text(encoding="utf-8")
        except OSError:
            return ""
        return f"[Script: {script_path}]\n```javascript\n{content}\n```\n"

    def _build_deck_context(self, deck_id: int) -> str:
        """Return a compact summary of every slide in *deck_id* for deck-level chat."""
        rows = self.conn.execute(
            """SELECT s.id, s.position, s.title, s.content_text, d.name as deck_name
               FROM slides s JOIN decks d ON s.deck_id = d.id
               WHERE s.deck_id = ?
               ORDER BY s.position ASC""",
            (deck_id,),
        ).fetchall()
        if not rows:
            return ""
        deck_name = rows[0]["deck_name"]
        parts = [f"[Deck context — \"{deck_name}\", {len(rows)} slides]"]
        for r in rows:
            entry = f"\nSlide {r['position']} (id={r['id']}): {r['title']}"
            if r["content_text"]:
                body = r["content_text"][:400]
                if len(r["content_text"]) > 400:
                    body += "…"
                entry += f"\n{body}"
            parts.append(entry)
        return "\n".join(parts)

    def _build_slide_context(self, slide_id: int) -> str:
        """Return a text block describing the slide's current content."""
        row = self.conn.execute(
            """SELECT s.id, s.position, s.title, s.content_text, s.notes, d.name as deck_name
               FROM slides s JOIN decks d ON s.deck_id = d.id
               WHERE s.id = ?""",
            (slide_id,),
        ).fetchone()
        if not row:
            return ""
        parts = [
            f"[Slide context — deck: {row['deck_name']}, slide id: {row['id']}, position: {row['position']}]",
            f"Title: {row['title']}",
        ]
        if row["content_text"]:
            parts.append(f"Content:\n{row['content_text']}")
        if row["notes"]:
            parts.append(f"Speaker notes:\n{row['notes']}")
        return "\n".join(parts)

    def _get_slide_image(self, slide_id: int) -> Optional[str]:
        """Return the image_path for *slide_id* or None if not available."""
        row = self.conn.execute(
            "SELECT image_path FROM slides WHERE id = ?", (slide_id,)
        ).fetchone()
        if row and row["image_path"]:
            from pathlib import Path
            p = Path(row["image_path"])
            if p.exists():
                return str(p)
        return None

    # ------------------------------------------------------------------
    # Streaming response
    # ------------------------------------------------------------------

    def stream_reply(
        self,
        conversation_id: int,
        user_message: str,
        *,
        slide_id: Optional[int] = None,
        mode: str = "ask",
        cancel_token: Optional[CancelToken] = None,
    ) -> Generator[str, None, None]:
        """Persist the user message, stream the LLM reply, and surface any
        patch blocks as ``[PATCH_PROPOSED:msg_id:json]`` events.

        Patches are NOT applied automatically — the caller must present them
        to the user and call :meth:`apply_message_patch` on confirmation.

        Yields str chunks (text fragments) as they arrive from the LLM, plus
        special sentinel strings:

        - ``"[PATCH_PROPOSED:{msg_id}:{json}]"`` — patch JSON ready for review.
        - ``"[CANCELLED]"`` if the cancel token fires mid-stream.

        Args:
            conversation_id: Which conversation to continue.
            user_message: The user's new message text.
            slide_id: Optional slide to include as context (and image if available).
            mode: ``"ask"`` (read-only) or ``"edit"`` (patches allowed).
            cancel_token: If set, streaming stops when ``cancel_token.is_cancelled``.
        """
        conv = self.get_conversation(conversation_id)
        conv_script_path = conv.get("script_path") if conv else None

        if slide_id:
            context = self._build_slide_context(slide_id)
        elif conv_script_path:
            context = self._build_script_context(conv_script_path)
        else:
            context = self._build_deck_context(conv["deck_id"]) if conv else ""
        full_user_content = (
            f"{context}\n\n---\n\n{user_message}" if context else user_message
        )

        # Persist user message
        self._save_message(conversation_id, "user", user_message, slide_id, mode=mode)

        # Build LLM history — re-inject context for every prior user turn so
        # the model always has the script/slide data regardless of history depth.
        history = self.get_messages(conversation_id)
        conv_meta = self.get_conversation(conversation_id)
        script_path_for_ctx = conv_meta.get("script_path") if conv_meta else None
        deck_ctx: str
        if script_path_for_ctx:
            deck_ctx = self._build_script_context(script_path_for_ctx)
        else:
            deck_ctx = self._build_deck_context(conv_meta["deck_id"]) if conv_meta else ""
        llm_messages = []
        for m in history[:-1]:  # exclude the message we just saved
            if m["role"] == "assistant":
                llm_messages.append({"role": "assistant", "content": m["content"]})
            elif m["slide_id"]:
                ctx = self._build_slide_context(m["slide_id"])
                llm_messages.append({"role": "user", "content": f"{ctx}\n\n---\n\n{m['content']}"})
            else:
                llm_messages.append({"role": "user", "content": f"{deck_ctx}\n\n---\n\n{m['content']}" if deck_ctx else m["content"]})
        llm_messages.append({"role": "user", "content": full_user_content})

        image_path = self._get_slide_image(slide_id) if slide_id else None
        use_vision = image_path is not None and self.llm.model_config.supports_vision
        script_path = conv_meta.get("script_path") if conv_meta else None
        system = _system_prompt(mode, script_path=script_path)

        if use_vision:
            stream_iter: Iterator[str] = self.llm.stream_text_with_image(
                llm_messages,
                image_path=image_path,
                system_prompt=system,
                max_tokens=4096,
            )
        else:
            stream_iter = self.llm.stream_text(
                llm_messages,
                system_prompt=system,
                max_tokens=4096,
            )

        accumulated = []
        try:
            for chunk in stream_iter:
                if cancel_token and cancel_token.is_cancelled:
                    yield "[CANCELLED]"
                    break
                accumulated.append(chunk)
                yield chunk
        except Exception as exc:
            logger.error("LLM stream error: %s", exc)
            raise

        full_reply = "".join(accumulated)

        # In edit mode, extract patches and save them — do NOT apply yet.
        patch_json_str: Optional[str] = None
        if mode == "edit":
            patches = extract_patches(full_reply)
            if patches:
                patch_dicts = []
                for p in patches:
                    if p.is_script_patch:
                        patch_dicts.append({
                            "script_path": p.script_path,
                            "anchor": p.anchor,
                            "old": p.old,
                            "new": p.new,
                            "summary": p.summary,
                        })
                    else:
                        patch_dicts.append({
                            "slide_id": p.slide_id,
                            "field": p.field,
                            "old_text": p.old_text,
                            "new_text": p.new_text,
                        })
                patch_json_str = json.dumps(patch_dicts)

        msg_id = self._save_message(
            conversation_id, "assistant", full_reply, slide_id,
            mode=mode, patch_json=patch_json_str,
        )

        if patch_json_str:
            yield f"[PATCH_PROPOSED:{msg_id}:{patch_json_str}]"
