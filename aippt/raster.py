"""Make uploaded PNG, JPEG and GIF images safe to place on a slide.

A file is checked to really be the type its name says. A phone photo stores
"which way is up" as an EXIF tag that PowerPoint ignores, so it is turned
upright here. CMYK JPEGs (common from print tools) become RGB, which every
viewer can show, and very large images are scaled down so the deck stays
small; slides never need more than MAX_SIDE pixels.
"""
from __future__ import annotations

import io

MAX_SIDE = 4000

_FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".gif": "GIF"}
_EXIF_ORIENTATION = 0x0112


class RasterError(ValueError):
    """The upload is not a usable image; the message is safe to show."""


def prepare(filename: str, data: bytes) -> bytes:
    """Return *data* ready for a slide, or raise RasterError."""
    from PIL import Image, ImageOps

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    want = _FORMATS.get(ext)
    if not want:
        raise RasterError(f"{filename}: not a PNG, JPEG or GIF")
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
            img.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except Image.DecompressionBombError:
        raise RasterError(f"{filename}: image is too many pixels") from None
    except Exception:
        raise RasterError(f"{filename}: not a readable image") from None
    if fmt != want:
        raise RasterError(f"{filename}: file is {fmt}, not {ext[1:].upper()}")
    if fmt == "GIF":
        return data  # may be animated; re-saving would keep only one frame

    turned = img.getexif().get(_EXIF_ORIENTATION, 1) not in (1, None)
    cmyk = img.mode == "CMYK"
    big = max(img.size) > MAX_SIDE
    if not (turned or cmyk or big):
        return data
    if turned:
        img = ImageOps.exif_transpose(img)
    if cmyk:
        img = img.convert("RGB")
    if big:
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    out = io.BytesIO()
    if fmt == "JPEG":
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(out, "JPEG", quality=92, icc_profile=img.info.get("icc_profile"))
    else:
        img.save(out, "PNG", optimize=True)
    return out.getvalue()
