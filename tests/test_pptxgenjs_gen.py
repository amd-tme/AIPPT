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


def test_prompt_lists_every_brand_recipe():
    """Each recipe helper is documented and has a when-to-use row named by helper."""
    import re
    from aippt import recipes
    from aippt.pptxgenjs_gen import _SYSTEM_PROMPT

    for helper in recipes.helpers().values():
        assert re.search(rf"^{helper}\(", _SYSTEM_PROMPT, re.M), helper
        assert re.search(rf"^\|.*\| {helper} \|$", _SYSTEM_PROMPT, re.M), helper
    assert "{recipes}" not in _SYSTEM_PROMPT and "{recipe_rows}" not in _SYSTEM_PROMPT
    # Rows point at helpers, not recipe / directive ids
    assert "use hero_number" not in _SYSTEM_PROMPT and "(use addHeroNumber)" in _SYSTEM_PROMPT


_ICON_OUTLINE = """\
# Deck
Sub

# Why Instinct
- **Security** — secure by design
- **Performance** — leadership throughput
- **Open software** — ROCm is open source

# Key metrics
- **Throughput** — 1.3x — more tokens per GPU
- **TCO** — 40% — lower cost per token
- **Bandwidth** — 2x — more HBM bandwidth

# Endnotes
- **PERF-01** — Testing by AMD.
- **PERF-02** — Training throughput.
- **PERF-03** — vLLM, FP8.
"""


def test_prompt_lists_icons_for_feature_slides(tmp_path):
    from aippt import icons
    client = _make_client(_GOOD_SCRIPT)
    generate_script(_ICON_OUTLINE, str(tmp_path / "d.mjs"), client)
    prompt = client.generate_text.call_args.kwargs["prompt"]
    hints = prompt.split("Brand icons", 1)[1].split("Output ONLY", 1)[0]
    ids = [line.split(" — ")[0] for line in hints.strip().splitlines()[1:]]
    assert "security" in ids
    assert all(icons.get(i) for i in ids)
    # Only the feature slide feeds the list — not metrics or endnotes
    assert "bandwidth" not in ids


def test_prompt_has_no_icons_without_feature_items(tmp_path):
    client = _make_client(_GOOD_SCRIPT)
    generate_script(_OUTLINE, str(tmp_path / "d.mjs"), client)
    assert "Brand icons" not in client.generate_text.call_args.kwargs["prompt"]


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


# ---------------------------------------------------------------------------
# 30-3-30 decks
# ---------------------------------------------------------------------------

_TIER_OUTLINE = """\
# Widget Platform

## Widget Platform
A short tour

# 30 Seconds

## Widgets in one slide
- Reliability — fewer outages
- Speed — faster builds
<!-- notes
Open with the outage numbers.
-->

# 3 Minutes

## How it works
- Pilot with two teams
- Expand to the org

# 30 Minutes

## Architecture
- Control plane
- Data plane

## Thank you

# Appendix

## Resources
- Docs: example.com
"""

_TIER_TITLES = ["Widget Platform", "Widgets in one slide", "How it works",
                "Architecture", "Thank you", "Resources"]


def _unique_script(titles=_TIER_TITLES) -> str:
    """What the LLM writes for a tier outline: each slide once, numbered 1..K."""
    lines = ["import { createDeck, addTitleSlide, addStatCallout, addClosingSlide } "
             "from '../lib/pptxgenjs-helpers.mjs';", "",
             "const deck = await createDeck('themes/amd.yaml');", ""]
    for k, title in enumerate(titles, 1):
        lines.append(f"// ═══ Slide {k}: {title} ═══")
        if k == 1:
            lines.append(f"addTitleSlide(deck, `{title}`, `A short tour`, 1);")
        elif title == "Thank you":
            lines.append(f"addClosingSlide(deck, {k}, `Questions?`);")
        else:
            lines.append(f"addStatCallout(deck, `{title}`, [{{ value: `{k}`, label: `Slide {k}` }}], "
                         f"{k}, `notes for {k}`);")
        lines.append("")
    lines += ["const outDir = process.env.AIPPT_PREVIEW_OUT || 'output';",
              "await deck.save(`${outDir}/widgets.pptx`);"]
    return "\n".join(lines)


def test_tier_outline_llm_sees_each_slide_once(tmp_path):
    client = _make_client(_unique_script())
    generate_script(_TIER_OUTLINE, str(tmp_path / "d.mjs"), client)
    prompt = client.generate_text.call_args.kwargs["prompt"]
    assert "exactly 6 slides" in prompt
    assert "# 30 Seconds" not in prompt and "# Appendix" not in prompt
    assert "Open with the outage numbers." in prompt  # notes survive


