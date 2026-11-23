"""Brand recipes (aippt/brand/recipes.json) in the no-LLM engine.

Recipes are picked automatically only on the recipes.json auto_themes (the
corp themes); on other themes they are used only from a LAYOUT: line, so
the amd output does not change.
"""
import re
import shutil
from pathlib import Path

import pytest

from aippt import recipes
from aippt.parser import _VALID_LAYOUT_TYPES
from aippt.pptxgenjs_direct import _EMITTERS, _LAYOUT_DIRECTIVES, _build_script
from aippt.pptxgenjs_validate import _HELPER_FUNCTIONS, validate_script

ROOT = Path(__file__).resolve().parents[1]
CORP = sorted(recipes.auto_themes())

SAMPLE = """\
# Instinct for Inference
Recipes sample

# Why customers choose Instinct
- **Memory** — 288 GB HBM3E holds large models on one GPU
- **Open software** — ROCm is open source end to end
- **Security** — Secure by design, from silicon to software
- **Performance** — leadership FP4 throughput

# Headline results
- 3x — faster training (vs. prior gen)
- 40% — lower cost per token
> Leadership across training and inference.
Source: AMD internal testing.
Endnote: PERF-01, PERF-02

# One number
- 1.3x — more tokens per second
Endnote: PERF-03

# Inference throughput by model
| Model | MI355X | B200 |
|---|---|---|
| Llama 3.1 405B | 1.3 | 1.0 |
| DeepSeek R1 | 1.2 | 1.0 |
Metric: Relative tokens/s (higher is better)
Date: Oct 2026

# MI355X at a glance
| Spec | MI355X | B200 |
|---|---|---|
| HBM | 288 GB | 192 GB |
| FP4 | 10 PF | 9 PF |

# Software support
| Capability | MI355X | H200 |
|---|---|---|
| Frameworks | | |
| PyTorch | ✓ | ✓ |
| JAX | partial | ✓ |

# Instinct roadmap
**2023**
- MI300X
- 192 GB HBM3

**2024**
- MI325X

**2025 (now)**
- MI355X
- CDNA 4

# Deployment workflow
**Pull**
- **Containers**
- vLLM image

**Serve**
- One command

**Scale**
- Kubernetes operator
> Production inference in an afternoon.

# Endnotes
- **PERF-01** — Testing by AMD as of Oct 2026.
- **PERF-02** — Training throughput.
- **PERF-03** — vLLM, FP8.

# Thank you
"""

AUTO = ['addTitleSlide', 'addIconFeatureGrid', 'addKpiTiles', 'addHeroNumber',
        'addCompetitiveChart', 'addSpecTable', 'addCheckMatrix', 'addTimeline',
        'addStageFlow', 'addEndnotesSlide', 'addClosingSlide']


def _calls(script):
    return re.findall(r"^(add[A-Z]\w+)\(deck", script, re.M)


def _slide(script, n):
    return re.search(rf"// ═══ Slide {n}:.*?(?=// ═══ Slide|const outDir)", script, re.S).group(0)


def test_recipes_json_is_consistent():
    ids = recipes.ids()
    assert len(ids) == len(set(ids)) == 10
    for r in recipes.recipes():
        assert {'id', 'helper', 'when', 'when_not', 'capacity', 'outline'} <= set(r)
        assert r['helper'] in _HELPER_FUNCTIONS
        assert r['helper'] in _EMITTERS
        assert _LAYOUT_DIRECTIVES[r['id']] == r['helper']
        assert r['id'] in _VALID_LAYOUT_TYPES
    assert recipes.auto_themes() == {'corp_black', 'corp_white'}
    assert all(line.startswith('- ') for line in recipes.index_lines().splitlines())


@pytest.mark.parametrize("theme", CORP)
def test_corp_themes_pick_recipes(theme):
    script = _build_script(SAMPLE, theme=theme)
    assert validate_script(script)[0]
    assert _calls(script) == AUTO


