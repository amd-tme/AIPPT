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


def test_retry_prompt_includes_prior_failure_reasons(tmp_path):
    """On regenerate, the next prompt must contain the validation reasons."""
    client = MagicMock()
    client.generate_text.side_effect = [
        f"```javascript\n{_BAD_SCRIPT}\n```",
        f"```javascript\n{_GOOD_SCRIPT}\n```",
    ]
    out = str(tmp_path / "deck.mjs")

    generate_script(_OUTLINE, out, client, max_retries=3)

    # Second call's prompt should reference the fix-up instruction + a reason.
    second_prompt = client.generate_text.call_args_list[1].kwargs.get("prompt", "")
    assert "failed these checks" in second_prompt
    assert "-" in second_prompt  # at least one bulleted reason
    # First call's prompt should NOT contain the fix-up preamble.
    first_prompt = client.generate_text.call_args_list[0].kwargs.get("prompt", "")
    assert "failed these checks" not in first_prompt


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


def test_prompt_helper_signatures_match_library():
    """Every helper the LLM prompt documents exists with the same parameters, in order.

    Guards against the prompt drifting from lib/pptxgenjs-helpers.mjs (wrong
    argument lists make the LLM write calls that render broken slides).
    """
    import re
    from pathlib import Path
    from aippt.pptxgenjs_gen import _SYSTEM_PROMPT

    lib = (Path(__file__).resolve().parents[1] / "lib" / "pptxgenjs-helpers.mjs").read_text()

    def names(params):
        return [p.split("=")[0].strip() for p in params.split(",") if p.strip()]

    actual = {m.group(1): names(m.group(2)) for m in re.finditer(
        r"^export (?:async )?function (\w+)\(([^)]*)\)", lib, re.M)}
    documented = {m.group(1): [p.rstrip("?") for p in names(m.group(2))]
                  for m in re.finditer(r"^(\w+)\(([\w\s,?]*)\)", _SYSTEM_PROMPT, re.M)}
    assert len(documented) >= 30
    for name, params in documented.items():
        assert name in actual, f"prompt documents unknown helper {name}"
        assert params == actual[name], (
            f"{name}: prompt says ({', '.join(params)}), library has ({', '.join(actual[name])})")


# ---------------------------------------------------------------------------
# Retry context, truncation, render repair
# ---------------------------------------------------------------------------

def _fenced(script: str) -> str:
    return f"```javascript\n{script}\n```"


def test_retry_prompt_includes_previous_script(tmp_path):
    client = MagicMock()
    client.generate_text.side_effect = [_fenced(_BAD_SCRIPT), _fenced(_GOOD_SCRIPT)]
    generate_script(_OUTLINE, str(tmp_path / "d.mjs"), client)
    second_prompt = client.generate_text.call_args_list[1].kwargs["prompt"]
    assert "Your previous script" in second_prompt
    assert "eval('pwned')" in second_prompt


def test_truncated_response_is_retried(tmp_path):
    client = MagicMock()
    cut = "```javascript\n" + _GOOD_SCRIPT.split("await deck.save")[0]
    client.generate_text.side_effect = [cut, _fenced(_GOOD_SCRIPT)]
    generate_script(_OUTLINE, str(tmp_path / "d.mjs"), client)
    second_prompt = client.generate_text.call_args_list[1].kwargs["prompt"]
    assert "cut off" in second_prompt
    assert client.generate_text.call_count == 2


def _render_results(*successes):
    from aippt.preview import RenderResult
    return [
        RenderResult(success=True, pptx_path="out.pptx") if ok else
        RenderResult(success=False, stderr_tail="SyntaxError: Unexpected identifier 's'")
        for ok in successes
    ]


def test_render_failure_is_repaired_with_stderr(tmp_path):
    from aippt.pptxgenjs_gen import generate_and_render
    client = MagicMock()
    fixed = _GOOD_SCRIPT.replace("An overview", "A fixed overview")
    client.generate_text.side_effect = [_fenced(_GOOD_SCRIPT), _fenced(fixed)]
    renderer = MagicMock()
    renderer.render.side_effect = _render_results(False, True)
    out = tmp_path / "d.mjs"

    result = generate_and_render(_OUTLINE, str(out), client, renderer, str(tmp_path))

    assert result.success
    repair_prompt = client.generate_text.call_args_list[1].kwargs["prompt"]
    assert "SyntaxError: Unexpected identifier" in repair_prompt
    assert "Your previous script" in repair_prompt
    assert "A fixed overview" in out.read_text()


def test_repairs_are_bounded(tmp_path):
    from aippt.pptxgenjs_gen import generate_and_render
    client = MagicMock()
    client.generate_text.return_value = _fenced(_GOOD_SCRIPT)
    renderer = MagicMock()
    renderer.render.side_effect = _render_results(False, False, False)

    result = generate_and_render(_OUTLINE, str(tmp_path / "d.mjs"), client, renderer,
                                 str(tmp_path), max_repairs=2)

    assert not result.success
    assert renderer.render.call_count == 3
    assert client.generate_text.call_count == 3


def test_successful_first_render_makes_one_llm_call(tmp_path):
    from aippt.pptxgenjs_gen import generate_and_render
    client = _make_client(_GOOD_SCRIPT)
    renderer = MagicMock()
    renderer.render.side_effect = _render_results(True)
    result = generate_and_render(_OUTLINE, str(tmp_path / "d.mjs"), client, renderer, str(tmp_path))
    assert result.success and client.generate_text.call_count == 1


# ---------------------------------------------------------------------------
# Worked example embedded in the prompt
# ---------------------------------------------------------------------------

def test_prompt_example_is_valid_and_embedded():
    from aippt.pptxgenjs_gen import _EXAMPLE_SCRIPT, _SYSTEM_PROMPT
    from aippt.pptxgenjs_validate import validate_script
    assert validate_script(_EXAMPLE_SCRIPT) == (True, [])
    assert _EXAMPLE_SCRIPT in _SYSTEM_PROMPT
    assert "{example}" not in _SYSTEM_PROMPT


def test_prompt_example_renders(tmp_path):
    import shutil
    from aippt.preview import Renderer
    from aippt.web.routes import _stage_render_workspace
    from aippt.pptxgenjs_gen import _EXAMPLE_SCRIPT

    root = Path(__file__).resolve().parents[1]
    if not shutil.which("node") or Renderer(project_root=str(root))._find_node_modules() is None:
        pytest.skip("node / node_modules not available")
    job_id = f"pytest-example-{tmp_path.name}"
    try:
        script, out_dir = _stage_render_workspace(str(root / "uploads"), job_id, "example", str(root))
        Path(script).write_text(_EXAMPLE_SCRIPT, encoding="utf-8")
        result = Renderer(project_root=str(root)).render(script, out_dir)
        assert result.success, result.stderr_tail
        from pptx import Presentation
        assert len(Presentation(result.pptx_path).slides) == 9
    finally:
        shutil.rmtree(root / "uploads" / job_id, ignore_errors=True)
