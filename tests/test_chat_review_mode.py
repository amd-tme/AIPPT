"""Tests for review mode additions to aippt.chat."""
import json
from unittest.mock import MagicMock, patch

import pytest

from aippt.deck_review import ReviewResult, Severity
from aippt.chat import (
    ChatService,
    _system_prompt,
    _REVIEW_MODE_SYSTEM_PROMPT,
    _NOTES_FLOW_PROMPT,
)


# ---------------------------------------------------------------------------
# System prompt selection
# ---------------------------------------------------------------------------

def test_review_mode_selects_review_prompt():
    prompt = _system_prompt(mode="review")
    assert "[REVIEW_FINDINGS]" in prompt
    assert "actionable" in prompt.lower()


def test_ask_mode_selects_non_review_prompt():
    prompt = _system_prompt(mode="ask")
    assert "[REVIEW_FINDINGS]" not in prompt


def test_edit_mode_selects_non_review_prompt():
    prompt = _system_prompt(mode="edit")
    assert "[REVIEW_FINDINGS]" not in prompt


def test_review_prompt_contains_severity_levels():
    p = _REVIEW_MODE_SYSTEM_PROMPT.lower()
    assert "high" in p
    assert "medium" in p
    assert "low" in p


def test_notes_flow_prompt_mentions_slide_num():
    assert "slide_num" in _NOTES_FLOW_PROMPT or "null" in _NOTES_FLOW_PROMPT


# ---------------------------------------------------------------------------
# stream_reply review mode — REVIEW_COMPLETE sentinel emitted
# ---------------------------------------------------------------------------

def _make_chat_svc():
    conn = MagicMock()
    llm = MagicMock()
    llm.model = "test-model"

    conv_row = {"id": 1, "deck_id": 1, "model": "claude-sonnet-4-6"}
    slide_row = {"id": 10, "position": 1, "image_path": None, "notes": ""}

    def execute_side(sql, params=()):
        cur = MagicMock()
        if "FROM conversations" in sql or "FROM chat_conversations" in sql:
            cur.fetchone.return_value = conv_row
        elif "FROM slides" in sql and ("WHERE id" in sql or "WHERE s.id" in sql):
            cur.fetchone.return_value = slide_row
        elif "INSERT INTO chat_messages" in sql:
            cur.lastrowid = 42
        else:
            cur.fetchone.return_value = None
            cur.fetchall.return_value = []
        return cur

    conn.execute.side_effect = execute_side
    return ChatService(conn, llm, "/fake")


def test_stream_reply_review_emits_review_complete_sentinel():
    findings_block = json.dumps({"findings": [
        {"slide_num": 1, "severity": "high", "category": "overflow",
         "description": "overflow", "actionable": True}
    ]})
    raw_reply = f"Analysis.\n[REVIEW_FINDINGS]\n{findings_block}\n[/REVIEW_FINDINGS]"

    svc = _make_chat_svc()
    svc.llm.stream_text.return_value = iter([raw_reply])
    svc.llm.stream_text_with_image.return_value = iter([raw_reply])

    sentinels = []
    for chunk in svc.stream_reply(conversation_id=1, user_message="Review slide 1", mode="review"):
        if chunk.startswith("[REVIEW_COMPLETE:"):
            sentinels.append(chunk)

    assert len(sentinels) == 1
    inner = sentinels[0][len("[REVIEW_COMPLETE:"):-1]
    colon = inner.index(":")
    findings_json = json.loads(inner[colon + 1:])
    assert "findings" in findings_json
    assert len(findings_json["findings"]) == 1
    assert findings_json["findings"][0]["severity"] == "high"


# ---------------------------------------------------------------------------
# run_notes_flow_pass
# ---------------------------------------------------------------------------

def test_run_notes_flow_pass_returns_review_result():
    slides = [
        {"position": 1, "title": "Intro", "notes": "Speaker note for slide 1"},
        {"position": 2, "title": "Details", "notes": "Speaker note for slide 2"},
    ]
    conv_row = {"id": 1, "deck_id": 1, "model": "claude-sonnet-4-6"}

    conn = MagicMock()

    def execute_side(sql, params=()):
        cur = MagicMock()
        if "FROM conversations" in sql or "FROM chat_conversations" in sql:
            cur.fetchone.return_value = conv_row
        elif "FROM slides" in sql:
            cur.fetchall.return_value = slides
        else:
            cur.fetchone.return_value = None
            cur.fetchall.return_value = []
        return cur

    conn.execute.side_effect = execute_side

    findings_block = json.dumps({"findings": [
        {"slide_num": None, "severity": "medium", "category": "notes",
         "description": "Repetitive opening lines", "actionable": False}
    ]})
    raw_reply = f"Notes analysis.\n[REVIEW_FINDINGS]\n{findings_block}\n[/REVIEW_FINDINGS]"

    llm = MagicMock()
    llm.stream_text.return_value = iter([raw_reply])
    llm.model = "test-model"

    svc = ChatService(conn, llm, "/fake")
    result = svc.run_notes_flow_pass(conversation_id=1)

    assert isinstance(result, ReviewResult)
    assert len(result.findings) == 1
    assert result.findings[0].slide_num is None
    assert result.findings[0].severity == Severity.MEDIUM
    assert result.findings[0].actionable is False
