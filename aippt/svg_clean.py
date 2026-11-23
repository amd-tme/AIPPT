"""Clean user-uploaded SVGs before they go into a deck.

An SVG is a document, not just a picture: it can carry scripts, event
handlers, links to outside files, embedded HTML and XML entity tricks. This
keeps an allow-list of drawing elements and attributes and drops the rest,
so what is left is only artwork. References may point inside the file
(``#id``) or at an embedded raster (``data:image/png;base64,...``), never
outside it.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

MAX_SVG_BYTES = 2_000_000

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"

_ELEMENTS = frozenset("""
    svg g defs symbol use title desc path rect circle ellipse line polyline polygon
    text tspan textPath linearGradient radialGradient stop clipPath mask pattern
    image style filter feGaussianBlur feOffset feBlend feColorMatrix feComposite
    feFlood feMerge feMergeNode
""".split())

_ATTRIBUTES = frozenset("""
    id class style transform viewBox preserveAspectRatio width height x y x1 y1 x2 y2
    cx cy r rx ry d points fill fill-opacity fill-rule stroke stroke-width
    stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray
    stroke-dashoffset stroke-opacity opacity color display visibility clip-path
    clip-rule mask filter offset stop-color stop-opacity gradientUnits
    gradientTransform spreadMethod fx fy fr patternUnits patternContentUnits
    patternTransform clipPathUnits maskUnits maskContentUnits filterUnits
    primitiveUnits href font-family font-size font-weight font-style text-anchor
    dominant-baseline letter-spacing dx dy rotate textLength lengthAdjust version
    stdDeviation in in2 result mode values type operator k1 k2 k3 k4 flood-color
    flood-opacity overflow enable-background xml:space
""".split())

# Internal reference, or a raster embedded in the file itself.
_SAFE_HREF = re.compile(r"#[\w.:-]+|data:image/(?:png|jpe?g|gif);base64,[A-Za-z0-9+/=\s]+")
# url(...) in an attribute or CSS is fine only when it points inside the file.
_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)


class SvgError(ValueError):
    """The upload is not a usable SVG."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attr_name(name: str):
    """Attribute name as the allow-list writes it; None for editor namespaces."""
    if "}" not in name:
        return name
    ns, local = name[1:].split("}", 1)
    if ns in (SVG_NS, XLINK_NS):
        return local
    if ns == XML_NS:
        return f"xml:{local}"
    return None  # inkscape:, sodipodi:, adobe ... metadata


def _has_safe_href(el: ET.Element) -> bool:
    return any(_attr_name(n) == "href" and _SAFE_HREF.fullmatch(v.strip()) for n, v in el.attrib.items())


def _safe_css(text: str) -> bool:
    lowered = text.lower()
    if "@import" in lowered or "expression(" in lowered or "javascript:" in lowered:
        return False
    return all(target.startswith("#") for _, target in _URL.findall(text))


def _clean(el: ET.Element) -> None:
    for child in list(el):
        if not isinstance(child.tag, str) or _local(child.tag) not in _ELEMENTS:
            el.remove(child)  # comments, processing instructions, unknown elements
            continue
        if _local(child.tag) == "style" and not _safe_css(child.text or ""):
            el.remove(child)
            continue
        if _local(child.tag) in ("image", "use") and not _has_safe_href(child):
            el.remove(child)  # with no safe source left it would load a file
            continue
        _clean(child)
    for name in list(el.attrib):
        local = _attr_name(name)
        value = el.attrib[name]
        if (local not in _ATTRIBUTES
                or (local == "href" and not _SAFE_HREF.fullmatch(value.strip()))
                or (local == "style" and not _safe_css(value))
                or not all(t.startswith("#") for _, t in _URL.findall(value))):
            del el.attrib[name]


def clean_svg(data: bytes) -> bytes:
    """Return *data* with everything but the artwork removed.

    Raises SvgError if it is too big, not an SVG, uses DOCTYPE/entity
    declarations, or cannot be drawn after cleaning.
    """
    if len(data) > MAX_SVG_BYTES:
        raise SvgError(f"SVG too large (max {MAX_SVG_BYTES // 1_000_000} MB)")
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in data.lower():
        raise SvgError("SVG must not contain DOCTYPE or ENTITY declarations")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise SvgError(f"Not a valid SVG: {exc}") from None
    if root.tag != f"{{{SVG_NS}}}svg":
        raise SvgError("Not an SVG (root element must be <svg>)")
    _clean(root)

    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    out = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    # Must still draw: the deck's PNG fallback is made the same way
    from cairosvg.surface import PNGSurface

    from aippt.preview import _no_fetch
    try:
        PNGSurface.convert(bytestring=out, output_width=64, url_fetcher=_no_fetch)
    except Exception as exc:
        raise SvgError(f"SVG could not be drawn: {exc}") from None
    return out
