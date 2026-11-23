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
    if directive == "competitive_chart":
        expected = "addTableSlide"  # no numeric table, so the data is shown as a table
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


# ---------------------------------------------------------------------------
# Phase 1 — no content is dropped
# ---------------------------------------------------------------------------

def _deck(*slides: str) -> str:
    """Build an outline with a title slide followed by the given slide bodies."""
    return "# Deck Title\nSubtitle line\n\n" + "\n\n".join(slides) + "\n"


def _slide_call(script: str, n: int) -> str:
    """Source for slide *n* (1-based) — from its marker to the next one."""
    m = re.search(rf"// ═══ Slide {n}:.*?(?=// ═══ Slide|const outDir)", script, re.S)
    return m.group(0)


def test_title_subtitle_uses_plain_text_line():
    assert "`Subtitle line`" in _slide_call(_build_script(_deck("# A\n- x\n- y")), 1)


def test_code_with_bullets_splits_into_two_slides():
    script = _build_script(_deck(
        "# Install\n- Needs Python 3.11\n- Needs Node 20\n```bash\npip install aippt\n```"
    ))
    calls = _calls(script)
    assert calls[1] != "addCodeSlide" and calls[2] == "addCodeSlide"
    assert "Needs Node 20" in _slide_call(script, 2)
    assert "pip install aippt" in _slide_call(script, 3)


def test_code_first_keeps_author_order():
    script = _build_script(_deck(
        "# Install\n```bash\npip install aippt\n```\n- Needs Python 3.11\n- Needs Node 20"
    ))
    assert _calls(script)[1] == "addCodeSlide"


def test_mostly_code_slide_stays_single_and_keeps_text_in_notes():
    script = _build_script(_deck("# Run It\nStart the server:\n```bash\naippt serve\n```"))
    assert _calls(script)[1:] == ["addCodeSlide"]
    assert "Start the server:" in _slide_call(script, 2)


def test_card_grid_keeps_all_six_items():
    items = "\n".join(f"- Feature {i}: does thing {i}" for i in range(1, 7))
    script = _build_script(_deck(f"# Features\n{items}"))
    assert _calls(script)[1] == "addCardGrid"
    for i in range(1, 7):
        assert f"does thing {i}" in script


def test_seven_plain_items_fall_back_to_bullets_not_truncated_cards():
    items = "\n".join(f"- Point number {i}" for i in range(1, 8))
    script = _build_script(_deck(f"# Points\n{items}"))
    assert _calls(script)[1] == "addBulletSlide"
    assert "Point number 7" in script


def test_sub_bullets_are_preserved():
    script = _build_script(_deck(
        "# Details\n- Parent one\n  - Child A\n  - Child B\n- Parent two\n- Parent three"
    ))
    assert _calls(script)[1] == "addBulletSlide"
    assert "{ text: 'Parent one', subs: ['Child A', 'Child B'] }" in script


def test_hyphenated_words_are_not_split_as_lead_ins():
    script = _build_script(_deck(
        "# Engines\n- python-pptx based output\n- pptxgenjs scripts"
    ))
    assert "title: 'python-pptx based output'" in script


def test_markdown_is_stripped_for_cards_but_lead_in_kept_for_bullets():
    cards = _build_script(_deck("# Cards\n- **Fast** — uses `cache`\n- **Safe** — sandboxed"))
    assert "title: 'Fast', body: 'uses cache'" in cards
    bullets = _build_script(_deck(
        "# B\nLAYOUT: bullet\n- **Fast** — uses `cache`\n- **Safe** — sandboxed"
    ))
    assert "'**Fast** — uses cache'" in bullets


def test_product_names_do_not_trigger_stat_callout():
    script = _build_script(_deck("# GPUs\n- MI300X has 192 GB\n- H100 has 80 GB\n- Both ship today"))
    assert "addStatCallout" not in _calls(script)


def test_stat_led_items_use_stat_callout_with_all_values():
    script = _build_script(_deck(
        "# Results\n- 3x faster training\n- 50% lower cost\n- 192 GB HBM3 memory\n- 2.4x throughput"
    ))
    assert _calls(script)[1] == "addStatCallout"
    for value in ("'3x'", "'50%'", "'192 GB'", "'2.4x'"):
        assert f"value: {value}" in script


