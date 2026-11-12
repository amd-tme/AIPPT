"""Render tests for the brand-pattern helpers in lib/pptxgenjs-helpers.mjs.

Each script runs through the real Renderer (Node --permission sandbox), the
same path the web app uses.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _render(tmp_path, name, script_text):
    """Render a helper script; return the saved Presentation."""
    from pptx import Presentation
    from aippt.preview import Renderer
    from aippt.web.routes import _stage_render_workspace

    if not shutil.which("node") or Renderer(project_root=str(ROOT))._find_node_modules() is None:
        pytest.skip("node / node_modules not available")
    job_id = f"pytest-{name}-{tmp_path.name}"
    try:
        script, out_dir = _stage_render_workspace(str(ROOT / "uploads"), job_id, name, str(ROOT))
        Path(script).write_text(script_text, encoding="utf-8")
        result = Renderer(project_root=str(ROOT)).render(script, out_dir)
        assert result.success, result.stderr_tail
        return Presentation(result.pptx_path)
    finally:
        shutil.rmtree(ROOT / "uploads" / job_id, ignore_errors=True)


def _svg_pictures(slide):
    # 13 = picture; the theme logo is a PNG, icons are SVG
    return [s for s in slide.shapes if s.shape_type == 13 and b"svgBlip" in s._element.xml.encode()]


def _text_colour(slide, text):
    for shape in slide.shapes:
        if shape.has_text_frame and shape.text_frame.text == text:
            return str(shape.text_frame.paragraphs[0].runs[0].font.color.rgb)
    raise AssertionError(f"no text {text!r}")


# ---------------------------------------------------------------------------
# addIconFeatureGrid
# ---------------------------------------------------------------------------

_GRID_SCRIPT = """\
import { createDeck, addIconFeatureGrid, loadIcons } from '../lib/pptxgenjs-helpers.mjs';
const deck = await createDeck('themes/__THEME__.yaml');
const six = [
  { icon: 'gpu', label: 'Compute', desc: 'Fast.' },
  { icon: 'hbm', label: 'Memory', desc: 'Big.', highlight: true },
  { icon: 'application', label: 'Software', desc: 'Open.' },
  { icon: 'data-center', label: 'Racks', desc: 'Standard.' },
  { icon: loadIcons(['calendar'], '00FF00').calendar, label: 'Own image', desc: 'Data string.' },
  { icon: 'no-such-icon', label: 'Missing', desc: 'Text only.' },
];
for (const n of [3, 4, 5, 6]) addIconFeatureGrid(deck, `Grid ${n}`, six.slice(0, n), n, '', { takeaway: 'So what' });
addIconFeatureGrid(deck, 'Empty', [], 7);
await deck.save(`${process.env.AIPPT_PREVIEW_OUT || 'output'}/grid.pptx`);
"""


@pytest.mark.parametrize("theme,ink", [("corp_black", "FFFFFF"), ("corp_white", "000000")])
def test_icon_feature_grid(tmp_path, theme, ink):
    prs = _render(tmp_path, "grid", _GRID_SCRIPT.replace("__THEME__", theme))
    slides = list(prs.slides)
    assert len(slides) == 5
    # One icon per item; the unknown id is left out but its text stays
    assert [len(_svg_pictures(s)) for s in slides] == [3, 4, 5, 5, 0]
    six = slides[3]
    assert _text_colour(six, "Compute") == ink
    assert _text_colour(six, "Memory") == "00C2DE"      # highlight = accent
    assert _text_colour(six, "Missing") == ink
    # Brand rule: no container shapes (circles, cards) behind the icons
    for shape in six.shapes:
        if shape.shape_type != 13:   # pptxgenjs text boxes are auto shapes
            assert shape.has_text_frame and shape.fill.type in (None, 5), shape.name  # 5 = no fill
    # 5 items = 3 over 2, the second row centred
    pics = sorted(_svg_pictures(slides[2]), key=lambda p: (p.top, p.left))
    assert len({p.top for p in pics[:3]}) == 1 and pics[3].top > pics[0].top
    pitch = pics[1].left - pics[0].left
    assert abs(pics[3].left - (pics[0].left + pitch / 2)) < 914400 * 0.02
    assert abs(pics[4].left - pics[3].left - pitch) < 914400 * 0.02
    # Everything sits above the footer
    for slide in slides[:4]:
        for shape in slide.shapes:
            if shape.shape_type == 13 and b"svgBlip" in shape._element.xml.encode():
                assert shape.top + shape.height < 914400 * 6.9


# ---------------------------------------------------------------------------
# addKpiTiles / addHeroNumber
# ---------------------------------------------------------------------------

_KPI_SCRIPT = """\
import { createDeck, addKpiTiles, addHeroNumber } from '../lib/pptxgenjs-helpers.mjs';
const deck = await createDeck('themes/__THEME__.yaml');
addKpiTiles(deck, 'Tiles', [
  { icon: 'hbm', value: '288 GB', label: 'Memory', context: 'vs. 192 GB' },
  { icon: 'gpu', value: '1.3x', label: 'Faster', highlight: true },
  { value: '40%', label: 'Efficiency' },
  { value: '$2.3M', label: 'TCO' },
  { value: 'extra', label: 'Fifth tile is dropped' },
], 1, '', { takeaway: 'So what', source: 'Source: test endnote' });
addKpiTiles(deck, 'Long values', [
  { value: '1,234,567 tokens/s', label: 'A' }, { value: '9', label: 'B' },
], 2);
addHeroNumber(deck, '1.3x', 'faster inference', 3, '', { context: 'FP4, 8 GPUs', source: 'See endnote X-1' });
addHeroNumber(deck, '$12.5M', 'saved', 4, '', { title: 'TCO' });
await deck.save(`${process.env.AIPPT_PREVIEW_OUT || 'output'}/kpi.pptx`);
"""


def _shape_with_text(slide, text):
    return next(s for s in slide.shapes if s.has_text_frame and s.text_frame.text == text)


def _font_pt(slide, text):
    return _shape_with_text(slide, text).text_frame.paragraphs[0].runs[0].font.size.pt


@pytest.mark.parametrize("theme,ink", [("corp_black", "FFFFFF"), ("corp_white", "000000")])
def test_kpi_tiles_and_hero_number(tmp_path, theme, ink):
    prs = _render(tmp_path, "kpi", _KPI_SCRIPT.replace("__THEME__", theme))
    tiles, long_values, hero, hero_titled = prs.slides
    texts = [s.text_frame.text for s in tiles.shapes if s.has_text_frame]
    assert "extra" not in texts                          # at most 4 tiles
    assert _text_colour(tiles, "1.3x") == "00C2DE"       # highlight only
    assert _text_colour(tiles, "288 GB") == ink
    assert len(_svg_pictures(tiles)) == 2
    # All values share one size; a long value shrinks the whole row
    assert len({_font_pt(tiles, v) for v in ("288 GB", "1.3x", "40%", "$2.3M")}) == 1
    assert _font_pt(long_values, "9") == _font_pt(long_values, "1,234,567 tokens/s") < 48
    # Source line sits above the footer, under the tiles
    src = _shape_with_text(tiles, "Source: test endnote")
    tile_bottom = max(s.top + s.height for s in tiles.shapes if s.has_text_frame and s.text_frame.text == "vs. 192 GB")
    assert tile_bottom < src.top and src.top + src.height <= 914400 * 6.9 + 10
    # Hero: big accent number, left-aligned at the margin
    value = _shape_with_text(hero, "1.3x")
    assert _text_colour(hero, "1.3x") == "00C2DE" and _font_pt(hero, "1.3x") >= 96
    assert abs(value.left - 914400 * 0.64) < 9144
    assert "See endnote X-1" in [s.text_frame.text for s in hero.shapes if s.has_text_frame]
    assert "TCO" in [s.text_frame.text for s in hero_titled.shapes if s.has_text_frame]
