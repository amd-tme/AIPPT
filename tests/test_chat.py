"""Tests for Chat-with-a-Deck: schema, patch engine, ChatService, and routes.

All LLM calls are stubbed so no network or API key is required.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aippt.catalog import get_db
from aippt.patch import (
    Patch,
    extract_patches,
    validate_patch,
    apply_patch,
    revert_last,
    PATCHABLE_FIELDS,
)
from aippt.chat import ChatService, CancelToken, _system_prompt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def conn(db_path):
    c = get_db(db_path)
    # Seed a deck and two slides
    cur = c.execute(
        "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?,?,?,?)",
        ("test-deck", "/tmp/test.pptx", "abc123", 2),
    )
    deck_id = cur.lastrowid
    c.execute(
        "INSERT INTO slides (deck_id, position, title, content_text, content_hash) VALUES (?,?,?,?,?)",
        (deck_id, 1, "Intro", "Welcome to the deck.\nMore text here.", "h1"),
    )
    c.execute(
        "INSERT INTO slides (deck_id, position, title, content_text, content_hash) VALUES (?,?,?,?,?)",
        (deck_id, 2, "Details", "Detailed content.", "h2"),
    )
    c.commit()
    yield c
    c.close()


@pytest.fixture
def deck_id(conn):
    row = conn.execute("SELECT id FROM decks LIMIT 1").fetchone()
    return row["id"]


@pytest.fixture
def slide_id(conn):
    row = conn.execute("SELECT id FROM slides ORDER BY position LIMIT 1").fetchone()
    return row["id"]


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestSchema:
    def test_chat_tables_exist(self, db_path):
        conn = get_db(db_path)
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "chat_conversations" in tables
        assert "chat_messages" in tables
        conn.close()

    def test_chat_conversation_fk_cascade(self, conn, deck_id):
        cur = conn.execute(
            "INSERT INTO chat_conversations (deck_id, title) VALUES (?, ?)",
            (deck_id, "test conv"),
        )
        conv_id = cur.lastrowid
        conn.execute(
            "INSERT INTO chat_messages (conversation_id, role, content) VALUES (?,?,?)",
            (conv_id, "user", "hello"),
        )
        conn.commit()
        conn.execute("DELETE FROM chat_conversations WHERE id = ?", (conv_id,))
        conn.commit()
        msgs = conn.execute(
            "SELECT * FROM chat_messages WHERE conversation_id = ?", (conv_id,)
        ).fetchall()
        assert msgs == [], "messages should cascade-delete when conversation is deleted"


# ---------------------------------------------------------------------------
# Patch engine tests
# ---------------------------------------------------------------------------

class TestExtractPatches:
    def test_valid_patch(self):
        text = (
            "Here is the change:\n"
            "```patch\n"
            "slide: 3\n"
            "field: content_text\n"
            "---\n"
            "old text\n"
            "===\n"
            "new text\n"
            "```\n"
        )
        patches = extract_patches(text)
        assert len(patches) == 1
        p = patches[0]
        assert p.slide_id == 3
        assert p.field == "content_text"
        assert p.old_text == "old text"
        assert p.new_text == "new text"

    def test_multiple_patches(self):
        text = (
            "```patch\nslide: 1\nfield: title\n---\nOld Title\n===\nNew Title\n```\n"
            "some text in between\n"
            "```patch\nslide: 2\nfield: notes\n---\nOld notes\n===\nNew notes\n```\n"
        )
        patches = extract_patches(text)
        assert len(patches) == 2

    def test_malformed_patch_skipped(self):
        text = "```patch\nslide: 1\nfield: title\n---\nno separator here\n```"
        patches = extract_patches(text)
        assert patches == []

    def test_unknown_field_skipped(self):
        text = "```patch\nslide: 1\nfield: nonexistent\n---\nold\n===\nnew\n```"
        patches = extract_patches(text)
        assert patches == []

    def test_no_patches(self):
        assert extract_patches("Just a regular response with no patches.") == []


class TestValidatePatch:
    def test_valid(self, conn, slide_id):
        p = Patch(slide_id=slide_id, field="content_text",
                  old_text="Welcome to the deck.", new_text="Hello world.")
        ok, reason = validate_patch(p, conn)
        assert ok, reason

    def test_slide_not_found(self, conn):
        p = Patch(slide_id=999999, field="content_text", old_text="x", new_text="y")
        ok, reason = validate_patch(p, conn)
        assert not ok
        assert "not found" in reason

    def test_old_text_not_in_field(self, conn, slide_id):
        p = Patch(slide_id=slide_id, field="content_text",
                  old_text="text that does not exist in slide", new_text="y")
        ok, reason = validate_patch(p, conn)
        assert not ok
        assert "not found" in reason


class TestApplyPatch:
    def test_apply_replaces_text(self, conn, slide_id, tmp_path):
        p = Patch(slide_id=slide_id, field="content_text",
                  old_text="Welcome to the deck.", new_text="Hello world.")
        apply_patch(p, conn, cwd=str(tmp_path))
        row = conn.execute("SELECT content_text FROM slides WHERE id = ?", (slide_id,)).fetchone()
        assert "Hello world." in row["content_text"]

    def test_apply_writes_edit_history(self, conn, slide_id, tmp_path):
        p = Patch(slide_id=slide_id, field="content_text",
                  old_text="Welcome to the deck.", new_text="Updated.")
        apply_patch(p, conn, cwd=str(tmp_path))
        hist = conn.execute(
            "SELECT * FROM edit_history WHERE slide_id = ? AND field = ?",
            (slide_id, "content_text"),
        ).fetchall()
        assert len(hist) == 1

    def test_apply_writes_jsonl(self, conn, slide_id, tmp_path):
        p = Patch(slide_id=slide_id, field="content_text",
                  old_text="Welcome to the deck.", new_text="From test.")
        apply_patch(p, conn, cwd=str(tmp_path))
        log_file = tmp_path / ".aippt" / "edit-history.jsonl"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().splitlines()[0])
        assert entry["action"] == "apply"
        assert entry["slide_id"] == slide_id

    def test_apply_invalid_raises(self, conn, slide_id, tmp_path):
        p = Patch(slide_id=slide_id, field="content_text",
                  old_text="NO SUCH TEXT", new_text="x")
        with pytest.raises(ValueError, match="validation failed"):
            apply_patch(p, conn, cwd=str(tmp_path))


class TestRevertPatch:
    def test_revert_last(self, conn, slide_id, tmp_path):
        p = Patch(slide_id=slide_id, field="content_text",
                  old_text="Welcome to the deck.", new_text="Changed.")
        apply_patch(p, conn, cwd=str(tmp_path))
        ok, msg = revert_last(slide_id, "content_text", conn, cwd=str(tmp_path))
        assert ok, msg
        row = conn.execute("SELECT content_text FROM slides WHERE id = ?", (slide_id,)).fetchone()
        assert "Welcome to the deck." in row["content_text"]

    def test_revert_no_history(self, conn, slide_id, tmp_path):
        ok, msg = revert_last(slide_id, "notes", conn, cwd=str(tmp_path))
        assert not ok
        assert "No edit history" in msg


# ---------------------------------------------------------------------------
# Script-file patch tests (the new .js-patch path)
# ---------------------------------------------------------------------------

class TestScriptPatch:
    def _seed_script_deck(self, conn, tmp_path, body):
        script = tmp_path / "deck.js"
        script.write_text(body, encoding="utf-8")
        cur = conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, source_script_path) VALUES (?,?,?,?)",
            ("script-deck", "/tmp/script-deck.pptx", "shash", str(script)),
        )
        return str(script), cur.lastrowid

    def test_apply_script_patch_fresh_db(self, conn, tmp_path):
        """A script patch inserts slide_id=NULL into edit_history; regression
        test for the NOT NULL crash on a freshly-initialized database."""
        script, _ = self._seed_script_deck(conn, tmp_path, "var title = 'Old Title';\n")
        conn.commit()
        p = Patch(script_path=script, old="Old Title", new="New Title", summary="s")
        history_id = apply_patch(p, conn, cwd=str(tmp_path))
        assert history_id > 0
        assert "New Title" in Path(script).read_text()
        row = conn.execute(
            "SELECT slide_id, field FROM edit_history WHERE id = ?", (history_id,)
        ).fetchone()
        assert row["slide_id"] is None
        assert row["field"] == "script"

    def test_apply_script_patch_syncs_grid(self, conn, tmp_path):
        script, deck_id = self._seed_script_deck(conn, tmp_path, "title = 'Alpha';\n")
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash) VALUES (?,?,?,?,?)",
            (deck_id, 1, "Alpha", "body", "sh1"),
        )
        conn.commit()
        p = Patch(script_path=script, old="Alpha", new="Beta", summary="s")
        apply_patch(p, conn, cwd=str(tmp_path))
        row = conn.execute(
            "SELECT title FROM slides WHERE deck_id = ? AND position = 1", (deck_id,)
        ).fetchone()
        assert row["title"] == "Beta"

    def test_ambiguous_old_text_rejected(self, conn, tmp_path):
        """When old text matches more than once, the file write (first-only) and
        the grid mirror (replace-all) would diverge, so the patch is rejected."""
        script, _ = self._seed_script_deck(conn, tmp_path, "a = 'Foo';\nb = 'Foo';\n")
        conn.commit()
        p = Patch(script_path=script, old="Foo", new="Bar", summary="s")
        ok, reason = validate_patch(p, conn)
        assert not ok
        assert "ambiguous" in reason
        with pytest.raises(ValueError, match="validation failed"):
            apply_patch(p, conn, cwd=str(tmp_path))
        # File must be untouched after a rejected apply.
        assert Path(script).read_text() == "a = 'Foo';\nb = 'Foo';\n"

    def test_unique_context_disambiguates(self, conn, tmp_path):
        script, _ = self._seed_script_deck(conn, tmp_path, "a = 'Foo';\nb = 'Foo';\n")
        conn.commit()
        p = Patch(script_path=script, old="a = 'Foo'", new="a = 'Bar'", summary="s")
        ok, reason = validate_patch(p, conn)
        assert ok, reason
        apply_patch(p, conn, cwd=str(tmp_path))
        assert Path(script).read_text() == "a = 'Bar';\nb = 'Foo';\n"

    def test_missing_script_file_rejected(self, conn, tmp_path):
        p = Patch(script_path=str(tmp_path / "gone.js"), old="x", new="y", summary="s")
        ok, reason = validate_patch(p, conn)
        assert not ok
        assert "not found" in reason

    def test_readonly_script_write_raises_clean_valueerror(self, conn, tmp_path, monkeypatch):
        """A read-only script path must surface a ValueError (→ 400), not an
        uncaught OSError (→ 500). Regression for the container read-only-fs
        crash on script-patch apply."""
        script, _ = self._seed_script_deck(conn, tmp_path, "title = 'Alpha';\n")
        conn.commit()
        p = Patch(script_path=script, old="Alpha", new="Beta", summary="s")

        real_write_text = Path.write_text

        def _deny_write(self, *args, **kwargs):
            if str(self) == script:
                raise OSError(30, "Read-only file system")
            return real_write_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", _deny_write)
        with pytest.raises(ValueError, match="read-only"):
            apply_patch(p, conn, cwd=str(tmp_path))


class TestThumbnailInvalidationOnEdit:
    """Applying / reverting a chat patch must invalidate the affected slide's
    thumbnail so the UI never shows a stale image after a content change."""

    def _seed_script_deck(self, conn, tmp_path, body):
        script = tmp_path / "deck.js"
        script.write_text(body, encoding="utf-8")
        cur = conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, source_script_path) VALUES (?,?,?,?)",
            ("script-deck", "/tmp/script-deck.pptx", "shash", str(script)),
        )
        return str(script), cur.lastrowid

    def test_slides_touched_by_script_patch(self, conn, tmp_path):
        from aippt.patch import slides_touched_by_patch

        script, deck_id = self._seed_script_deck(conn, tmp_path, "t = 'Alpha';\n")
        c1 = conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash) VALUES (?,?,?,?,?)",
            (deck_id, 1, "Alpha", "has Alpha inside", "sh1"),
        )
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash) VALUES (?,?,?,?,?)",
            (deck_id, 2, "Beta", "no match", "sh2"),
        )
        conn.commit()
        p = Patch(script_path=script, old="Alpha", new="Gamma", summary="s")
        touched = slides_touched_by_patch(p, conn)
        assert touched == [c1.lastrowid]

    def test_slides_touched_by_legacy_patch(self, conn, slide_id, tmp_path):
        from aippt.patch import slides_touched_by_patch

        p = Patch(slide_id=slide_id, field="title", old_text="Intro", new_text="Introduction")
        assert slides_touched_by_patch(p, conn) == [slide_id]

    def test_slides_touched_by_code_anchored_patch(self, conn, tmp_path):
        """Real LLM script patches wrap the changed text in code, e.g.
        ``addBulletSlide(deck, 'Benefits', [``. The raw ``old`` is never a
        substring of a rendered slide field, so matching must extract the
        changed *string literal* ('Benefits') and match that. Regression for the
        Check-3 prod failure where invalidation never fired on script decks."""
        from aippt.patch import slides_touched_by_patch

        script, deck_id = self._seed_script_deck(
            conn, tmp_path, "addBulletSlide(deck, 'Benefits', ['a','b']);\n"
        )
        c1 = conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash) VALUES (?,?,?,?,?)",
            (deck_id, 1, "Benefits", "", "sh1"),
        )
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash) VALUES (?,?,?,?,?)",
            (deck_id, 2, "Other", "", "sh2"),
        )
        conn.commit()
        p = Patch(
            script_path=script,
            old="addBulletSlide(deck, 'Benefits', [",
            new="addBulletSlide(deck, 'Why It Rocks', [",
            summary="rename",
        )
        # Precise: only the slide whose title matches the changed literal.
        assert slides_touched_by_patch(p, conn) == [c1.lastrowid]

    def test_slides_touched_coarse_fallback_when_no_literal_matches(self, conn, tmp_path):
        """When the changed text can't be located in any rendered slide field
        (e.g. content_text is empty and the edit is structural), fall back to
        invalidating every slide of the script's deck(s) — never stale."""
        from aippt.patch import slides_touched_by_patch

        script, deck_id = self._seed_script_deck(
            conn, tmp_path, "addImageSlide(deck, 'diagram.png');\n"
        )
        ids = []
        for pos in (1, 2, 3):
            c = conn.execute(
                "INSERT INTO slides (deck_id, position, title, content_text, content_hash) VALUES (?,?,?,?,?)",
                (deck_id, pos, f"Title {pos}", "", f"h{pos}"),
            )
            ids.append(c.lastrowid)
        conn.commit()
        # The literal 'diagram.png' / 'chart.png' appears in no slide field.
        p = Patch(
            script_path=script,
            old="addImageSlide(deck, 'diagram.png')",
            new="addImageSlide(deck, 'chart.png')",
            summary="swap image",
        )
        assert slides_touched_by_patch(p, conn) == sorted(ids)

    def test_apply_invalidates_thumbnail(self, conn, tmp_path):
        script, deck_id = self._seed_script_deck(conn, tmp_path, "t = 'Alpha';\n")
        c1 = conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash, "
            "image_path, image_content_hash) VALUES (?,?,?,?,?,?,?)",
            (deck_id, 1, "Alpha", "body", "sh1", "images/x/Slide1.png", "sh1"),
        )
        slide_id = c1.lastrowid
        conn.commit()

        mock_llm = MagicMock()
        mock_llm.model_config.supports_vision = False
        svc = ChatService(conn, mock_llm, db_cwd=str(tmp_path))
        conv_id = svc.create_conversation(deck_id, script_path=script)
        msg_id = svc._save_message(
            conv_id, "assistant", "ok", mode="edit",
            patch_json=json.dumps([
                {"script_path": script, "old": "Alpha", "new": "Beta", "summary": "s"}
            ]),
        )
        ok, reason = svc.apply_message_patch(msg_id)
        assert ok, reason

        row = conn.execute(
            "SELECT image_path, image_content_hash FROM slides WHERE id = ?", (slide_id,)
        ).fetchone()
        assert row["image_path"] is None
        assert row["image_content_hash"] is None

    def test_revert_invalidates_thumbnail(self, conn, tmp_path):
        script, deck_id = self._seed_script_deck(conn, tmp_path, "t = 'Alpha';\n")
        c1 = conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash, "
            "image_path, image_content_hash) VALUES (?,?,?,?,?,?,?)",
            (deck_id, 1, "Alpha", "body", "sh1", "images/x/Slide1.png", "sh1"),
        )
        slide_id = c1.lastrowid
        conn.commit()

        mock_llm = MagicMock()
        mock_llm.model_config.supports_vision = False
        svc = ChatService(conn, mock_llm, db_cwd=str(tmp_path))
        conv_id = svc.create_conversation(deck_id, script_path=script)
        msg_id = svc._save_message(
            conv_id, "assistant", "ok", mode="edit",
            patch_json=json.dumps([
                {"script_path": script, "old": "Alpha", "new": "Beta", "summary": "s"}
            ]),
        )
        assert svc.apply_message_patch(msg_id)[0]
        # A re-capture would repopulate the image; simulate that before revert.
        conn.execute(
            "UPDATE slides SET image_path = ?, image_content_hash = ? WHERE id = ?",
            ("images/x/Slide1.png", "sh-beta", slide_id),
        )
        conn.commit()

        ok, reason = svc.revert_message_patch(msg_id)
        assert ok, reason
        row = conn.execute(
            "SELECT image_path, image_content_hash FROM slides WHERE id = ?", (slide_id,)
        ).fetchone()
        assert row["image_path"] is None
        assert row["image_content_hash"] is None

    def test_apply_invalidates_thumbnail_code_anchored(self, conn, tmp_path):
        """End-to-end at the service level with a realistic code-anchored patch
        and a title-only slide (empty content_text) — the exact prod scenario
        from the Check-3 failure. Apply must invalidate the renamed slide's
        thumbnail via literal extraction."""
        body = "addBulletSlide(deck, 'Benefits of Code-Driven Decks', ['a','b']);\n"
        script, deck_id = self._seed_script_deck(conn, tmp_path, body)
        c1 = conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash, "
            "image_path, image_content_hash) VALUES (?,?,?,?,?,?,?)",
            (deck_id, 1, "Benefits of Code-Driven Decks", "", "sh1",
             "images/x/Slide1.png", "sh1"),
        )
        # A second, unrelated slide whose thumbnail must survive.
        c2 = conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash, "
            "image_path, image_content_hash) VALUES (?,?,?,?,?,?,?)",
            (deck_id, 2, "Other Slide", "", "sh2", "images/x/Slide2.png", "sh2"),
        )
        conn.commit()

        mock_llm = MagicMock()
        mock_llm.model_config.supports_vision = False
        svc = ChatService(conn, mock_llm, db_cwd=str(tmp_path))
        conv_id = svc.create_conversation(deck_id, script_path=script)
        msg_id = svc._save_message(
            conv_id, "assistant", "ok", mode="edit",
            patch_json=json.dumps([{
                "script_path": script,
                "old": "addBulletSlide(deck, 'Benefits of Code-Driven Decks', [",
                "new": "addBulletSlide(deck, 'Why Code-Driven Decks Rock', [",
                "summary": "rename",
            }]),
        )
        ok, reason = svc.apply_message_patch(msg_id)
        assert ok, reason

        r1 = conn.execute(
            "SELECT image_path, image_content_hash FROM slides WHERE id = ?", (c1.lastrowid,)
        ).fetchone()
        r2 = conn.execute(
            "SELECT image_path FROM slides WHERE id = ?", (c2.lastrowid,)
        ).fetchone()
        # Renamed slide invalidated; the unrelated slide keeps its thumbnail.
        assert r1["image_path"] is None
        assert r1["image_content_hash"] is None
        assert r2["image_path"] == "images/x/Slide2.png"


