"""Golden test: the existing AMD pptxgenjs layouts must not change.

Renders one slide per existing helper with the AMD theme and compares a
fingerprint of every shape (geometry, text, fonts, colours, image bytes)
against tests/fixtures/amd_layouts_golden.json.

New themes and layouts must be additive. If a change to one of these
layouts is genuinely intended, regenerate the fixture with:

    AIPPT_UPDATE_GOLDEN=1 venv/bin/python -m pytest tests/test_amd_layouts_golden.py
"""
import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).parent / "fixtures" / "amd_layouts_golden.json"

SCRIPT = """\
import { createDeck, cardShadow, addTitleSlide, addBulletSlide, addCardGrid,
  addTwoColumn, addStatCallout, addProcessFlow, addCodeSlide, addSectionDivider,
  addTitleAlt, addSectionContent, addTwoColNumbered, addThreeColContent,
  addClosingSlide } from '../lib/pptxgenjs-helpers.mjs';

const deck = await createDeck('themes/amd.yaml');
addTitleSlide(deck, 'Golden Title', 'Golden subtitle', 1);
addBulletSlide(deck, 'Bullets', ['Alpha point', 'Beta point', 'Gamma point'], 2, 'n');
addCardGrid(deck, 'Cards', [
  { title: 'One', body: 'First card', shadow: cardShadow(deck.theme) },
  { title: 'Two', body: 'Second card', shadow: cardShadow(deck.theme) },
  { title: 'Three', body: 'Third card', shadow: cardShadow(deck.theme) },
], 3, 'n');
addTwoColumn(deck, 'Compare', 'Left', 'Right', ['L1', 'L2'], ['R1', 'R2'], 4, 'n');
addStatCallout(deck, 'Stats', [{ value: '3x', label: 'Faster' }, { value: '50%', label: 'Cheaper' }], 5, 'n');
addProcessFlow(deck, 'Flow', ['Plan', 'Build', 'Ship', 'Learn'], 6, 'n');
addCodeSlide(deck, 'Code', 'print("hello")', 7, 'n');
addSectionDivider(deck, 1, 'Section One', 8);
addTitleAlt(deck, 'Alt Title', 'Alt subtitle', 9);
addSectionContent(deck, 'Section Content', ['Item A', 'Item B'], 10, 'n');
addTwoColNumbered(deck, 'Ranked', ['First', 'Second', 'Third'], 11, 'n');
addThreeColContent(deck, 'Three Col', [
  { heading: 'H1', body: 'Body one' }, { heading: 'H2', body: 'Body two' },
  { heading: 'H3', body: 'Body three' },
], 12, 'n');
addClosingSlide(deck, 13, 'n');

const outDir = process.env.AIPPT_PREVIEW_OUT || 'output';
await deck.save(`${outDir}/golden.pptx`);
"""


def _color(obj):
    try:
        return str(obj.rgb) if obj.type is not None else None
    except Exception:
        return None


def _shape_fp(shape):
    fp = {
        "type": str(shape.shape_type),
        "box": [shape.left, shape.top, shape.width, shape.height],
    }
    if shape.shape_type == 13:  # picture
        fp["image_sha1"] = hashlib.sha1(shape.image.blob).hexdigest()
    try:
        if shape.fill.type == 1:  # solid
            fp["fill"] = _color(shape.fill.fore_color)
    except Exception:
        pass
    if shape.has_text_frame:
        fp["runs"] = [
            [r.text, r.font.name, r.font.size, r.font.bold, _color(r.font.color)]
            for p in shape.text_frame.paragraphs for r in p.runs
        ]
    return fp


def _fingerprint(pptx_path):
    from pptx import Presentation
    prs = Presentation(pptx_path)
    slides = []
    for slide in prs.slides:
        bg = None
        try:
            if slide.background.fill.type == 1:
                bg = _color(slide.background.fill.fore_color)
        except Exception:
            pass
        slides.append({"background": bg, "shapes": [_shape_fp(s) for s in slide.shapes]})
    # json round-trip normalises tuples/ints for comparison with the fixture
    return json.loads(json.dumps({"size": [prs.slide_width, prs.slide_height], "slides": slides}))


def _node_available() -> bool:
    if not shutil.which("node"):
        return False
    from aippt.preview import Renderer
    return Renderer(project_root=str(PROJECT_ROOT))._find_node_modules() is not None


@pytest.mark.skipif(not _node_available(), reason="node / node_modules not available")
def test_amd_layouts_unchanged(tmp_path):
    from aippt.preview import Renderer
    from aippt.web.routes import _stage_render_workspace

    job_id = f"pytest-golden-{tmp_path.name}"
    uploads = PROJECT_ROOT / "uploads"
    try:
        script_path, out_dir = _stage_render_workspace(
            str(uploads), job_id, "golden", str(PROJECT_ROOT)
        )
        Path(script_path).write_text(SCRIPT, encoding="utf-8")
        result = Renderer(project_root=str(PROJECT_ROOT)).render(script_path, out_dir)
        assert result.success, result.stderr_tail
        actual = _fingerprint(result.pptx_path)
    finally:
        shutil.rmtree(uploads / job_id, ignore_errors=True)

    if os.environ.get("AIPPT_UPDATE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(actual, indent=1) + "\n", encoding="utf-8")
        pytest.skip("golden fixture regenerated")

    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert actual["size"] == expected["size"]
    assert len(actual["slides"]) == len(expected["slides"])
    for i, (a, e) in enumerate(zip(actual["slides"], expected["slides"]), start=1):
        assert a == e, f"AMD layout on golden slide {i} changed — see module docstring"