def test_numbered_list_becomes_process_flow():
    script = _build_script(_deck("# Setup\n1. Clone\n2. Install\n3. Run"))
    assert _calls(script)[1] == "addProcessFlow"


def test_long_numbered_list_uses_two_col_numbered():
    items = "\n".join(f"{i}. Step {i}" for i in range(1, 9))
    script = _build_script(_deck(f"# Checklist\n{items}"))
    assert _calls(script)[1] == "addTwoColNumbered"
    assert "Step 8" in script and "1. Step" not in script


def test_two_column_honours_headers_and_column_break():
    script = _build_script(_deck(
        "# Options\nLAYOUT: two_column | Cloud | On-prem\n- Elastic\n- Managed\n- Pay as you go\n|||\n- Full control"
    ))
    call = _slide_call(script, 2)
    assert "'Cloud', 'On-prem'" in call
    left, right = re.findall(r"\[\n(.*?)\n  \]", call, re.S)
    assert "'Pay as you go'" in left and "'Full control'" not in left
    assert right.strip() == "'Full control',"


def test_grouped_content_keeps_headings():
    script = _build_script(_deck(
        "# Engines\n**Alpha**\n- a1\n- a2\n\n**Beta**\n- b1\n\n**Gamma**\n- g1"
    ))
    assert _calls(script)[1] == "addCardGrid"
    for word in ("'Alpha'", "'Beta'", "'Gamma'", "a2", "g1"):
        assert word in script


def test_dense_groups_split_into_continuation_slide():
    groups = "\n\n".join(
        f"**Group {g}**\n" + "\n".join(f"- item {g}.{i}" for i in range(5)) for g in range(3)
    )
    script = _build_script(_deck(f"# Dense\n{groups}"))
    assert "Dense (cont.)" in script
    assert "item 2.4" in script


def test_prose_goes_to_speaker_notes():
    script = _build_script(_deck("# Why\nThis intro sentence matters.\n- One thing\n- Another thing"))
    assert "This intro sentence matters." in _slide_call(script, 2)


def test_closing_content_kept_in_notes():
    script = _build_script(_deck("# Questions\n- Email platform@example.com"))
    assert _calls(script)[-1] == "addClosingSlide"
    assert "platform@example.com" in script


def test_section_dividers_are_numbered_in_order():
    script = _build_script(_deck("# Part One", "# Middle\n- a\n- b\n- c\n- d\n- e\n- f\n- g", "# Part Two", "# End\n- x\n- y\n- z\n- w\n- v\n- u\n- t"))
    assert re.findall(r"addSectionDivider\(deck, (\d+),", script) == ["1", "2"]


def test_horizontal_rules_are_ignored():
    script = _build_script(_deck("# A\n- one\n- two\n\n---"))
    assert "\n---\n\n---" not in script
    assert "'---'" not in script


def test_metadata_block_uses_real_newlines():
    from aippt.metadata import _META_PATTERN
    script = _build_script(SIMPLE_OUTLINE)
    notes = re.search(r"\[AIPPT-META\].*?\[/AIPPT-META\]", script, re.S).group(0)
    assert _META_PATTERN.search(notes)


def test_js_quoting_escapes_backslashes_and_newlines():
    script = _build_script(_deck("# Paths\nLAYOUT: bullet\n- C:\\temp\\out\n- it's fine"))
    assert "'C:\\\\temp\\\\out'" in script
    assert "'it\\'s fine'" in script
    assert validate_script(script)[0]


def test_three_col_content_directive():
    script = _build_script(_deck("# Pillars\nLAYOUT: three_col_content\n**A**\n- a\n**B**\n- b\n**C**\n- c"))
    assert _calls(script)[1] == "addThreeColContent"
    assert "heading: 'B', body: 'b'" in script


# ---------------------------------------------------------------------------
# Shared slide patterns (Phase 2)
# ---------------------------------------------------------------------------

def test_takeaway_line_with_points_uses_takeaway_slide():
    script = _build_script(_deck(
        "# Why Now\n> Memory is the bottleneck.\n- **Size** — models are huge\n- **Cost** — TCO matters"))
    assert _calls(script)[1] == "addTakeawaySlide"
    call = _slide_call(script, 2)
    assert "'Memory is the bottleneck.'" in call
    assert "'**Size** — models are huge'" in call
    assert validate_script(script)[0]