class TestEditHistoryMigration:
    def test_legacy_notnull_slide_id_is_relaxed(self, tmp_path):
        """A pre-existing DB with edit_history.slide_id NOT NULL is migrated to
        nullable without losing rows, and the migration is idempotent."""
        db_path = str(tmp_path / "legacy.db")
        raw = sqlite3.connect(db_path)
        raw.executescript(
            """
            CREATE TABLE slides (
                id INTEGER PRIMARY KEY, deck_id INT, position INT,
                title TEXT DEFAULT '', content_text TEXT DEFAULT '',
                content_hash TEXT DEFAULT '', notes TEXT DEFAULT ''
            );
            CREATE TABLE edit_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slide_id INTEGER NOT NULL REFERENCES slides(id) ON DELETE CASCADE,
                field TEXT NOT NULL, old_value TEXT, new_value TEXT,
                source TEXT NOT NULL DEFAULT 'web',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO slides (id, deck_id, position, title) VALUES (1, 1, 1, 'x');
            INSERT INTO edit_history (slide_id, field, old_value, new_value, source)
                VALUES (1, 'notes', 'a', 'b', 'web');
            """
        )
        raw.commit()
        raw.close()

        def slide_id_notnull(c):
            info = next(r for r in c.execute("PRAGMA table_info(edit_history)") if r[1] == "slide_id")
            return info[3]

        conn = get_db(db_path)
        assert slide_id_notnull(conn) == 0
        row = conn.execute("SELECT slide_id, field, old_value, new_value FROM edit_history").fetchone()
        assert (row["slide_id"], row["field"], row["old_value"], row["new_value"]) == (1, "notes", "a", "b")
        conn.close()

        # Re-open: migration must be a no-op the second time.
        conn2 = get_db(db_path)
        assert slide_id_notnull(conn2) == 0
        conn2.close()


