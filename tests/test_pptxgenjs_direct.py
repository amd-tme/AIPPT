"""Tests for the deterministic (no-LLM) pptxgenjs engine.

Unit tests check layout selection and that every emitted script passes
``validate_script``. The render tests run the script through Node and
skip when node / node_modules are unavailable.
"""
import re
import shutil
from pathlib import Path

import pytest

from aippt.pptxgenjs_direct import (
    _LAYOUT_DIRECTIVES,
    _build_script,
    generate_script,
)
from aippt.pptxgenjs_validate import validate_script

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SIMPLE_OUTLINE = """\
# Widget Platform
A short tour

# Why Widgets
- Reliability: fewer outages in production
- Speed: faster builds for every team
- Cost: lower spend per workload

# Rollout Plan
- Pilot with two teams
- Expand to the org
- Retire the legacy stack
- Review results
- Publish the playbook

# Questions
- Contact the platform team
"""

HIERARCHICAL_OUTLINE = """\
# Introduction
## Welcome
- About the team
- Meeting objectives

# Results
## Revenue
- Total revenue grew
- Margins improved
"""


def _calls(script: str) -> list:
    """Helper calls in emission order, e.g. ['addTitleSlide', 'addBulletSlide']."""
    return re.findall(r"^(add[A-Z]\w+)\(deck", script, re.M)


def _imports(script: str) -> set:
    m = re.search(r"import \{(.+?)\} from", script)
    return {name.strip() for name in m.group(1).split(",")}


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_simple_outline_one_slide_per_h1():
    script = _build_script(SIMPLE_OUTLINE)
    calls = _calls(script)
    assert len(calls) == 4
    assert calls[0] == "addTitleSlide"


def test_hierarchical_outline_prepends_title_slide():
    calls = _calls(_build_script(HIERARCHICAL_OUTLINE))
    # synthetic title slide + one slide per H2
    assert len(calls) == 3
    assert calls[0] == "addTitleSlide"


def test_last_slide_with_closing_keyword_is_closing():
    assert _calls(_build_script(SIMPLE_OUTLINE))[-1] == "addClosingSlide"


def test_script_passes_validation():
    ok, reasons = validate_script(_build_script(SIMPLE_OUTLINE))
    assert ok, reasons


def test_every_called_helper_is_imported():
    script = _build_script(SIMPLE_OUTLINE)
    assert set(_calls(script)) <= _imports(script)


def test_empty_outline_raises(tmp_path):
    from aippt.pptxgenjs_direct import ScriptGenerationError
    with pytest.raises(ScriptGenerationError):
        generate_script("", str(tmp_path / "x.mjs"))


def test_generate_script_writes_file(tmp_path):
    out = tmp_path / "deck.mjs"
    script = generate_script(SIMPLE_OUTLINE, str(out))
    assert out.read_text(encoding="utf-8") == script


# ---------------------------------------------------------------------------
# LAYOUT: directives — every supported directive must produce a valid script
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("directive", sorted(_LAYOUT_DIRECTIVES))
def test_layout_directive_produces_valid_script(directive):
    outline = (
        "# Deck Title\nSubtitle\n\n"
        f"# Directed Slide\nLAYOUT: {directive}\n"
        "- First item\n- Second item\n- Third item\n"
    )
    script = _build_script(outline)
    ok, reasons = validate_script(script)
    assert ok, reasons
    assert set(_calls(script)) <= _imports(script)
    expected = _LAYOUT_DIRECTIVES[directive]
    if directive == "diagram":
        expected = "addBulletSlide"  # no IMAGE: given, so nothing to diagram
    assert _calls(script)[1] == expected


def test_diagram_directive_with_image_uses_image_layout():
    outline = (
        "# Deck Title\nSubtitle\n\n"
        "# Architecture\nLAYOUT: diagram\nIMAGE: images/arch.png\n- Service mesh\n"
    )
    script = _build_script(outline)
    assert validate_script(script)[0]
    assert _calls(script)[1] in ("addImageSlide", "addImageBulletsSlide")


# ---------------------------------------------------------------------------
# Render through Node (integration)
# ---------------------------------------------------------------------------

def _node_available() -> bool:
    if not shutil.which("node"):
        return False
    from aippt.preview import Renderer
    return Renderer(project_root=str(PROJECT_ROOT))._find_node_modules() is not None


@pytest.mark.skipif(not _node_available(), reason="node / node_modules not available")
def test_render_produces_pptx(tmp_path):
    from pptx import Presentation
    from aippt.preview import Renderer
    from aippt.web.routes import _stage_render_workspace

    # Node's permission model only allows reads under the project root, so
    # stage in the (gitignored) repo uploads/ dir like the web route does
    job_id = f"pytest-direct-{tmp_path.name}"
    uploads = PROJECT_ROOT / "uploads"
    try:
        script_path, out_dir = _stage_render_workspace(
            str(uploads), job_id, "Direct Test", str(PROJECT_ROOT)
        )
        generate_script(SIMPLE_OUTLINE, script_path)
        result = Renderer(project_root=str(PROJECT_ROOT)).render(script_path, out_dir)
        assert result.success, result.stderr_tail
        assert len(Presentation(result.pptx_path).slides) == 4
    finally:
        shutil.rmtree(uploads / job_id, ignore_errors=True)