def test_takeaway_goes_to_notes_when_layout_cannot_show_it():
    script = _build_script(_deck("# Steps\nLAYOUT: numbered\n> Ship weekly.\n1. Plan\n2. Build\n3. Ship"))
    call = _slide_call(script, 2)
    assert call.startswith("// ═══ Slide 2") and "addProcessFlow(" in call
    assert "Ship weekly." in call.split("`", 3)[-1]  # in the notes argument


def test_markdown_table_becomes_table_slide_with_takeaway_and_source():
    script = _build_script(_deck(
        "# Compare\n> B wins.\n| Spec | A | B |\n|---|:-:|---:|\n| Mem | 1 GB | 2 GB |\n"
        "| BW | 3 | 4 |\nSource: spec sheets"))
    assert _calls(script)[1] == "addTableSlide"
    call = _slide_call(script, 2)
    assert "['Spec', 'A', 'B']" in call
    assert "['Mem', '1 GB', '2 GB']" in call and "['BW', '3', '4']" in call
    assert "takeaway: 'B wins.'" in call and "source: 'Source: spec sheets'" in call
    assert "|---" not in script
    assert validate_script(script)[0]


def test_table_without_separator_has_no_header():
    script = _build_script(_deck("# Grid\n| a | b |\n| c | d |"))
    assert "addTableSlide(deck, `Grid`, null," in script


def test_table_with_bullets_is_split_in_author_order():
    script = _build_script(_deck("# Data\n- first point\n- second point\n| h1 | h2 |\n|---|---|\n| x | y |"))
    calls = _calls(script)
    assert len(calls) == 3 and calls[2] == "addTableSlide"
    assert "first point" in _slide_call(script, 2) and "first point" not in _slide_call(script, 3)


def test_quote_slide_with_attribution_line():
    script = _build_script(_deck("# Voice\n> It just worked.\n— Jane, CTO"))
    assert _calls(script)[1] == "addQuoteSlide"
    assert "addQuoteSlide(deck, 'It just worked.', 'Jane, CTO'," in script


def test_quote_slide_attribution_inside_blockquote():
    script = _build_script(_deck("# Voice\n> It just worked.\n> — Jane, CTO"))
    assert "addQuoteSlide(deck, 'It just worked.', 'Jane, CTO'," in script


def test_agenda_title_uses_agenda_slide():
    script = _build_script(_deck("# Agenda\n- Intro\n- Results\n- Next steps"))
    assert _calls(script)[1] == "addAgendaSlide"
    assert "'Results'" in _slide_call(script, 2)


def test_roadmap_from_period_headings():
    script = _build_script(_deck("# What's Coming\n**Q1**\n- Alpha\n**Q2**\n- Beta\n- Gamma\n**Q3**\n- GA"))
    assert _calls(script)[1] == "addRoadmapSlide"
    assert "{ heading: 'Q2', items: ['Beta', 'Gamma'] }" in script


def test_roadmap_title_with_many_groups_is_not_split():
    groups = "\n".join(f"**Phase {i}**\n- a{i}\n- b{i}\n- c{i}" for i in range(1, 6))
    script = _build_script(_deck(f"# Product Roadmap\n{groups}"))
    assert _calls(script)[1:] == ["addRoadmapSlide"]


def test_disclaimer_title_uses_disclaimer_slide():
    script = _build_script(_deck("# Disclaimer\nThis is subject to change.\nAll rights reserved."))
    assert _calls(script)[1] == "addDisclaimerSlide"
    assert "This is subject to change.\nAll rights reserved." in script


@pytest.mark.parametrize("name,helper", [
    ("agenda", "addAgendaSlide"), ("quote", "addQuoteSlide"), ("roadmap", "addRoadmapSlide"),
    ("table", "addTableSlide"), ("takeaway", "addTakeawaySlide"), ("disclaimer", "addDisclaimerSlide"),
])
def test_pattern_layout_directives(name, helper):
    assert _LAYOUT_DIRECTIVES[name] == helper
    script = _build_script(_deck(f"# Slide\nLAYOUT: {name}\n- **Q1** — one\n- **Q2** — two"))
    assert _calls(script)[1] == helper
    assert validate_script(script)[0]


