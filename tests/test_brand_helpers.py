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


# ---------------------------------------------------------------------------
# addMetricTable
# ---------------------------------------------------------------------------

_METRIC_SCRIPT = """\
import { createDeck, addMetricTable } from '../lib/pptxgenjs-helpers.mjs';
const deck = await createDeck('themes/__THEME__.yaml');
const rows = [1, 2, 3, 4, 5, 6, 7].map(i => ({ label: `Metric ${i}`, value: `${i}.0x`, why: `Reason ${i}` }));
addMetricTable(deck, 'With image', rows.slice(0, 4), 1, '', {
  header: ['Metric', 'Ours', 'Why'], image: 'themes/assets/mi355x-die.png', source: 'Source: test',
});
addMetricTable(deck, 'Seven rows', rows, 2);
addMetricTable(deck, 'Two columns', rows.slice(0, 2).map(({ label, value }) => ({ label, value })), 3);
await deck.save(`${process.env.AIPPT_PREVIEW_OUT || 'output'}/metric.pptx`);
"""


@pytest.mark.parametrize("theme,ink", [("corp_black", "FFFFFF"), ("corp_white", "000000")])
def test_metric_table(tmp_path, theme, ink):
    prs = _render(tmp_path, "metric", _METRIC_SCRIPT.replace("__THEME__", theme))
    with_image, seven, two_cols = prs.slides
    table = next(s for s in with_image.shapes if s.has_table).table
    assert len(table.rows) == 5 and len(table.columns) == 3       # header + 4
    assert [c.text for c in table.rows[0].cells] == ["Metric", "Ours", "Why"]
    label, value, why = table.rows[1].cells
    run = lambda cell: cell.text_frame.paragraphs[0].runs[0].font
    assert str(run(label).color.rgb) == ("9D9FA2" if theme == "corp_black" else "5E5E5E")
    assert str(run(value).color.rgb) == "00C2DE" and run(value).size.pt == 36 and run(value).bold
    assert str(run(why).color.rgb) == ink
    # Product image to the left of the table, source line under it
    tbl = next(s for s in with_image.shapes if s.has_table)
    pic = next(s for s in with_image.shapes if s.shape_type == 13 and s.left < tbl.left)
    assert pic.left + pic.width <= tbl.left
    assert "Source: test" in [s.text_frame.text for s in with_image.shapes if s.has_text_frame]
    # Horizontal rules only: no vertical borders in the XML
    import re
    xml = tbl._element.xml
    for side in ("lnL", "lnR"):
        assert all("<a:noFill/>" in m for m in re.findall(rf"<a:{side}\b.*?</a:{side}>", xml, re.S))
    body_rules = re.findall(r"<a:lnB\b.*?</a:lnB>", xml, re.S)[3:]           # skip header cells
    assert body_rules and all('w="28575"' in m for m in body_rules)    # 2.25 pt
    # Capped at 6 rows (no header); values shrink for long tables
    t7 = next(s for s in seven.shapes if s.has_table).table
    assert len(t7.rows) == 6
    assert run(t7.rows[0].cells[1]).size.pt < 36
    # No "why" values -> two columns
    assert len(next(s for s in two_cols.shapes if s.has_table).table.columns) == 2


# ---------------------------------------------------------------------------
# addSpecTable
# ---------------------------------------------------------------------------

_SPEC_SCRIPT = """\
import { createDeck, addSpecTable } from '../lib/pptxgenjs-helpers.mjs';
const deck = await createDeck('themes/__THEME__.yaml');
const rows = [['HBM', '192 GB', '288 GB', '192 GB'], ['Power', '1,000 W', '1,400 W', '750 W']];
addSpecTable(deck, 'Auto', ['Spec', 'B200', 'AMD Instinct MI355X', 'MI300X'], rows, 1, '', { source: 'Source: test' });
addSpecTable(deck, 'Forced', ['Spec', 'A', 'B', 'C'], rows, 2, '', { highlight: 3 });
addSpecTable(deck, 'None', ['Spec', 'B200', 'MI355X', 'MI300X'], rows, 3, '', { highlight: false });
addSpecTable(deck, 'Sheet', ['', ''], [['Architecture', 'CDNA 4'], ['HBM', '288 GB']], 4);
const many = Array.from({ length: 14 }, (_, i) => [`S${i}`, '1', '2', '3']);
addSpecTable(deck, 'Long', ['Spec', 'EPYC 9965', 'Xeon', 'Other'], many, 5);
await deck.save(`${process.env.AIPPT_PREVIEW_OUT || 'output'}/spec.pptx`);
"""


def _table(slide):
    return next(s for s in slide.shapes if s.has_table).table


def _cell_fill(cell):
    return str(cell.fill.fore_color.rgb) if cell.fill.type == 1 else None   # 1 = solid