# ---------------------------------------------------------------------------
# ChatService tests
# ---------------------------------------------------------------------------

class TestChatService:
    def _make_svc(self, conn, tmp_path):
        mock_llm = MagicMock()
        mock_llm.model_config.supports_vision = False
        return ChatService(conn, mock_llm, db_cwd=str(tmp_path))

    def test_create_conversation(self, conn, deck_id, tmp_path):
        svc = self._make_svc(conn, tmp_path)
        conv_id = svc.create_conversation(deck_id, "My conv")
        assert isinstance(conv_id, int)
        conv = svc.get_conversation(conv_id)
        assert conv["title"] == "My conv"
        assert conv["deck_id"] == deck_id

    def test_list_conversations(self, conn, deck_id, tmp_path):
        svc = self._make_svc(conn, tmp_path)
        svc.create_conversation(deck_id, "A")
        svc.create_conversation(deck_id, "B")
        convs = svc.list_conversations(deck_id)
        assert len(convs) == 2

    def test_delete_conversation(self, conn, deck_id, tmp_path):
        svc = self._make_svc(conn, tmp_path)
        conv_id = svc.create_conversation(deck_id, "to delete")
        ok = svc.delete_conversation(conv_id)
        assert ok
        assert svc.get_conversation(conv_id) is None

    def test_stream_reply_stores_messages(self, conn, deck_id, slide_id, tmp_path):
        mock_llm = MagicMock()
        mock_llm.model_config.supports_vision = False
        mock_llm.stream_text.return_value = iter(["Hello ", "world!"])
        svc = ChatService(conn, mock_llm, db_cwd=str(tmp_path))
        conv_id = svc.create_conversation(deck_id)

        chunks = list(svc.stream_reply(conv_id, "Hi there", slide_id=slide_id))
        text_chunks = [c for c in chunks if not c.startswith("[")]
        assert "".join(text_chunks) == "Hello world!"

        msgs = svc.get_messages(conv_id)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Hello world!"

    def test_stream_reply_proposes_patch_in_edit_mode(self, conn, deck_id, slide_id, tmp_path):
        mock_llm = MagicMock()
        mock_llm.model_config.supports_vision = False
        reply = (
            "I'll update the title.\n"
            f"```patch\nslide: {slide_id}\nfield: title\n---\nIntro\n===\nIntroduction\n```"
        )
        mock_llm.stream_text.return_value = iter([reply])
        svc = ChatService(conn, mock_llm, db_cwd=str(tmp_path))
        conv_id = svc.create_conversation(deck_id)

        events = list(svc.stream_reply(conv_id, "Rename the first slide", mode="edit"))
        patch_events = [e for e in events if e.startswith("[PATCH_PROPOSED:")]
        assert len(patch_events) == 1

        # Patch is proposed but NOT applied yet — title unchanged
        row = conn.execute("SELECT title FROM slides WHERE id = ?", (slide_id,)).fetchone()
        assert row["title"] == "Intro"

        # Extract msg_id from event and apply via service
        rest = patch_events[0][len("[PATCH_PROPOSED:"):]
        msg_id = int(rest.split(":")[0])
        ok, reason = svc.apply_message_patch(msg_id)
        assert ok, reason

        # Now the title should be updated
        row = conn.execute("SELECT title FROM slides WHERE id = ?", (slide_id,)).fetchone()
        assert row["title"] == "Introduction"

    def test_stream_reply_ask_mode_no_patch(self, conn, deck_id, slide_id, tmp_path):
        mock_llm = MagicMock()
        mock_llm.model_config.supports_vision = False
        reply = (
            "I'll update the title.\n"
            f"```patch\nslide: {slide_id}\nfield: title\n---\nIntro\n===\nIntroduction\n```"
        )
        mock_llm.stream_text.return_value = iter([reply])
        svc = ChatService(conn, mock_llm, db_cwd=str(tmp_path))
        conv_id = svc.create_conversation(deck_id)

        # In ask mode, even if LLM emits a patch block it is silently ignored
        events = list(svc.stream_reply(conv_id, "Rename the first slide", mode="ask"))
        patch_events = [e for e in events if e.startswith("[PATCH_PROPOSED:")]
        assert patch_events == []

        # Title unchanged
        row = conn.execute("SELECT title FROM slides WHERE id = ?", (slide_id,)).fetchone()
        assert row["title"] == "Intro"

    def test_cancel_token(self):
        tok = CancelToken()
        assert not tok.is_cancelled
        tok.cancel()
        assert tok.is_cancelled

    def test_edit_mode_upload_deck_proposes_slide_patch(self, conn, deck_id, slide_id, tmp_path):
        """An upload deck (no script_path) must round-trip a slide-field patch.

        Regression: edit mode used to steer the LLM toward a ```json script
        patch even when the conversation had no script, so Apply always failed
        validation with 'script file not found'. Upload decks should use the
        legacy slide-field patch path instead.
        """
        mock_llm = MagicMock()
        mock_llm.model_config.supports_vision = False
        reply = (
            "Renaming the slide.\n"
            f"```patch\nslide: {slide_id}\nfield: title\n---\nIntro\n===\nIntroduction\n```"
        )
        mock_llm.stream_text.return_value = iter([reply])
        svc = ChatService(conn, mock_llm, db_cwd=str(tmp_path))
        conv_id = svc.create_conversation(deck_id)  # no script_path

        events = list(svc.stream_reply(conv_id, "Rename the first slide", mode="edit"))
        patch_events = [e for e in events if e.startswith("[PATCH_PROPOSED:")]
        assert len(patch_events) == 1

        # The proposed patch is a legacy slide patch, not a script patch.
        rest = patch_events[0][len("[PATCH_PROPOSED:"):]
        msg_id, _, payload = rest.partition(":")
        payload = payload[:-1] if payload.endswith("]") else payload
        proposed = json.loads(payload)
        assert proposed[0]["slide_id"] == slide_id
        assert "script_path" not in proposed[0]

        ok, reason = svc.apply_message_patch(int(msg_id))
        assert ok, reason
        row = conn.execute("SELECT title FROM slides WHERE id = ?", (slide_id,)).fetchone()
        assert row["title"] == "Introduction"