PATTERNS_OUTLINE = """\
# Patterns Deck
Subtitle

# Agenda
- One
- Two
- Three

# Why
> The point.
- **A** — first
- **B** — second

# Numbers
> B is bigger.
| Spec | A | B |
|---|---|---|
| Mem | 1 | 2 |

# Voice
> Great product.
— Someone

# Roadmap
**2026**
- Alpha
**2027**
- Beta

# Legal Notice
Subject to change.
"""


@pytest.mark.skipif(not _node_available(), reason="node / node_modules not available")
def test_render_shared_patterns(tmp_path):
    from pptx import Presentation
    from aippt.preview import Renderer
    from aippt.web.routes import _stage_render_workspace

    job_id = f"pytest-direct-patterns-{tmp_path.name}"
    uploads = PROJECT_ROOT / "uploads"
    try:
        script_path, out_dir = _stage_render_workspace(
            str(uploads), job_id, "patterns", str(PROJECT_ROOT))
        Path(script_path).write_text(_build_script(PATTERNS_OUTLINE), encoding="utf-8")
        result = Renderer(project_root=str(PROJECT_ROOT)).render(script_path, out_dir)
        assert result.success, result.stderr_tail
        prs = Presentation(result.pptx_path)
        assert len(prs.slides) == 7
        texts = [" ".join(sh.text_frame.text for sh in s.shapes if sh.has_text_frame) for s in prs.slides]
        assert "The point." in texts[2]
        assert any(sh.has_table for sh in prs.slides[3].shapes)
        assert "Great product." in texts[4]
    finally:
        shutil.rmtree(uploads / job_id, ignore_errors=True)


# ---------------------------------------------------------------------------
# Brand slides (hero / product title, section intro, statement, proof point,
# feature list) — opt-in by LAYOUT: directive; the default title stays put
# ---------------------------------------------------------------------------

BRAND_OUTLINE = """\
# ROCm 7: Open Software for AI
LAYOUT: product_title
The open AI stack for AMD Instinct GPUs
Presenter: Jane Doe
November 2026

# Agenda
- Why open
- Proof
- What's new

# Why Open Matters
LAYOUT: section_intro
Customers want choice.

# Open Wins
LAYOUT: statement
> Open moves faster
Developers pick what runs first.
- 2M+ models run on ROCm
  - Source: Example Research
- Day-0 model support

# Throughput
LAYOUT: proof_point
> ROCm 7 is faster
Example workload.
- **ROCm 6** — 1,000 tok/s
- **ROCm 7** — 3,500 tok/s

# What's New
LAYOUT: feature_list
> Built for scale
- **Inference** — disaggregated serving
  - vLLM and SGLang
- **Datatypes** — FP4 and FP6
"""


def test_default_title_unchanged_without_directive():
    script = _build_script(_deck("# Agenda\n- a\n- b\n- c"))
    assert _calls(script)[:2] == ["addTitleSlide", "addAgendaSlide"]
    assert "image:" not in _slide_call(script, 2)


def test_brand_outline_validates_and_uses_brand_helpers():
    script = _build_script(BRAND_OUTLINE)
    ok, reasons = validate_script(script)
    assert ok, reasons
    assert _calls(script) == [
        "addProductTitleSlide", "addAgendaSlide", "addSectionIntroSlide",
        "addStatementSlide", "addProofPointSlide", "addFeatureListSlide",
    ]


def test_product_title_infers_product_and_presenter():
    title = _slide_call(_build_script(BRAND_OUTLINE), 1)
    assert "product: 'ROCm'" in title
    assert "presenter: 'Jane Doe'" in title
    assert "November 2026" in title  # no date slot → kept in notes


def test_hero_title_gets_date_option():
    script = _build_script("# Our Strategy\nLAYOUT: hero_title\nWinning together\nJune 2026\n\n# Next\n- a\n")
    title = _slide_call(script, 1)
    assert "addHeroTitleSlide" in title and "date: 'June 2026'" in title
    assert "'Winning together'" in title


def test_brand_deck_agenda_uses_photo_variant():
    agenda = _slide_call(_build_script(BRAND_OUTLINE), 2)
    assert "image: ''" in agenda and "label: 'ROCm 7: Open Software for AI'" in agenda