@pytest.mark.parametrize("theme,ink,tint", [("corp_black", "FFFFFF", "00313"), ("corp_white", "000000", "D9F6")])
def test_spec_table(tmp_path, theme, ink, tint):
    prs = _render(tmp_path, "spec", _SPEC_SCRIPT.replace("__THEME__", theme))
    auto, forced, none, sheet, long = prs.slides
    font = lambda cell: cell.text_frame.paragraphs[0].runs[0].font
    t = _table(auto)
    # The AMD column is found from its header: accent header with black text, tinted bold body
    assert _cell_fill(t.cell(0, 2)) == "00C2DE" and str(font(t.cell(0, 2)).color.rgb) == "000000"
    assert _cell_fill(t.cell(1, 2)).startswith(tint) and font(t.cell(1, 2)).bold
    assert str(font(t.cell(1, 2)).color.rgb) == ink
    # Competitors are muted, not filled
    assert _cell_fill(t.cell(1, 1)) is None and not font(t.cell(1, 1)).bold
    assert str(font(t.cell(1, 1)).color.rgb) != ink
    assert "Source: test" in [s.text_frame.text for s in auto.shapes if s.has_text_frame]
    # opts.highlight overrides / disables detection
    assert [_cell_fill(_table(forced).cell(0, c)) for c in range(4)] == [None, None, None, "00C2DE"]
    assert all(_cell_fill(_table(none).cell(r, c)) is None for r in range(3) for c in range(4))
    # One product: borderless sheet, no empty header row, accent labels
    ts = _table(sheet)
    assert len(ts.rows) == 2 and len(ts.columns) == 2
    assert str(font(ts.cell(0, 0)).color.rgb) == "00C2DE"
    # Capped at 12 body rows, smaller type for dense tables
    tl = _table(long)
    assert len(tl.rows) == 13 and font(tl.cell(1, 0)).size.pt == 12
    assert _cell_fill(tl.cell(0, 1)) == "00C2DE"                    # EPYC detected


# ---------------------------------------------------------------------------
# addCompetitiveChart
# ---------------------------------------------------------------------------

_CHART_SCRIPT = """\
import { createDeck, addCompetitiveChart } from '../lib/pptxgenjs-helpers.mjs';
const deck = await createDeck('themes/__THEME__.yaml');
addCompetitiveChart(deck, 'Throughput', ['Model A', 'Model B'], [
  { name: 'Competitor X', values: [100, 200] },
  { name: 'AMD Instinct MI355X', values: [130, 250] },
], 1, '', { metric: 'Tokens/s', date: 'Nov 2026', source: 'Illustrative' });
addCompetitiveChart(deck, 'Lower is better', ['Job'], [
  { name: 'Ours', values: [40], amd: true }, { name: 'Theirs', values: [60] },
], 2, '', { lowerIsBetter: true });
addCompetitiveChart(deck, 'No ratios', ['A', 'B'], [
  { name: 'X', values: [1, 2] }, { name: 'Y', values: [2, 3] },
], 3, '', { ratios: false });
addCompetitiveChart(deck, 'Empty', [], [], 4);
await deck.save(`${process.env.AIPPT_PREVIEW_OUT || 'output'}/chart.pptx`);
"""


def _chart(slide):
    frames = [s for s in slide.shapes if s.has_chart]
    assert len(frames) == 1
    return frames[0].chart


@pytest.mark.parametrize("theme", ["corp_black", "corp_white"])
def test_competitive_chart(tmp_path, theme):
    import re

    prs = _render(tmp_path, "chart", _CHART_SCRIPT.replace("__THEME__", theme))
    slides = list(prs.slides)
    assert len(slides) == 4

    chart = _chart(slides[0])
    xml = chart._chartSpace.xml
    # Native clustered columns from zero; no legend, title, gridlines or value axis
    assert chart.chart_type is not None and 'barDir val="col"' in xml
    assert not chart.has_legend
    assert "<c:majorGridlines" not in xml
    assert re.search(r"<c:valAx>.*?<c:delete val=\"1\"/>", xml, re.S)
    assert re.search(r"<c:min val=\"0\"/>", xml)
    # AMD series = accent, competitor = grey
    fills = re.findall(r"<c:ser>.*?<a:srgbClr val=\"(\w{6})\"", xml, re.S)
    assert fills[1] == "00C2DE" and fills[0] != "00C2DE"
    # Ratio labels (AMD / best competitor) in the accent colour, above the AMD bars
    assert _text_colour(slides[0], "1.3×") == "00C2DE"
    assert _shape_with_text(slides[0], "1.3×").top < _chart_bottom(slides[0])
    # Chip legend + metric note + Date / Data Source block with bold labels
    _shape_with_text(slides[0], "Competitor X")
    _shape_with_text(slides[0], "Tokens/s")
    src = _shape_with_text(slides[0], "Date: Nov 2026    Data Source: Illustrative")
    runs = src.text_frame.paragraphs[0].runs
    assert runs[0].font.bold and not runs[1].font.bold

    # lowerIsBetter: competitor / AMD; the explicit amd flag wins over the name
    assert _text_colour(slides[1], "1.5×") == "00C2DE"
    # ratios: false -> no ratio text; no AMD name -> last series is highlighted
    assert not [s for s in slides[2].shapes if s.has_text_frame and s.text_frame.text.endswith("×")]
    fills = re.findall(r"<c:ser>.*?<a:srgbClr val=\"(\w{6})\"", _chart(slides[2])._chartSpace.xml, re.S)
    assert fills[1] == "00C2DE"
    # Empty input -> title-only slide
    assert not [s for s in slides[3].shapes if s.has_chart]
    # Everything sits above the footer
    for shape in slides[0].shapes:
        if shape.top is not None and shape.has_text_frame and shape.text_frame.text not in ("1",):
            assert (shape.top + shape.height) / 914400 <= 7.0, shape.text_frame.text


def _chart_bottom(slide):
    frame = next(s for s in slide.shapes if s.has_chart)
    return frame.top + frame.height
