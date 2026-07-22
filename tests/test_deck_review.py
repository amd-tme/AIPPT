"""Tests for aippt.deck_review — findings model, parser, and auto-refine orchestrator."""
import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from aippt.deck_review import (
    Finding,
    RefineResult,
    ReviewResult,
    Severity,
    parse_review_output,
    run_auto_refine,
)


# ---------------------------------------------------------------------------
# parse_review_output
# ---------------------------------------------------------------------------

def _make_findings_block(findings: list) -> str:
    payload = json.dumps({"findings": findings})
    return f"Some preamble.\n[REVIEW_FINDINGS]\n{payload}\n[/REVIEW_FINDINGS]\nTrailing text."


def test_parse_valid_block():
    raw = _make_findings_block([
        {"slide_num": 2, "severity": "high", "category": "overflow",
         "description": "Text overflows", "actionable": True, "patch_hint": "shorten"},
        {"slide_num": None, "severity": "low", "category": "notes",
         "description": "Weak hook", "actionable": False},
    ])
    result = parse_review_output(raw, round_num=1, model_used="test-model")
    assert result.round_num == 1
    assert result.model_used == "test-model"
    assert len(result.findings) == 2

    f0 = result.findings[0]
    assert f0.slide_num == 2
    assert f0.severity == Severity.HIGH
    assert f0.category == "overflow"
    assert f0.actionable is True
    assert f0.patch_hint == "shorten"

    f1 = result.findings[1]
    assert f1.slide_num is None
    assert f1.severity == Severity.LOW
    assert f1.actionable is False


def test_parse_missing_block_returns_advisory():
    result = parse_review_output("No structured block here at all.", round_num=2)
    assert len(result.findings) == 1
    assert result.findings[0].actionable is False
    assert result.round_num == 2


def test_parse_malformed_json_returns_advisory():
    raw = "[REVIEW_FINDINGS]\nnot valid json\n[/REVIEW_FINDINGS]"
    result = parse_review_output(raw)
    assert len(result.findings) == 1
    assert result.findings[0].actionable is False


def test_parse_empty_findings_list():
    raw = _make_findings_block([])
    result = parse_review_output(raw)
    assert result.findings == []


# ---------------------------------------------------------------------------
# ReviewResult properties
# ---------------------------------------------------------------------------

def test_review_result_actionable_filter():
    findings = [
        Finding(slide_num=1, severity=Severity.HIGH, category="overflow",
                description="overflow", actionable=True),
        Finding(slide_num=2, severity=Severity.LOW, category="content",
                description="style", actionable=False),
    ]
    rr = ReviewResult(findings=findings)
    assert len(rr.actionable) == 1
    assert rr.actionable[0].slide_num == 1
    assert len(rr.advisory) == 1
    assert rr.advisory[0].slide_num == 2


# ---------------------------------------------------------------------------
# run_auto_refine — unit tests with all I/O mocked
# ---------------------------------------------------------------------------

def _make_db_conn(slide_rows=None):
    """Return a mock sqlite3 connection that returns preset rows."""
    conn = MagicMock()
    deck_row = {"source_script_path": "/fake/script.mjs"}
    slides = slide_rows or [
        {"id": 10, "position": 1, "title": "Intro"},
        {"id": 11, "position": 2, "title": "Details"},
    ]

    def execute_side_effect(sql, params=()):
        cursor = MagicMock()
        if "source_script_path" in sql:
            cursor.fetchone.return_value = deck_row
        elif "FROM slides" in sql:
            cursor.fetchall.return_value = slides
        elif "SELECT d.name" in sql:
            cursor.fetchone.return_value = {"name": "test-deck"}
        else:
            cursor.fetchone.return_value = None
            cursor.fetchall.return_value = []
        return cursor

    conn.execute.side_effect = execute_side_effect
    return conn


_ACTION_BLOCK = json.dumps({"findings": [
    {"slide_num": 1, "severity": "high", "category": "overflow",
     "description": "overflow", "actionable": True, "patch_hint": "shorten"}
]})
_NO_ACTION_BLOCK = json.dumps({"findings": [
    {"slide_num": 1, "severity": "low", "category": "content",
     "description": "looks fine", "actionable": False}
]})

_PATCH_TARGETS = [
    "aippt.catalog.get_db",
    "aippt.chat.ChatService",
    "aippt.thumbnails.invalidate_slides",
    "aippt.patch.apply_patch",
    "aippt.patch.validate_patch",
    "aippt.patch.extract_patches",
    "aippt.patch.slides_touched_by_patch",
]


@patch("aippt.catalog.get_db")
@patch("aippt.chat.ChatService")
@patch("aippt.thumbnails.invalidate_slides")
@patch("aippt.patch.apply_patch")
@patch("aippt.patch.validate_patch")
@patch("aippt.patch.extract_patches")
@patch("aippt.patch.slides_touched_by_patch")
def test_run_auto_refine_no_actionable_stops_immediately(
    mock_touched, mock_extract, mock_validate, mock_apply, mock_invalidate, MockChat, mock_get_db
):
    conn = _make_db_conn()
    mock_get_db.return_value = conn

    chat_instance = MagicMock()
    raw = f"[REVIEW_FINDINGS]\n{_NO_ACTION_BLOCK}\n[/REVIEW_FINDINGS]"
    chat_instance.stream_reply.return_value = iter([raw])
    chat_instance.run_notes_flow_pass.return_value = ReviewResult(findings=[], round_num=1)
    MockChat.return_value = chat_instance

    result = run_auto_refine(
        deck_id=1, conversation_id=5, db_path="/fake/slides.db",
        project_root="/fake", llm_client=MagicMock(), max_rounds=3,
    )

    assert result.rounds_completed == 1
    mock_apply.assert_not_called()