def test_statement_evidence_keeps_sources():
    call = _slide_call(_build_script(BRAND_OUTLINE), 4)
    assert "'Open moves faster', 'Developers pick what runs first.'" in call
    assert "source: 'Source: Example Research'" in call
    assert "{ text: 'Day-0 model support' }" in call


def test_proof_point_computes_multiple():
    call = _slide_call(_build_script(BRAND_OUTLINE), 5)
    assert "before: { value: '1,000 tok/s', label: 'ROCm 6' }" in call
    assert "multiple: '3.5X'" in call
    assert "label: 'Throughput'" in call


def test_feature_list_uses_deck_product():
    call = _slide_call(_build_script(BRAND_OUTLINE), 6)
    assert "heading: 'Inference', lines: ['disaggregated serving', 'vLLM and SGLang']" in call
    assert "product: 'ROCm'" in call


@pytest.mark.skipif(not _node_available(), reason="node / node_modules not available")
def test_render_brand_slides(tmp_path):
    from pptx import Presentation
    from aippt.preview import Renderer
    from aippt.web.routes import _stage_render_workspace

    job_id = f"pytest-direct-brand-{tmp_path.name}"
    uploads = PROJECT_ROOT / "uploads"
    try:
        script_path, out_dir = _stage_render_workspace(
            str(uploads), job_id, "brand", str(PROJECT_ROOT))
        Path(script_path).write_text(_build_script(BRAND_OUTLINE), encoding="utf-8")
        result = Renderer(project_root=str(PROJECT_ROOT)).render(script_path, out_dir)
        assert result.success, result.stderr_tail
        prs = Presentation(result.pptx_path)
        assert len(prs.slides) == 6
        texts = [" ".join(sh.text_frame.text for sh in s.shapes if sh.has_text_frame) for s in prs.slides]
        assert "3.5X" in texts[4]
        assert "Source: Example Research" in texts[3]
        # Photo agenda + product render on the title
        assert any(sh.shape_type == 13 for sh in prs.slides[1].shapes)
    finally:
        shutil.rmtree(uploads / job_id, ignore_errors=True)


@pytest.mark.skipif(not _node_available(), reason="node / node_modules not available")
def test_render_disclaimer_scales_text(tmp_path):
    """Short notices get large type; long legal text flows into two columns."""
    from pptx import Presentation
    from aippt.preview import Renderer
    from aippt.web.routes import _stage_render_workspace

    para = ("AMD reserves the right to revise this information and to make changes from time "
            "to time to the content hereof without obligation of AMD to notify any person.")
    outline = ("# Deck\nSubtitle\n\n# Disclaimer\nLAYOUT: disclaimer\nExample data for illustration only.\n\n"
               "# Legal Notices\nLAYOUT: disclaimer\n" + "\n\n".join([para] * 24) + "\n")
    job_id = f"pytest-direct-disclaimer-{tmp_path.name}"
    uploads = PROJECT_ROOT / "uploads"
    try:
        script_path, out_dir = _stage_render_workspace(
            str(uploads), job_id, "disc", str(PROJECT_ROOT))
        Path(script_path).write_text(_build_script(outline), encoding="utf-8")
        result = Renderer(project_root=str(PROJECT_ROOT)).render(script_path, out_dir)
        assert result.success, result.stderr_tail
        prs = Presentation(result.pptx_path)

        def body_boxes(slide):
            return [sh for sh in slide.shapes if sh.has_text_frame and len(sh.text_frame.text) > 30]

        def size(shape):
            return shape.text_frame.paragraphs[0].runs[0].font.size.pt

        short, long_ = body_boxes(prs.slides[1]), body_boxes(prs.slides[2])
        assert len(short) == 1 and size(short[0]) == 18
        assert len(long_) == 2 and 9 <= size(long_[0]) < 18
    finally:
        shutil.rmtree(uploads / job_id, ignore_errors=True)


# ---------------------------------------------------------------------------
# 30-3-30 decks
# ---------------------------------------------------------------------------