def test_tier_outline_is_assembled_with_sections_dividers_and_repeats(tmp_path):
    import re
    script = generate_script(_TIER_OUTLINE, str(tmp_path / "d.mjs"), _make_client(_unique_script()))
    assert re.findall(r"^startSection\(deck, `([^`]*)`", script, re.M) == [
        "Intro", "30 Seconds", "3 Minutes", "30 Minutes", "Appendix"]
    titles = re.findall(r"^// ═══ Slide (\d+): (.*?) ═══", script, re.M)
    assert [int(n) for n, _ in titles] == list(range(1, len(titles) + 1))
    assert [t for _, t in titles] == [
        "Widget Platform",
        "Executive Overview (30 Sec)", "Widgets in one slide", "Closing",
        "Overview (3 Minute)", "Widgets in one slide", "How it works", "Closing",
        "Deep Dive (30 Minute)", "Widgets in one slide", "How it works", "Architecture", "Thank you",
        "Appendix", "Resources"]
    # Every helper's slideNum follows the deck order; slide text is untouched
    nums = re.findall(r"^add\w+\(deck, (?:.*, )?(\d+)(?:, `[^`]*`)?\);$", script, re.M)
    assert [int(n) for n in nums] == list(range(1, len(titles) + 1))
    assert script.count("value: `2`") == 3  # the repeated slide keeps its own text
    assert "startSection" in script.splitlines()[0] and "addTierDivider" in script.splitlines()[0]
    assert (tmp_path / "d.mjs").read_text() == script


def test_tier_outline_wrong_slide_count_is_retried(tmp_path):
    client = MagicMock()
    client.generate_text.side_effect = [_fenced(_unique_script(_TIER_TITLES[:-1])),
                                        _fenced(_unique_script())]
    generate_script(_TIER_OUTLINE, str(tmp_path / "d.mjs"), client)
    assert client.generate_text.call_count == 2
    assert "write exactly 6 slides" in client.generate_text.call_args_list[1].kwargs["prompt"]


def test_renumber_only_touches_slide_numbers():
    from aippt.pptxgenjs_gen import _renumber
    block = ("// ═══ Slide 3: X ═══\n"
             "addStatCallout(deck, `3 wins`, [{ value: `3`, label: `three` }], 3, `see slide 3`);\n")
    out = _renumber(block, 3, 11)
    assert out == ("// ═══ Slide 11: X ═══\n"
                   "addStatCallout(deck, `3 wins`, [{ value: `3`, label: `three` }], 11, `see slide 3`);\n")


def test_non_tier_outline_prompt_unchanged(tmp_path):
    client = _make_client(_GOOD_SCRIPT)
    generate_script(_OUTLINE, str(tmp_path / "d.mjs"), client)
    assert "exactly" not in client.generate_text.call_args.kwargs["prompt"]


def test_tier_render_repair_reassembles(tmp_path):
    from aippt.pptxgenjs_gen import generate_and_render
    client = MagicMock()
    fixed = _unique_script().replace("A short tour", "A fixed tour")
    client.generate_text.side_effect = [_fenced(_unique_script()), _fenced(fixed)]
    renderer = MagicMock()
    renderer.render.side_effect = _render_results(False, True)
    out = tmp_path / "d.mjs"

    assert generate_and_render(_TIER_OUTLINE, str(out), client, renderer, str(tmp_path)).success
    repair_prompt = client.generate_text.call_args_list[1].kwargs["prompt"]
    assert "startSection" not in repair_prompt  # the LLM only sees its own script
    assert "A fixed tour" in out.read_text() and "startSection" in out.read_text()


# ---------------------------------------------------------------------------
# Theme — the script loads the requested theme even if the LLM copies amd
# ---------------------------------------------------------------------------

_META_SCRIPT = _GOOD_SCRIPT.replace(
    "addClosingSlide(deck, 3, '');",
    'addClosingSlide(deck, 3, `[AIPPT-META]\n[{"operation":"create","theme":"amd"}]\n[/AIPPT-META]`);')


@pytest.mark.parametrize("theme", ["corp_black", "corp_white", "amd"])
def test_script_loads_requested_theme(tmp_path, theme):
    client = _make_client(_META_SCRIPT)
    script = generate_script(_OUTLINE, str(tmp_path / "d.mjs"), client, theme=theme)
    assert f"createDeck('themes/{theme}.yaml')" in script
    assert f'"theme":"{theme}"' in script
    assert script == (tmp_path / "d.mjs").read_text()
    assert f"createDeck('themes/{theme}.yaml')" in client.generate_text.call_args.kwargs["prompt"]


def test_unknown_theme_leaves_script_alone(tmp_path):
    script = generate_script(_OUTLINE, str(tmp_path / "d.mjs"), _make_client(_META_SCRIPT),
                             theme="no_such_theme")
    assert "createDeck('themes/amd.yaml')" in script and '"theme":"amd"' in script


def test_tier_script_loads_requested_theme(tmp_path):
    script = generate_script(_TIER_OUTLINE, str(tmp_path / "d.mjs"),
                             _make_client(_unique_script()), theme="corp_white")
    assert "createDeck('themes/corp_white.yaml')" in script
    assert "themes/amd.yaml" not in script


def test_repaired_script_loads_requested_theme(tmp_path):
    from aippt.pptxgenjs_gen import generate_and_render
    client = MagicMock()
    client.generate_text.side_effect = [_fenced(_GOOD_SCRIPT), _fenced(_GOOD_SCRIPT)]
    renderer = MagicMock()
    renderer.render.side_effect = _render_results(False, True)
    out = tmp_path / "d.mjs"
    assert generate_and_render(_OUTLINE, str(out), client, renderer, str(tmp_path),
                               theme="corp_black").success
    assert "createDeck('themes/corp_black.yaml')" in out.read_text()
