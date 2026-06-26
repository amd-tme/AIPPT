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
from aippt.chat import ChatService, CancelToken


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
