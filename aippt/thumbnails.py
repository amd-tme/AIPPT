"""Slide thumbnail storage and stale-image invalidation.

Script/preview-origin decks (``origin.kind == "script"``) are cataloged
without slide rasters, so the deck and chat views fall back to placeholder
cards and ``GET /slide-image/{id}`` 404s. This module receives per-slide
images captured in the browser (PptxViewJS ``renderSlide`` → ``canvas.toBlob``)
at Save-to-Library time and wires them into the existing
``slides.image_path`` + object-storage plumbing, so downstream
(``serve_slide_image``, ``asset_sync``, multimodal LLM helpers) is unchanged.

It also provides cheap, always-safe *invalidation*: when a slide's content
changes (chat Edit apply/revert, deck regenerate) the affected slide's
``image_path`` is nulled so the UI falls back to a placeholder rather than
showing a stale thumbnail. A ``image_content_hash`` freshness marker records
the slide's ``content_hash`` at generation time.

Everything here is best-effort: a bad image, missing Pillow, or a write
error logs and skips — it never raises into the catalog/apply/revert path,
so those flows never turn a success into a 500.

Writes land only under the caller-supplied ``out_dir`` (in the web layer,
``app.state.images_dir`` → ``/app/data/images`` in prod), never ``/app`` —
satisfying ``readOnlyRootFilesystem``.
"""
from __future__ import annotations

import base64
import binascii
import logging
import os
import sqlite3
from typing import Iterable, List, Optional, Union

logger = logging.getLogger(__name__)

# Grid-card tier: downscaled JPEG kept alongside the full PNG to bound page
# weight and object-storage footprint. Full PNG remains the LLM-analysis image.
_THUMB_MAX_WIDTH = 480
_THUMB_SUFFIX = ".thumb.jpg"
_THUMB_QUALITY = 80

ImageData = Union[str, bytes]


def _decode_image(data: ImageData) -> Optional[bytes]:
    """Decode one image payload to raw bytes, or None if it can't be decoded.

    Accepts raw ``bytes``, a bare base64 string, or a ``data:...;base64,`` URL.
    """
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if not isinstance(data, str) or not data:
        return None
    payload = data
    if payload.startswith("data:"):
        # data:image/png;base64,XXXX
        comma = payload.find(",")
        if comma == -1:
            return None
        payload = payload[comma + 1:]
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        return None


def _write_downscaled(full_png_path: str, out_dir: str, position: int) -> None:
    """Best-effort downscaled grid tier next to the full PNG.

    Missing Pillow or any render error is swallowed — the full PNG is what
    ``image_path`` points at, so the grid tier is a pure optimization.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.debug("Pillow not available; skipping thumbnail downscale tier")
        return
    try:
        with Image.open(full_png_path) as im:
            im = im.convert("RGB")
            if im.width > _THUMB_MAX_WIDTH:
                ratio = _THUMB_MAX_WIDTH / float(im.width)
                im = im.resize(
                    (_THUMB_MAX_WIDTH, max(1, round(im.height * ratio))),
                    Image.LANCZOS,
                )
            thumb_path = os.path.join(out_dir, f"Slide{position}{_THUMB_SUFFIX}")
            im.save(thumb_path, format="JPEG", quality=_THUMB_QUALITY)
    except Exception:
        logger.exception("Failed to write downscaled thumbnail for slide %d", position)


def store_client_images(
    deck_id: int,
    images: Iterable[dict],
    *,
    out_dir: str,
    db_path: str,
    base_dir: Optional[str] = None,
) -> int:
    """Persist browser-captured slide images and wire them to ``slides.image_path``.

    Args:
        deck_id: The deck whose slides these images belong to.
        images: Iterable of ``{"position": int, "data": bytes|str}`` where
            ``data`` is raw PNG bytes, a base64 string, or a data URL.
        out_dir: Directory to write ``Slide{N}.png`` into (created if absent).
            Must be on a writable volume.
        db_path: SQLite database path.
        base_dir: Base for the stored relative ``image_path`` (default: cwd),
            matching ``catalog_deck``'s convention.

    Returns:
        The number of slide rows whose ``image_path`` was set.
    """
    base = base_dir or os.getcwd()
    written = 0
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError:
        logger.exception("Cannot create thumbnail out_dir %s", out_dir)
        return 0

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        for entry in images or []:
            try:
                position = int(entry.get("position"))
            except (TypeError, ValueError, AttributeError):
                continue
            raw = _decode_image(entry.get("data"))
            if not raw:
                logger.warning(
                    "Skipping thumbnail for deck %s position %s: undecodable image",
                    deck_id, entry.get("position"),
                )
                continue

            row = conn.execute(
                "SELECT id, content_hash FROM slides WHERE deck_id = ? AND position = ?",
                (deck_id, position),
            ).fetchone()
            if row is None:
                logger.warning(
                    "Skipping thumbnail: no slide at deck %s position %s",
                    deck_id, position,
                )
                continue

            png_path = os.path.join(out_dir, f"Slide{position}.png")
            try:
                with open(png_path, "wb") as fh:
                    fh.write(raw)
            except OSError:
                logger.exception("Failed to write thumbnail %s", png_path)
                continue

            _write_downscaled(png_path, out_dir, position)

            rel = os.path.relpath(os.path.abspath(png_path), base)
            conn.execute(
                "UPDATE slides SET image_path = ?, image_content_hash = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (rel, row["content_hash"], row["id"]),
            )
            written += 1
        conn.commit()
    except Exception:
        logger.exception("store_client_images failed for deck %s", deck_id)
    finally:
        if conn is not None:
            conn.close()
    return written


def invalidate_slides(slide_ids: Iterable[int], *, db_path: str) -> int:
    """Null ``image_path`` + ``image_content_hash`` for the given slides.

    Called after a slide's content changes so the UI falls back to a
    placeholder card instead of showing a stale thumbnail. Cheap and always
    safe: unknown ids are ignored, an empty list is a no-op, and any error is
    swallowed so it can't break the apply/revert/regenerate path.

    Returns the number of rows updated.
    """
    ids: List[int] = []
    for sid in slide_ids or []:
        try:
            ids.append(int(sid))
        except (TypeError, ValueError):
            continue
    if not ids:
        return 0

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
        placeholders = ",".join("?" for _ in ids)
        cur = conn.execute(
            f"UPDATE slides SET image_path = NULL, image_content_hash = NULL, "  # noqa: S608
            f"updated_at = datetime('now') WHERE id IN ({placeholders})",
            ids,
        )
        conn.commit()
        return cur.rowcount or 0
    except Exception:
        logger.exception("invalidate_slides failed for ids %s", ids)
        return 0
    finally:
        if conn is not None:
            conn.close()
