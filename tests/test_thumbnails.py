"""Tests for aippt.thumbnails — canvas-captured slide thumbnail storage
and stale-image invalidation.

No browser, network, or API key is required: the canvas capture happens in
the browser; these tests exercise the server-side storage + invalidation that
receives the captured bytes.
"""
from __future__ import annotations

import base64
import io
import os

import pytest

from aippt import thumbnails
from aippt.catalog import get_db, content_hash


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def seeded(db_path):
    """A deck with two slides; returns (db_path, deck_id, [slide_ids])."""
    conn = get_db(db_path)
    cur = conn.execute(
        "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?,?,?,?)",
        ("t", "/tmp/t.pptx", "h", 2),
    )
    deck_id = cur.lastrowid
    ids = []
    for pos, (title, body) in enumerate(
        [("Intro", "welcome"), ("Details", "more")], start=1
    ):
        c = conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash) "
            "VALUES (?,?,?,?,?)",
            (deck_id, pos, title, body, content_hash(title, body)),
        )
        ids.append(c.lastrowid)
    conn.commit()
    conn.close()
    return db_path, deck_id, ids


def _png_bytes(color=(200, 30, 30)):
    """Return raw PNG bytes for a small solid image via Pillow."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 36), color).save(buf, format="PNG")
    return buf.getvalue()


def _png_b64(color=(200, 30, 30)):
    return base64.b64encode(_png_bytes(color)).decode("ascii")


# ---------------------------------------------------------------------------
# store_client_images
# ---------------------------------------------------------------------------

class TestThumbnailStorage:
    def test_writes_png_and_sets_image_path(self, seeded, tmp_path):
        db_path, deck_id, ids = seeded
        out_dir = str(tmp_path / "images" / "t")
        images = [
            {"position": 1, "data": _png_b64((10, 20, 30))},
            {"position": 2, "data": _png_b64((40, 50, 60))},
        ]
        written = thumbnails.store_client_images(
            deck_id, images, out_dir=out_dir, db_path=db_path, base_dir=str(tmp_path)
        )
        assert written == 2
        assert os.path.isfile(os.path.join(out_dir, "Slide1.png"))
        assert os.path.isfile(os.path.join(out_dir, "Slide2.png"))

        conn = get_db(db_path)
        rows = conn.execute(
            "SELECT position, image_path, image_content_hash FROM slides "
            "WHERE deck_id = ? ORDER BY position",
            (deck_id,),
        ).fetchall()
        conn.close()
        assert all(r["image_path"] for r in rows)
        # image_path is stored relative to base_dir
        assert rows[0]["image_path"] == os.path.join("images", "t", "Slide1.png")

    def test_records_content_hash_of_current_slide(self, seeded, tmp_path):
        db_path, deck_id, ids = seeded
        out_dir = str(tmp_path / "images" / "t")
        thumbnails.store_client_images(
            deck_id,
            [{"position": 1, "data": _png_b64()}],
            out_dir=out_dir,
            db_path=db_path,
            base_dir=str(tmp_path),
        )
        conn = get_db(db_path)
        row = conn.execute(
            "SELECT content_hash, image_content_hash FROM slides WHERE id = ?",
            (ids[0],),
        ).fetchone()
        conn.close()
        assert row["image_content_hash"] == row["content_hash"]

    def test_writes_downscaled_thumb_tier(self, seeded, tmp_path):
        db_path, deck_id, ids = seeded
        out_dir = str(tmp_path / "images" / "t")
        thumbnails.store_client_images(
            deck_id,
            [{"position": 1, "data": _png_b64()}],
            out_dir=out_dir,
            db_path=db_path,
            base_dir=str(tmp_path),
        )
        # A downscaled grid tier sits alongside the full PNG.
        assert os.path.isfile(os.path.join(out_dir, "Slide1.thumb.jpg"))

    def test_accepts_raw_bytes(self, seeded, tmp_path):
        db_path, deck_id, ids = seeded
        out_dir = str(tmp_path / "images" / "t")
        written = thumbnails.store_client_images(
            deck_id,
            [{"position": 1, "data": _png_bytes()}],
            out_dir=out_dir,
            db_path=db_path,
            base_dir=str(tmp_path),
        )
        assert written == 1
        assert os.path.isfile(os.path.join(out_dir, "Slide1.png"))

    def test_accepts_data_url_prefix(self, seeded, tmp_path):
        db_path, deck_id, ids = seeded
        out_dir = str(tmp_path / "images" / "t")
        data_url = "data:image/png;base64," + _png_b64()
        written = thumbnails.store_client_images(
            deck_id,
            [{"position": 1, "data": data_url}],
            out_dir=out_dir,
            db_path=db_path,
            base_dir=str(tmp_path),
        )
        assert written == 1

    def test_bad_image_skipped_gracefully(self, seeded, tmp_path):
        db_path, deck_id, ids = seeded
        out_dir = str(tmp_path / "images" / "t")
        images = [
            {"position": 1, "data": "not-valid-base64-@@@"},
            {"position": 2, "data": _png_b64()},
        ]
        # One bad image must not abort the batch or raise.
        written = thumbnails.store_client_images(
            deck_id, images, out_dir=out_dir, db_path=db_path, base_dir=str(tmp_path)
        )
        assert written == 1
        assert os.path.isfile(os.path.join(out_dir, "Slide2.png"))

    def test_empty_images_noop(self, seeded, tmp_path):
        db_path, deck_id, ids = seeded
        out_dir = str(tmp_path / "images" / "t")
        written = thumbnails.store_client_images(
            deck_id, [], out_dir=out_dir, db_path=db_path, base_dir=str(tmp_path)
        )
        assert written == 0

    def test_unknown_position_skipped(self, seeded, tmp_path):
        db_path, deck_id, ids = seeded
        out_dir = str(tmp_path / "images" / "t")
        written = thumbnails.store_client_images(
            deck_id,
            [{"position": 99, "data": _png_b64()}],
            out_dir=out_dir,
            db_path=db_path,
            base_dir=str(tmp_path),
        )
        # No slide at position 99 → nothing written to the DB, no crash.
        assert written == 0


# ---------------------------------------------------------------------------
# invalidate_slides
# ---------------------------------------------------------------------------

class TestThumbnailInvalidation:
    def test_nulls_path_and_hash(self, seeded, tmp_path):
        db_path, deck_id, ids = seeded
        out_dir = str(tmp_path / "images" / "t")
        thumbnails.store_client_images(
            deck_id,
            [{"position": 1, "data": _png_b64()}, {"position": 2, "data": _png_b64()}],
            out_dir=out_dir,
            db_path=db_path,
            base_dir=str(tmp_path),
        )
        thumbnails.invalidate_slides([ids[0]], db_path=db_path)

        conn = get_db(db_path)
        rows = {
            r["id"]: r
            for r in conn.execute(
                "SELECT id, image_path, image_content_hash FROM slides WHERE deck_id = ?",
                (deck_id,),
            ).fetchall()
        }
        conn.close()
        # Invalidated slide has both nulled …
        assert rows[ids[0]]["image_path"] is None
        assert rows[ids[0]]["image_content_hash"] is None
        # … the other is untouched.
        assert rows[ids[1]]["image_path"] is not None

    def test_empty_list_noop(self, seeded, tmp_path):
        db_path, deck_id, ids = seeded
        # Should not raise.
        thumbnails.invalidate_slides([], db_path=db_path)

    def test_unknown_id_noop(self, seeded, tmp_path):
        db_path, deck_id, ids = seeded
        thumbnails.invalidate_slides([999999], db_path=db_path)
