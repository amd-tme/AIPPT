"""A user's own icons and logos, kept for their decks.

Each user (by NTID) gets a folder ``<uploads>/assets/users/<ntid>/`` holding
the files and a ``manifest.json`` that lists them::

    {"assets": [{"id": "3f2a9c01b7", "kind": "icon", "name": "Partner Cloud",
                 "tags": ["cloud", "hosting"], "file": "3f2a9c01b7.svg",
                 "created": "2026-11-18T10:00:00+00:00"}]}

Icons are matched to slides by name and tags, the same way the AMD icon bank
is (5d). Logos are a partner's mark for the title/closing co-brand. SVGs go
through :func:`aippt.svg_clean.clean_svg`; PNG/JPEG must really be PNG/JPEG.
"""
from __future__ import annotations

import io
import json
import os
import re
import uuid
from datetime import datetime, timezone

from aippt.svg_clean import SvgError, clean_svg

KINDS = ("icon", "logo")
EXTS = {"icon": (".svg", ".png"), "logo": (".svg", ".png", ".jpg", ".jpeg")}
MAX_RASTER_BYTES = 5 * 1024 * 1024
MAX_ASSETS = 200
MAX_NAME = 60
MAX_TAGS = 10

_NTID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_ID_RE = re.compile(r"^[0-9a-f]{10}$")
_TAG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
_PIL_FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}


class AssetError(ValueError):
    """The upload or request cannot be used (maps to HTTP 400)."""


def user_dir(uploads_dir: str, ntid: str) -> str:
    """The user's asset folder. *ntid* must already be a safe NTID."""
    if not _NTID_RE.match(ntid or "") or ntid in (".", ".."):
        raise AssetError("A valid NTID is required for your asset library")
    return os.path.join(os.path.abspath(uploads_dir), "assets", "users", ntid)


def manifest_path(folder: str) -> str:
    return os.path.join(folder, "manifest.json")


def list_assets(folder: str) -> list:
    """The user's assets, oldest first ([] if none yet)."""
    try:
        with open(manifest_path(folder), encoding="utf-8") as fh:
            return json.load(fh).get("assets", [])
    except FileNotFoundError:
        return []


def _write(folder: str, assets: list) -> None:
    os.makedirs(folder, exist_ok=True)
    tmp = manifest_path(folder) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"assets": assets}, fh, indent=1)
    os.replace(tmp, manifest_path(folder))


def _check_file(kind: str, filename: str, data: bytes) -> tuple:
    """Return ``(ext, data)`` ready to save; SVGs come back cleaned."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in EXTS[kind]:
        raise AssetError(f"Unsupported {kind} type: {filename or '(no name)'} "
                         f"(use {', '.join(EXTS[kind])})")
    if ext == ".svg":
        try:
            return ext, clean_svg(data)
        except SvgError as exc:
            raise AssetError(f"{filename}: {exc}") from None
    if len(data) > MAX_RASTER_BYTES:
        raise AssetError(f"{filename}: too large (max {MAX_RASTER_BYTES // (1024 * 1024)} MB)")
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
            img.verify()
    except Exception:
        raise AssetError(f"{filename}: not a readable image") from None
    if fmt != _PIL_FORMATS[ext]:
        raise AssetError(f"{filename}: file is {fmt}, not {ext[1:].upper()}")
    return (".jpg" if ext == ".jpeg" else ext), data


def _clean_tags(tags) -> list:
    if isinstance(tags, str):
        tags = re.split(r"[,\s]+", tags)
    out = []
    for tag in tags or []:
        tag = str(tag).strip().lower()
        if tag and _TAG_RE.fullmatch(tag) and tag not in out:
            out.append(tag[:30])
    return out[:MAX_TAGS]


def add_asset(folder: str, kind: str, filename: str, data: bytes,
              name: str = "", tags=None) -> dict:
    """Check and save one upload; return its manifest entry."""
    if kind not in KINDS:
        raise AssetError(f"kind must be one of: {', '.join(KINDS)}")
    name = " ".join((name or "").split())[:MAX_NAME]
    if not name:
        name = os.path.splitext(os.path.basename(filename or ""))[0].replace("_", " ").strip()[:MAX_NAME]
    if not name:
        raise AssetError("A name is required")
    assets = list_assets(folder)
    if len(assets) >= MAX_ASSETS:
        raise AssetError(f"Asset library is full ({MAX_ASSETS}); delete some first")
    ext, data = _check_file(kind, filename, data)

    asset_id = uuid.uuid4().hex[:10]
    entry = {"id": asset_id, "kind": kind, "name": name,
             "tags": _clean_tags(tags) if kind == "icon" else [],
             "file": asset_id + ext,
             "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, entry["file"]), "wb") as fh:
        fh.write(data)
    _write(folder, assets + [entry])
    return entry


def asset_path(folder: str, entry: dict) -> str:
    return os.path.join(folder, entry["file"])


def delete_asset(folder: str, asset_id: str):
    """Remove one asset; return its entry, or None if the user has no such id."""
    if not _ID_RE.match(asset_id or ""):
        return None
    assets = list_assets(folder)
    entry = next((a for a in assets if a["id"] == asset_id), None)
    if entry is None:
        return None
    _write(folder, [a for a in assets if a["id"] != asset_id])
    try:
        os.remove(asset_path(folder, entry))
    except FileNotFoundError:
        pass
    return entry


SIDECAR = "user-assets.json"


def icon_entries(folder: str) -> list:
    """The user's icons as ``{name, tags, path}`` for :func:`aippt.icons.user_icons`."""
    return [{"name": a["name"], "tags": a["tags"], "path": asset_path(folder, a)}
            for a in list_assets(folder)
            if a["kind"] == "icon" and os.path.isfile(asset_path(folder, a))]


def _length(value) -> float:
    m = re.match(r"\s*(\d+(?:\.\d+)?)", value or "")
    return float(m.group(1)) if m else 0.0


def image_size(path: str) -> tuple:
    """(width, height) of an image in its own units, for aspect-correct placement."""
    if path.lower().endswith(".svg"):
        import xml.etree.ElementTree as ET
        root = ET.parse(path).getroot()
        box = (root.get("viewBox") or "").replace(",", " ").split()
        if len(box) == 4:
            return float(box[2]), float(box[3])
        w, h = _length(root.get("width")), _length(root.get("height"))
        return (w, h) if w and h else (1.0, 1.0)
    from PIL import Image
    with Image.open(path) as img:
        return img.size


def cobrand_logo(folder: str, asset_id: str) -> dict:
    """``{path, width, height}`` of the user's logo *asset_id*; AssetError if not theirs."""
    entry = next((a for a in list_assets(folder)
                  if a["id"] == asset_id and a["kind"] == "logo"), None)
    if entry is None or not os.path.isfile(asset_path(folder, entry)):
        raise AssetError("Co-brand logo not found in your asset library")
    path = asset_path(folder, entry)
    width, height = image_size(path)
    return {"path": path, "width": width, "height": height, "name": entry["name"]}


def write_sidecar(script_dir: str, icon_paths: dict, logo: dict = None) -> str:
    """Write ``user-assets.json`` next to a deck script; the helpers read it
    in createDeck (icons by ``my-*`` id, and the co-brand logo if any)."""
    path = os.path.join(script_dir, SIDECAR)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"icons": icon_paths, "cobrand": logo}, fh, indent=1)
    return path