@patch("aippt.catalog.get_db")
@patch("aippt.chat.ChatService")
@patch("aippt.thumbnails.invalidate_slides")
@patch("aippt.patch.apply_patch")
@patch("aippt.patch.validate_patch")
@patch("aippt.patch.extract_patches")
@patch("aippt.patch.slides_touched_by_patch")
def test_run_auto_refine_stops_when_no_patches_extracted(
    mock_touched, mock_extract, mock_validate, mock_apply, mock_invalidate, MockChat, mock_get_db
):
    """If LLM returns actionable findings but no parseable patch, loop stops after round 1."""
    conn = _make_db_conn()
    mock_get_db.return_value = conn

    raw = f"[REVIEW_FINDINGS]\n{_ACTION_BLOCK}\n[/REVIEW_FINDINGS]"
    chat_instance = MagicMock()
    chat_instance.stream_reply.return_value = iter([raw])
    chat_instance.run_notes_flow_pass.return_value = ReviewResult(findings=[], round_num=1)
    MockChat.return_value = chat_instance

    mock_extract.return_value = []  # no patches → applied=0 → break

    result = run_auto_refine(
        deck_id=1, conversation_id=5, db_path="/fake/slides.db",
        project_root="/fake", llm_client=MagicMock(), max_rounds=2,
    )
    assert result.rounds_completed == 1
    mock_apply.assert_not_called()


@patch("aippt.catalog.get_db")
@patch("aippt.chat.ChatService")
@patch("aippt.thumbnails.invalidate_slides")
@patch("aippt.patch.apply_patch")
@patch("aippt.patch.validate_patch")
@patch("aippt.patch.extract_patches")
@patch("aippt.patch.slides_touched_by_patch")
def test_run_auto_refine_thumbnails_event_unblocks_loop(
    mock_touched, mock_extract, mock_validate, mock_apply, mock_invalidate, MockChat, mock_get_db
):
    """thumbnails_ready_event.wait() should be called; pre-set event unblocks immediately."""
    conn = _make_db_conn(slide_rows=[])  # no slides → no findings
    mock_get_db.return_value = conn

    chat_instance = MagicMock()
    chat_instance.stream_reply.return_value = iter([])
    chat_instance.run_notes_flow_pass.return_value = ReviewResult(findings=[], round_num=1)
    MockChat.return_value = chat_instance

    evt = threading.Event()
    evt.set()  # pre-set so wait() returns immediately

    result = run_auto_refine(
        deck_id=1, conversation_id=5, db_path="/fake/slides.db",
        project_root="/fake", llm_client=MagicMock(), max_rounds=1,
        thumbnails_ready_event=evt,
    )
    assert result.rounds_completed == 1


@patch("aippt.catalog.get_db")
@patch("aippt.chat.ChatService")
@patch("aippt.thumbnails.invalidate_slides")
@patch("aippt.patch.apply_patch")
@patch("aippt.patch.validate_patch")
@patch("aippt.patch.extract_patches")
@patch("aippt.patch.slides_touched_by_patch")
@patch("aippt.preview.Renderer")
@patch("os.makedirs")
def test_run_auto_refine_patches_applied_counted(
    mock_makedirs, MockRenderer, mock_touched, mock_extract, mock_validate,
    mock_apply, mock_invalidate, MockChat, mock_get_db
):
    conn = _make_db_conn(slide_rows=[{"id": 10, "position": 1, "title": "Slide 1"}])
    mock_get_db.return_value = conn

    # Mock renderer so re-render path doesn't hit disk
    renderer_instance = MagicMock()
    renderer_instance.render.return_value = MagicMock(success=True)
    MockRenderer.return_value = renderer_instance

    raw_review = f"[REVIEW_FINDINGS]\n{_ACTION_BLOCK}\n[/REVIEW_FINDINGS]"

    def stream_side_effect(conv_id, user_message, slide_id=None, mode="ask"):
        if mode == "review":
            return iter([raw_review])
        return iter(["no patch here"])

    chat_instance = MagicMock()
    chat_instance.stream_reply.side_effect = stream_side_effect
    chat_instance.run_notes_flow_pass.return_value = ReviewResult(findings=[], round_num=1)
    MockChat.return_value = chat_instance

    fake_patch = MagicMock()
    mock_extract.return_value = [fake_patch]
    mock_validate.return_value = (True, "ok")
    mock_touched.return_value = [10]

    result = run_auto_refine(
        deck_id=1, conversation_id=5, db_path="/fake/slides.db",
        project_root="/fake", llm_client=MagicMock(), max_rounds=1,
    )
    assert result.patches_applied == 1
    mock_apply.assert_called_once()
    mock_invalidate.assert_called_once_with([10], "/fake/slides.db")
