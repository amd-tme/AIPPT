"""Tests for the AMD brand icon bank (themes/assets/icons/amd) and aippt.icons."""
from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from aippt import icons

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# The bank on disk
# ---------------------------------------------------------------------------

def test_every_icon_has_one_clean_svg():
    ids = [i["id"] for i in icons.manifest()["icons"]]
    assert len(ids) == len(set(ids)) > 200
    svgs = {p.stem for p in icons.ICON_DIR.glob("*.svg")}
    assert svgs == set(ids)
    for icon_id in ids:
        svg = (icons.ICON_DIR / f"{icon_id}.svg").read_text()
        assert "<metadata" not in svg and "display:none" not in svg.replace(" ", "")
        # One recolourable colour, so loadIcons can swap it with a string replace.
        assert set(re.findall(r"#[0-9a-fA-F]{3,6}\b", svg)) == {"#000000"}, icon_id
        assert len(svg) < 20_000, icon_id


def test_manifest_entries_are_complete():
    m = icons.manifest()
    categories = {c["id"] for c in m["categories"]}
    for icon in m["icons"]:
        assert icon["name"] and icon["description"], icon["id"]
        assert icon["category"] in categories, icon["id"]
        assert len(icon["tags"]) >= 3, icon["id"]
        assert icon["id"] == icons.slug(icon["id"])
        if "duplicate_of" in icon:
            target = icons.get(icon["duplicate_of"])
            assert target is not None and "duplicate_of" not in target


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def test_icon_ids_leave_out_duplicates_unless_asked():
    assert "users" not in icons.icon_ids()
    assert "users" in icons.icon_ids(include_duplicates=True)
    assert "customers" in icons.icon_ids()


@pytest.mark.parametrize("name,expected", [
    ("gpu", "gpu"),
    ("AI Box", "ai-box"),
    ("ai_box", "ai-box"),
    ("users", "customers"),        # same artwork — use the preferred copy
    ("not-an-icon", None),
    ("", None),
])
def test_resolve(name, expected):
    assert icons.resolve(name) == expected


@pytest.mark.parametrize("text,expected", [
    ("Scale out GPU clusters in the data center", "data-center"),
    ("Lower power, better efficiency", "power-reduction"),
    ("Roadmap and launch schedule", "calendar"),
])
def test_search_finds_the_obvious_icon_first(text, expected):
    assert icons.search(text)[0] == expected


def test_search_returns_known_ids_only():
    found = icons.search("AI inference on GPUs in the cloud with secure networking", k=20)
    assert found and len(found) <= 20
    assert all(icons.get(i) and not icons.get(i).get("duplicate_of") for i in found)


def test_best_match_needs_a_confident_score():
    assert icons.best_match("Roadmap and launch schedule") == "calendar"
    assert icons.best_match("Quarterly overview") is None


@pytest.mark.parametrize("heading,text,expected", [
    # The label decides: "models"/"parameter" in the detail used to pick fine-tuning.
    ("Memory", "288 GB HBM3E holds 500B-parameter models on one GPU", "hbm"),
    # "design"/"silicon" in the detail used to pick the DFT icon.
    ("Security", "Secure by design, from silicon to software", "secure-processor"),
    ("Open software", "ROCm is open source end to end", "software-stability"),
])
def test_heading_words_outweigh_the_detail(heading, text, expected):
    assert icons.search(text, k=1, heading=heading) == [expected]
    assert icons.best_match(text, heading=heading) == expected


def test_versioned_names_match_their_family():
    # "HBM3E" is the HBM icon, not an unknown word.
    assert icons.search("HBM3E", k=1) == ["hbm"]


def test_catalogue_lines():
    text = icons.catalogue_lines(["gpu", "calendar", "nope"])
    lines = text.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("gpu — ")


# ---------------------------------------------------------------------------
# loadIcons renders through the real Node sandbox
# ---------------------------------------------------------------------------

_ICON_SCRIPT = """\
import { createDeck, addCardGrid, loadIcons } from '../lib/pptxgenjs-helpers.mjs';
const deck = await createDeck('themes/amd.yaml');
const icons = loadIcons(["gpu", "users", "no-such-icon"], "00C2DE");
if (Object.keys(icons).join() !== "gpu,users") throw new Error("ids: " + Object.keys(icons));
if (!icons.gpu.startsWith("image/svg+xml;base64,")) throw new Error("not an SVG");
addCardGrid(deck, "Icons", [
  { title: "GPU", body: "Compute", iconImg: icons.gpu },
  { title: "Users", body: "People", iconImg: icons.users },
], 1);
await deck.save(`${process.env.AIPPT_PREVIEW_OUT || 'output'}/icons.pptx`);
"""


def test_load_icons_renders(tmp_path):
    import shutil
    from aippt.preview import Renderer
    from aippt.web.routes import _stage_render_workspace

    if not shutil.which("node") or Renderer(project_root=str(ROOT))._find_node_modules() is None:
        pytest.skip("node / node_modules not available")
    job_id = f"pytest-icons-{tmp_path.name}"
    try:
        script, out_dir = _stage_render_workspace(str(ROOT / "uploads"), job_id, "icons", str(ROOT))
        Path(script).write_text(_ICON_SCRIPT, encoding="utf-8")
        result = Renderer(project_root=str(ROOT)).render(script, out_dir)
        assert result.success, result.stderr_tail
        from pptx import Presentation
        slide = Presentation(result.pptx_path).slides[0]
        pictures = [s for s in slide.shapes  # 13 = picture; skip the theme logo
                    if s.shape_type == 13 and b"svgBlip" in s._element.xml.encode()]
        assert len(pictures) == 2
        # The PNG shown by viewers without SVG support is the icon, not
        # pptxgenjs's 100x119 broken-image placeholder.
        from PIL import Image
        for pic in pictures:
            png = Image.open(io.BytesIO(pic.image.blob))
            assert png.size[0] == 512
            colours = {c for _, c in png.convert("RGBA").getcolors(1 << 20) if c[3] > 200}
            assert colours and all(max(abs(x - y) for x, y in zip(c, (0x00, 0xC2, 0xDE))) <= 3
                                   for c in colours)  # the icon colour, ± anti-aliasing
    finally:
        shutil.rmtree(ROOT / "uploads" / job_id, ignore_errors=True)