TIER_OUTLINE = """\
# Widget Platform

## Widget Platform
A short tour

# 30 Seconds

## Widgets in one slide
- Reliability — fewer outages
- Speed — faster builds
- Cost — lower spend

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


def _sections(script):
    return re.findall(r'^startSection\(deck, `([^`]*)`', script, re.M)


def test_tier_outline_builds_sections_dividers_and_repeats():
    script = _build_script(TIER_OUTLINE)
    assert validate_script(script) == (True, [])
    sections = _sections(script)
    assert sections == ['Intro', '30 Seconds', '3 Minutes', '30 Minutes', 'Appendix']
    dividers = re.findall(r'^addTierDivider\(deck, `([^`]*)`, `([^`]*)`', script, re.M)
    assert dividers == [('Executive Overview (30 Sec)', 'Widget Platform'),
                        ('Overview (3 Minute)', 'Widget Platform'),
                        ('Deep Dive (30 Minute)', 'Widget Platform'),
                        ('Appendix', '')]
    # One title slide (the author's own), not a synthetic duplicate
    assert script.count('addTitleSlide(deck') == 1 and 'A short tour' in script
    # Earlier tiers are repeated: 30s slide x3, 3m slide x2
    assert script.count('`Widgets in one slide`') == 3
    assert script.count('`How it works`') == 2
    # A closing slide ends each timed tier; the author's "Thank you" is the last one
    assert script.count('addClosingSlide(deck') == 3
    nums = [int(n) for n in re.findall(r'^// ═══ Slide (\d+):', script, re.M)]
    assert nums == list(range(1, len(nums) + 1))


def test_tier_no_repeat_directive():
    outline = TIER_OUTLINE.replace('# 3 Minutes\n', '# 3 Minutes\nTIER: no-repeat\n')
    script = _build_script(outline)
    assert 'TIER' not in script
    assert script.count('`Widgets in one slide`') == 2  # 30s tier + 30m repeat only
    assert script.count('`How it works`') == 2


def test_tier_names_vary():
    outline = TIER_OUTLINE.replace('# 30 Seconds', '# Executive Overview (30 Sec)') \
        .replace('# 3 Minutes', '# 3 Min').replace('# 30 Minutes', '# Deep Dive (30 Mins)')
    sections = _sections(_build_script(outline))
    assert sections == ['Intro', '30 Seconds', '3 Minutes', '30 Minutes', 'Appendix']


def test_non_tier_outlines_unchanged():
    # One timed heading or an appendix alone is not a 30-3-30 deck
    outline = "# Deck\n\n## Intro\n- a\n- b\n\n# 30 Minutes\n\n## Topic\n- c\n- d\n\n# Appendix\n\n## More\n- e\n"
    script = _build_script(outline)
    assert 'startSection' not in script and 'addTierDivider' not in script
    assert 'startSection' not in _build_script(SIMPLE_OUTLINE)


def test_tier_outline_without_deck_title_uses_first_slide():
    outline = TIER_OUTLINE.split('# 30 Seconds', 1)[1]
    script = _build_script('# 30 Seconds' + outline)
    assert re.search(r'^addTitleSlide\(deck, `Widgets in one slide`', script, re.M)


@pytest.mark.skipif(not _node_available(), reason="node / node_modules not available")
def test_render_tier_deck_has_powerpoint_sections(tmp_path):
    import zipfile
    from aippt.preview import Renderer
    from aippt.web.routes import _stage_render_workspace

    job_id = f"pytest-direct-tiers-{tmp_path.name}"
    uploads = PROJECT_ROOT / "uploads"
    try:
        script_path, out_dir = _stage_render_workspace(
            str(uploads), job_id, "tiers", str(PROJECT_ROOT))
        generate_script(TIER_OUTLINE, script_path)
        result = Renderer(project_root=str(PROJECT_ROOT)).render(script_path, out_dir)
        assert result.success, result.stderr_tail
        xml = zipfile.ZipFile(result.pptx_path).read('ppt/presentation.xml').decode()
        names = re.findall(r'<p14:section name="([^"]+)"', xml)
        assert names == ['Intro', '30 Seconds', '3 Minutes', '30 Minutes', 'Appendix']
        # Every slide sits in a section
        assert len(re.findall(r'<p14:sldId ', xml)) == len(re.findall(r'<p:sldId ', xml))
    finally:
        shutil.rmtree(uploads / job_id, ignore_errors=True)
