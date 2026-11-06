"""Test slide master support in pptxgenjs-generated PPTX files.

Generates decks with and without masters and validates the PPTX
structure using python-pptx.
"""

import os
import subprocess
from pathlib import Path

import pytest
from pptx import Presentation
from PIL import Image
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE_PATH = subprocess.check_output(
    ["npm", "root", "-g"], cwd=REPO_ROOT, text=True
).strip()


def _generate_deck(use_master: bool, output_path: str, theme_path: str = None) -> str:
    """Generate a minimal pptxgenjs deck with or without masters."""
    master_flag = "true" if use_master else "false"
    helpers_path = os.path.join(REPO_ROOT, "lib", "pptxgenjs-helpers.mjs")
    theme_path = theme_path or os.path.join(REPO_ROOT, "themes", "default.yaml")
    script = f"""\
import {{ createDeck, addTitleSlide, addBulletSlide, addSectionDivider,
         addClosingSlide, addProcessFlow, addCardGrid, SW, SH
       }} from '{helpers_path}';

const deck = createDeck('{theme_path}', {{ useSlideMaster: {master_flag} }});

addTitleSlide(deck, 'Test Title', 'Subtitle', 1);
addBulletSlide(deck, 'Bullets', ['Item 1', 'Item 2', 'Item 3'], 2, 'notes');
addSectionDivider(deck, 1, 'Section One', 3);
addProcessFlow(deck, 'Process', ['Step 1', 'Step 2', 'Step 3'], 4, 'notes');
addCardGrid(deck, 'Cards', [
  {{ title: 'A', body: 'Desc A' }},
  {{ title: 'B', body: 'Desc B' }},
], 5, 'notes');
addClosingSlide(deck, 6, 'Thank you');

await deck.save('{output_path}');
"""
    script_path = str(Path(output_path).with_suffix(".mjs"))
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    env = {**os.environ, "NODE_PATH": NODE_PATH}
    result = subprocess.run(
        ["node", script_path],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"Generation failed:\n{result.stderr}"
    assert os.path.exists(output_path), f"Output not created: {output_path}"
    return output_path


@pytest.fixture
def branded_theme(tmp_path):
    logo = tmp_path / "logo.png"
    Image.new("RGB", (80, 20), "teal").save(logo)
    theme = yaml.safe_load((Path(REPO_ROOT) / "themes/default.yaml").read_text(encoding="utf-8"))
    theme["logo"] = {
        "path": str(logo), "width_inches": 0.8, "height_inches": 0.2,
        "x_inches": 0.3, "y_inches": 0.3,
    }
    path = tmp_path / "branded.yaml"
    path.write_text(yaml.safe_dump(theme), encoding="utf-8")
    return str(path), logo.read_bytes()


class TestMasterDefinition:
    """Generated PPTX has expected masters when useSlideMaster is true."""

    def test_master_deck_has_named_layouts(self, tmp_path):
        out = str(tmp_path / "master.pptx")
        _generate_deck(use_master=True, output_path=out)
        p = Presentation(out)
        layout_names = [sl.name for sm in p.slide_masters for sl in sm.slide_layouts]
        assert "TITLE_MASTER" in layout_names, f"Missing TITLE_MASTER in {layout_names}"
        assert "CONTENT_MASTER" in layout_names, f"Missing CONTENT_MASTER in {layout_names}"
        assert "SECTION_DIVIDER_MASTER" in layout_names, f"Missing SECTION_DIVIDER_MASTER in {layout_names}"

    def test_no_master_deck_has_default_master_only(self, tmp_path):
        out = str(tmp_path / "no_master.pptx")
        _generate_deck(use_master=False, output_path=out)
        p = Presentation(out)
        assert len(p.slide_masters) == 1

    def test_both_decks_have_same_slide_count(self, tmp_path):
        out_m = str(tmp_path / "master.pptx")
        out_n = str(tmp_path / "no_master.pptx")
        _generate_deck(use_master=True, output_path=out_m)
        _generate_deck(use_master=False, output_path=out_n)
        p_m = Presentation(out_m)
        p_n = Presentation(out_n)
        assert len(p_m.slides) == len(p_n.slides) == 6


class TestChromeNotDuplicated:
    """Content slides have no logo/footer shapes when masters are active."""

    def test_content_slides_have_no_image_shapes(self, tmp_path, branded_theme):
        """Logo should be on the master, not baked into individual slides."""
        out = str(tmp_path / "master.pptx")
        theme_path, logo = branded_theme
        _generate_deck(use_master=True, output_path=out, theme_path=theme_path)
        p = Presentation(out)
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        content_slides = 0
        for i, slide in enumerate(p.slides):
            if slide.slide_layout.name != "CONTENT_MASTER":
                continue
            content_slides += 1
            inherited_logos = [
                shape for shape in slide.slide_layout.shapes
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE and shape.image.blob == logo
            ]
            assert len(inherited_logos) == 1, "content layout must supply the logo exactly once"
            images = [
                s for s in slide.shapes
                if s.shape_type == MSO_SHAPE_TYPE.PICTURE
            ]
            assert len(images) == 0, (
                f"Slide {i + 1} ({slide.slide_layout.name}) has {len(images)} "
                f"image shapes — logo should be on the master, not the slide"
            )
        assert content_slides > 0, "no content slides were checked"

    def test_content_slides_use_placeholder_slide_numbers(self, tmp_path):
        """Slide numbers should come from the master placeholder, not addFooter."""
        out = str(tmp_path / "master.pptx")
        _generate_deck(use_master=True, output_path=out)
        p = Presentation(out)

        for i, slide in enumerate(p.slides):
            if slide.slide_layout.name != "CONTENT_MASTER":
                continue
            for shape in slide.shapes:
                if not shape.is_placeholder:
                    continue
                from pptx.enum.shapes import PP_PLACEHOLDER
                if shape.placeholder_format.type == PP_PLACEHOLDER.SLIDE_NUMBER:
                    break
            else:
                pytest.fail(
                    f"Slide {i + 1} (CONTENT_MASTER) has no slide number "
                    f"placeholder — expected one inherited from the master"
                )

    def test_no_master_slides_have_manual_footer(self, tmp_path):
        """Without masters, slides should have manually added footer shapes."""
        out = str(tmp_path / "no_master.pptx")
        _generate_deck(use_master=False, output_path=out)
        p = Presentation(out)

        # Bullet slide (index 1) should have a manual slide number text shape
        slide = p.slides[1]
        has_manual_number = any(
            hasattr(s, "text") and s.text.strip() == "2" and not s.is_placeholder
            for s in slide.shapes
        )
        assert has_manual_number, (
            "Non-master bullet slide should have a manually added slide number"
        )


class TestBackwardCompat:
    """Default useSlideMaster=false produces identical structure to today."""

    def test_default_creates_deck_without_masters(self, tmp_path):
        out = str(tmp_path / "default.pptx")
        _generate_deck(use_master=False, output_path=out)
        p = Presentation(out)
        assert len(p.slide_masters) == 1
        assert len(p.slides) == 6