class TestEditModeSystemPrompt:
    def test_script_deck_prompt_asks_for_json_script_patch(self):
        prompt = _system_prompt("edit", script_path="/app/examples/foo/foo.mjs")
        assert "/app/examples/foo/foo.mjs" in prompt
        assert "```json" in prompt

    def test_upload_deck_prompt_asks_for_slide_patch(self):
        prompt = _system_prompt("edit", script_path=None)
        # Steers to the legacy slide-field ```patch format, not a script patch.
        assert "```patch" in prompt
        assert "field:" in prompt
        assert "no source script" in prompt.lower()

    def test_ask_mode_forbids_patches(self):
        prompt = _system_prompt("ask", script_path=None)
        assert "read-only" in prompt.lower()


# ---------------------------------------------------------------------------
# Route-level smoke tests (in-process, no real LLM)
# ---------------------------------------------------------------------------

class TestChatRoutes:
    @pytest.fixture
    def app_client(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        from aippt.web.app import create_app

        db_file = str(tmp_path / "slides.db")
        conn = get_db(db_file)
        conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?,?,?,?)",
            ("route-deck", "/tmp/r.pptx", "def456", 0),
        )
        conn.commit()
        conn.close()

        app = create_app(db_path=db_file, images_dir=str(tmp_path / "images"))
        return TestClient(app), db_file

    def test_create_and_list_conversation(self, app_client):
        client, db_file = app_client
        deck_id = get_db(db_file).execute("SELECT id FROM decks LIMIT 1").fetchone()["id"]

        resp = client.post("/api/chat/conversations", json={"deck_id": deck_id, "title": "Test conv"})
        assert resp.status_code == 200
        conv_id = resp.json()["id"]

        resp2 = client.get(f"/api/chat/conversations?deck_id={deck_id}")
        assert resp2.status_code == 200
        assert any(c["id"] == conv_id for c in resp2.json())

    def test_get_conversation(self, app_client):
        client, db_file = app_client
        deck_id = get_db(db_file).execute("SELECT id FROM decks LIMIT 1").fetchone()["id"]
        resp = client.post("/api/chat/conversations", json={"deck_id": deck_id})
        conv_id = resp.json()["id"]

        resp2 = client.get(f"/api/chat/conversations/{conv_id}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert "conversation" in data
        assert "messages" in data

    def test_delete_conversation(self, app_client):
        client, db_file = app_client
        deck_id = get_db(db_file).execute("SELECT id FROM decks LIMIT 1").fetchone()["id"]
        resp = client.post("/api/chat/conversations", json={"deck_id": deck_id})
        conv_id = resp.json()["id"]

        del_resp = client.delete(f"/api/chat/conversations/{conv_id}")
        assert del_resp.status_code == 200

        get_resp = client.get(f"/api/chat/conversations/{conv_id}")
        assert get_resp.status_code == 404

    def test_rename_conversation(self, app_client):
        client, db_file = app_client
        deck_id = get_db(db_file).execute("SELECT id FROM decks LIMIT 1").fetchone()["id"]
        resp = client.post("/api/chat/conversations", json={"deck_id": deck_id, "title": "Old"})
        conv_id = resp.json()["id"]

        rename_resp = client.patch(f"/api/chat/conversations/{conv_id}", json={"title": "New Title"})
        assert rename_resp.status_code == 200

        get_resp = client.get(f"/api/chat/conversations/{conv_id}")
        assert get_resp.json()["conversation"]["title"] == "New Title"

    def test_view_only_blocks_chat(self, tmp_path):
        from fastapi.testclient import TestClient
        from aippt.web.app import create_app

        db_file = str(tmp_path / "vo.db")
        get_db(db_file).close()
        app = create_app(db_path=db_file, images_dir=str(tmp_path), view_only=True)
        client = TestClient(app)

        resp = client.post("/api/chat/conversations", json={"deck_id": 1})
        assert resp.status_code == 403
