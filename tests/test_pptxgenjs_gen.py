"""Unit tests for aippt.pptxgenjs_gen — generator flow with mocked LLMClient."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from aippt.pptxgenjs_gen import generate_script, ScriptGenerationError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GOOD_SCRIPT = """\
import { createDeck, addTitleSlide, addBulletSlide, addClosingSlide } from '../lib/pptxgenjs-helpers.mjs';

const deck = await createDeck('themes/amd.yaml');

// ═══ Slide 1: My Talk ═══
addTitleSlide(deck, 'My Talk', 'An overview', 1);

// ═══ Slide 2: Key Points ═══
addBulletSlide(deck, 'Key Points', ['Point one', 'Point two'], 2, '');

// ═══ Slide 3: Thank You ═══
addClosingSlide(deck, 3, '');

await deck.save('output/my-talk.pptx');
"""

_BAD_SCRIPT = """\
import fs from 'fs';
eval('pwned');
const c = '#FF0000';
"""

_OUTLINE = """\
# My Talk
## Key Points
- Point one
- Point two
"""


def _make_client(return_value: str) -> MagicMock:
    client = MagicMock()
    # Wrap in ```javascript fences so _extract_code_block works
    client.generate_text.return_value = f"```javascript\n{return_value}\n```"
    return client


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_valid_script_written_to_disk(tmp_path):
    client = _make_client(_GOOD_SCRIPT)
    out = str(tmp_path / "deck.mjs")

    result = generate_script(_OUTLINE, out, client)

    assert result.strip() == _GOOD_SCRIPT.strip()
    assert Path(out).read_text(encoding="utf-8").strip() == _GOOD_SCRIPT.strip()
    client.generate_text.assert_called_once()


def test_prompt_contains_outline_text(tmp_path):
    client = _make_client(_GOOD_SCRIPT)
    out = str(tmp_path / "deck.mjs")

    generate_script(_OUTLINE, out, client)

    kwargs = client.generate_text.call_args.kwargs
    prompt_arg = kwargs.get("prompt", "")
    assert "My Talk" in prompt_arg
    assert "Key Points" in prompt_arg


def test_system_prompt_contains_critical_rules(tmp_path):
    client = _make_client(_GOOD_SCRIPT)
    out = str(tmp_path / "deck.mjs")

    generate_script(_OUTLINE, out, client)

    kwargs = client.generate_text.call_args.kwargs
    system_prompt = kwargs.get("system_prompt", "")
    assert "LAYOUT_WIDE" in system_prompt
    assert "NEVER" in system_prompt
    assert "cardShadow" in system_prompt


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

def test_invalid_script_triggers_retry(tmp_path):
    """First call returns invalid script, second call returns valid."""
    client = MagicMock()
    client.generate_text.side_effect = [
        f"```javascript\n{_BAD_SCRIPT}\n```",
        f"```javascript\n{_GOOD_SCRIPT}\n```",
    ]
    out = str(tmp_path / "deck.mjs")

    result = generate_script(_OUTLINE, out, client, max_retries=3)

    assert result.strip() == _GOOD_SCRIPT.strip()
    assert client.generate_text.call_count == 2


def test_all_retries_exhausted_raises(tmp_path):
    """All attempts return invalid script — should raise ScriptGenerationError."""
    client = MagicMock()
    client.generate_text.return_value = f"```javascript\n{_BAD_SCRIPT}\n```"
    out = str(tmp_path / "deck.mjs")

    with pytest.raises(ScriptGenerationError) as exc_info:
        generate_script(_OUTLINE, out, client, max_retries=2)

    assert client.generate_text.call_count == 2
    assert "attempt" in str(exc_info.value).lower()
    # File should NOT be written when all retries fail
    assert not Path(out).exists()


def test_progress_callback_called_on_retry(tmp_path):
    """Progress callback should be called on generation and retries."""
    client = MagicMock()
    client.generate_text.side_effect = [
        f"```javascript\n{_BAD_SCRIPT}\n```",
        f"```javascript\n{_GOOD_SCRIPT}\n```",
    ]
    out = str(tmp_path / "deck.mjs")
    progress_calls = []

    generate_script(
        _OUTLINE, out, client, max_retries=3,
        progress_callback=lambda step, detail: progress_calls.append((step, detail))
    )

    steps = [c[0] for c in progress_calls]
    assert "generate" in steps
    # Retry message should mention retry
    retry_details = [c[1] for c in progress_calls if "Retry" in c[1]]
    assert len(retry_details) >= 1


# ---------------------------------------------------------------------------
# Code-block extraction
# ---------------------------------------------------------------------------

def test_unfenced_response_still_works(tmp_path):
    """LLM response without fences should still be processed."""
    client = MagicMock()
    client.generate_text.return_value = _GOOD_SCRIPT  # no fences
    out = str(tmp_path / "deck.mjs")

    result = generate_script(_OUTLINE, out, client)
    assert result.strip() == _GOOD_SCRIPT.strip()


def test_theme_included_in_prompt(tmp_path):
    client = _make_client(_GOOD_SCRIPT)
    out = str(tmp_path / "deck.mjs")

    generate_script(_OUTLINE, out, client, theme="instinct")

    kwargs = client.generate_text.call_args.kwargs
    prompt_arg = kwargs.get("prompt", "")
    assert "instinct" in prompt_arg
