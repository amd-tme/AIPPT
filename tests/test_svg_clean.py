"""clean_svg keeps the artwork of an uploaded SVG and drops everything else."""
import xml.etree.ElementTree as ET

import pytest

from aippt.icons import ICON_DIR
from aippt.svg_clean import MAX_SVG_BYTES, SvgError, clean_svg

NS = 'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'


def _png_uri():
    """A valid 1x1 PNG as a data: URI."""
    import base64, io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), "#00C2DE").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _svg(body, attrs=""):
    return f'<svg {NS} viewBox="0 0 10 10" {attrs}>{body}</svg>'.encode()


def _text(data):
    return clean_svg(data).decode()


def test_every_brand_icon_keeps_all_its_elements():
    for path in ICON_DIR.glob("*.svg"):
        raw = path.read_bytes()
        before = [e.tag for e in ET.fromstring(raw).iter()]
        assert [e.tag for e in ET.fromstring(clean_svg(raw)).iter()] == before, path.name


def test_drawing_survives():
    out = _text(_svg('<defs><linearGradient id="g"><stop offset="0" stop-color="#00C2DE"/>'
                     '</linearGradient></defs><path d="M0 0H10V10Z" fill="url(#g)"/>'
                     '<use xlink:href="#g"/><style>.a{fill:#fff}</style><rect class="a" width="5" height="5"/>'))
    for kept in ('d="M0 0H10V10Z"', 'fill="url(#g)"', 'href="#g"', ".a{fill:#fff}", 'class="a"'):
        assert kept in out


@pytest.mark.parametrize("body,gone", [
    ("<script>alert(1)</script><rect width='1' height='1'/>", "alert"),
    ("<rect width='1' height='1' onload='alert(1)'/>", "onload"),
    ("<foreignObject><iframe src='https://x'/></foreignObject>", "iframe"),
    ("<a href='javascript:alert(1)'><rect width='1' height='1'/></a>", "javascript"),
    ("<use xlink:href='https://evil.example/x.svg#a'/>", "evil.example"),
    ("<image href='file:///etc/passwd' width='1' height='1'/>", "passwd"),
    ("<rect width='1' height='1' fill='url(https://evil.example/p)'/>", "evil.example"),
    ("<rect width='1' height='1' style='fill:url(https://evil.example/p)'/>", "evil.example"),
    ("<style>@import url(https://evil.example/a.css);</style>", "evil.example"),
    ("<!-- secret --><rect width='1' height='1'/>", "secret"),
    ("<rect width='1' height='1' inkscape:label='x' xmlns:inkscape='http://www.inkscape.org/namespaces/inkscape'/>",
     "inkscape:label"),
])
def test_active_content_and_outside_links_are_removed(body, gone):
    assert gone not in _text(_svg(body))


def test_embedded_raster_is_kept():
    out = _text(_svg(f'<image width="10" height="10" xlink:href="{_png_uri()}"/>'))
    assert "data:image/png;base64," in out


@pytest.mark.parametrize("data,message", [
    (b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x "y">]><svg ' + NS.encode() + b'>&x;</svg>', "DOCTYPE"),
    (_svg("", 'width="1"').replace(b"<svg", b"<!ENTITY a 'b'><svg"), "ENTITY"),
    (b"<html><body/></html>", "root element"),
    (b"not xml", "Not a valid SVG"),
    (b"<svg" + b" " * MAX_SVG_BYTES + b"/>", "too large"),
])
def test_unusable_uploads_are_rejected(data, message):
    with pytest.raises(SvgError, match=message):
        clean_svg(data)
