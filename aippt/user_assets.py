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
