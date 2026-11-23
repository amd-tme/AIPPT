"""Attached images look right on a slide: never stretched, phone photos
upright, oversized or CMYK files made safe, and SVG fallbacks sharp."""
from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from aippt import raster

ROOT = Path(__file__).resolve().parents[1]


def _image(size, fmt="PNG", mode="RGB", **save):
    buf = io.BytesIO()
    Image.new(mode, size, "#00C2DE" if mode == "RGB" else 0).save(buf, fmt, **save)
    return buf.getvalue()


def _phone_photo():
    exif = Image.Exif()
    exif[0x0112] = 6  # stored landscape, shown rotated 90 degrees clockwise
    return _image((60, 40), "JPEG", exif=exif.tobytes())


# ── raster.prepare ──────────────────────────────────────────────────────

def test_plain_images_pass_through_unchanged():
    for name, data in [("a.png", _image((8, 4))), ("a.jpg", _image((8, 4), "JPEG")),
                       ("a.gif", _image((8, 4), "GIF"))]:
        assert raster.prepare(name, data) == data


def test_phone_photo_is_turned_upright():
    out = Image.open(io.BytesIO(raster.prepare("photo.jpg", _phone_photo())))
    assert out.size == (40, 60)
    assert out.getexif().get(0x0112, 1) == 1


def test_huge_image_is_scaled_down():
    out = Image.open(io.BytesIO(raster.prepare("wide.png", _image((raster.MAX_SIDE + 1000, 50)))))
    assert out.size[0] == raster.MAX_SIDE


def test_cmyk_jpeg_becomes_rgb():
    out = Image.open(io.BytesIO(raster.prepare("print.jpg", _image((8, 8), "JPEG", mode="CMYK"))))
    assert out.mode == "RGB"


@pytest.mark.parametrize("name,data,message", [
    ("a.png", b"not an image", "not a readable image"),
    ("a.png", _image((4, 4), "JPEG"), "file is JPEG, not PNG"),
    ("a.bmp", _image((4, 4), "BMP"), "not a PNG, JPEG or GIF"),
])
def test_bad_rasters_are_rejected(name, data, message):
    with pytest.raises(raster.RasterError, match=message):
        raster.prepare(name, data)


def test_user_logo_upload_is_turned_upright(tmp_path):
    from aippt import user_assets

    entry = user_assets.add_asset(str(tmp_path / "u"), "logo", "logo.jpg", _phone_photo(), name="Logo")
    path = user_assets.asset_path(str(tmp_path / "u"), entry)
    assert Image.open(path).size == (40, 60)


# ── placement on the slide ──────────────────────────────────────────────

_FIT_SCRIPT = """\
import { createDeck, addImageSlide, addImageBulletsSlide } from '../lib/pptxgenjs-helpers.mjs';
const deck = await createDeck('themes/corp_black.yaml');
const dir = '__DIR__';
addImageSlide(deck, 'Tall', `${dir}/tall.png`, 1);
addImageSlide(deck, 'Wide', `${dir}/wide.jpg`, 2);
addImageBulletsSlide(deck, 'Split', `${dir}/wide.jpg`, ['A point'], 3);
addImageSlide(deck, 'Vector', `${dir}/shape.svg`, 4);
addImageSlide(deck, 'Tiny', `${dir}/tiny.png`, 5);
await deck.save(`${process.env.AIPPT_PREVIEW_OUT || 'output'}/image-fit.pptx`);
"""


def test_images_keep_their_shape(tmp_path):
    from pptx import Presentation
    from aippt.preview import Renderer
    from aippt.web.routes import _stage_render_workspace

    if not shutil.which("node") or Renderer(project_root=str(ROOT))._find_node_modules() is None:
        pytest.skip("node / node_modules not available")
    job_id = f"pytest-fit-{tmp_path.name}"
    job = ROOT / "uploads" / job_id
    try:
        script, out_dir = _stage_render_workspace(str(ROOT / "uploads"), job_id, "fit", str(ROOT))
        media = job / "media"
        media.mkdir()
        (media / "tall.png").write_bytes(_image((300, 600)))
        (media / "wide.jpg").write_bytes(_image((1600, 400), "JPEG"))
        (media / "tiny.png").write_bytes(_image((72, 36)))
        (media / "shape.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100">'
            '<rect width="400" height="100" fill="#00C2DE"/></svg>')
        Path(script).write_text(_FIT_SCRIPT.replace("__DIR__", str(media)), encoding="utf-8")
        result = Renderer(project_root=str(ROOT)).render(script, out_dir)
        assert result.success, result.stderr_tail
        pres = Presentation(result.pptx_path)
        with zipfile.ZipFile(result.pptx_path) as z:
            fallbacks = {n: Image.open(io.BytesIO(z.read(n))).size for n in z.namelist()
                         if n.startswith("ppt/media/") and n.endswith(".png")}
    finally:
        shutil.rmtree(job, ignore_errors=True)

    def picture(slide):
        pics = [s for s in slide.shapes if s.shape_type == 13 and s.width > 914400 * 0.5]
        return max(pics, key=lambda s: s.width * s.height)

    slides = list(pres.slides)
    for slide, ratio in [(slides[0], 0.5), (slides[1], 4.0), (slides[2], 4.0), (slides[3], 4.0)]:
        pic = picture(slide)
        assert pic.width / pic.height == pytest.approx(ratio, rel=0.01), slide.shapes.title
    # The split layout's image starts level with the bullets, at the top
    split = picture(slides[2])
    assert split.top == min(s.top for s in slides[2].shapes if s.has_text_frame and s.text_frame.text == "A point")
    # A 72x36 image is shown at most 1 inch wide rather than blown up blurry
    assert picture(slides[4]).width <= 914400 + 1
    # The SVG's PNG fallback is drawn for its size on the slide, not a fixed 512 px
    svg_pic = picture(slides[3])
    want = min(svg_pic.width * 200 // 914400, 2400)
    assert any(abs(w - want) <= 2 for w, _ in fallbacks.values()), fallbacks