def test_amd_theme_keeps_todays_layouts():
    calls = _calls(_build_script(SAMPLE, theme='amd'))
    assert not set(calls) & set(recipes.helpers().values())
    assert calls[2] == 'addTakeawaySlide' and calls[4] == 'addTableSlide'


@pytest.mark.parametrize("rid", recipes.ids())
@pytest.mark.parametrize("theme", ['amd', 'corp_black'])
def test_recipe_directive_works_on_any_theme(rid, theme):
    outline = ("# Deck\nSub\n\n# Directed\nLAYOUT: " + rid +
               "\n- **Alpha** — 3x — first point\n- **Beta** — 2x — second point\n"
               "- **Gamma** — 40% — third point\nSource: Testing.\n")
    script = _build_script(outline, theme=theme)
    ok, reasons = validate_script(script)
    assert ok, reasons
    expected = recipes.helpers()[rid]
    if rid == 'competitive_chart':
        expected = 'addTableSlide'  # no numeric table — shown as a table instead
    assert _calls(script)[1] == expected


def test_recipe_slide_details():
    script = _build_script(SAMPLE, theme='corp_black')
    kpi = _slide(script, 3)
    assert "context: 'vs. prior gen'" in kpi and "highlight: true" in kpi
    assert "source: 'AMD internal testing.'" in kpi
    assert "endnote: ['PERF-01', 'PERF-02']" in kpi
    assert "takeaway: 'Leadership across training and inference.'" in kpi
    assert "endnote: 'PERF-03'" in _slide(script, 4)
    chart = _slide(script, 5)
    assert "{ name: 'MI355X', values: [1.3, 1.2] }" in chart
    assert "metric: 'Relative tokens/s (higher is better)'" in chart and "date: 'Oct 2026'" in chart
    assert "valueFormat: '#,##0.0'" in chart
    matrix = _slide(script, 7)
    assert "{ label: 'PyTorch', values: ['✓', '✓'], group: 'Frameworks' }" in matrix
    timeline = _slide(script, 8)
    assert "current: true" in timeline and "date: '2025'" in timeline and "caveat: true" in timeline
    flow = _slide(script, 9)
    assert "subhead: 'Containers'" in flow and "closing: 'Production inference in an afternoon.'" in flow
    assert "{ id: 'PERF-01', text: 'Testing by AMD as of Oct 2026.' }" in _slide(script, 10)


def test_icon_grid_needs_an_icon_for_every_item():
    outline = ("# Deck\nSub\n\n# Points\n- **Memory** — lots of HBM\n"
               "- **Zyzzyva** — no icon for this\n- **Security** — by design\n")
    assert _calls(_build_script(outline, theme='corp_black'))[1] == 'addCardGrid'


def test_icon_grid_source_goes_to_notes():
    outline = ("# Deck\nSub\n\n# Points\nLAYOUT: icon_grid\n- **Memory** — lots of HBM\n"
               "Source: AMD testing.\n")
    s = _slide(_build_script(outline, theme='corp_black'), 2)
    assert 'Source: AMD testing.' in s and 'source:' not in s


@pytest.mark.skipif(not shutil.which("node"), reason="node not available")
@pytest.mark.parametrize("theme", CORP + ['amd'])
def test_render_recipe_deck(tmp_path, theme):
    from pptx import Presentation
    from aippt.preview import Renderer
    from aippt.web.routes import _stage_render_workspace

    if Renderer(project_root=str(ROOT))._find_node_modules() is None:
        pytest.skip("node_modules not available")
    job_id = f"pytest-recipes-{theme}-{tmp_path.name}"
    uploads = ROOT / "uploads"
    try:
        script_path, out_dir = _stage_render_workspace(str(uploads), job_id, "recipes", str(ROOT))
        Path(script_path).write_text(_build_script(SAMPLE, theme=theme), encoding="utf-8")
        result = Renderer(project_root=str(ROOT)).render(script_path, out_dir)
        assert result.success, result.stderr_tail
        assert len(Presentation(result.pptx_path).slides) == len(AUTO)
    finally:
        shutil.rmtree(uploads / job_id, ignore_errors=True)
