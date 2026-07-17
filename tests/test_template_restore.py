"""Tests for restoring the corporate PPTX template from object storage.

Mirrors the catalog snapshot/restore contract (see test_catalog_snapshot.py):
``FsStorage`` against ``tmp_path`` proves the round-trip end-to-end without
object-storage credentials. The contract is identical for ``S3Storage`` -- only
the ``put``/``get``/``exists`` backend differs.
"""
import os

from aippt.templates_store import restore_template, TEMPLATE_SNAPSHOT_KEY
from aippt.storage import FsStorage


def test_restore_writes_template_when_present(tmp_path):
    store_root = tmp_path / "store"
    storage = FsStorage(str(store_root))
    # Seed the object store with a template blob under the canonical key.
    storage.put(TEMPLATE_SNAPSHOT_KEY, b"PPTX-BYTES")

    local = str(tmp_path / "data" / "templates" / "corp.pptx")
    assert restore_template(local, storage) is True
    assert os.path.isfile(local)
    with open(local, "rb") as fh:
        assert fh.read() == b"PPTX-BYTES"


def test_restore_missing_key_returns_false(tmp_path):
    storage = FsStorage(str(tmp_path / "store"))
    local = str(tmp_path / "data" / "templates" / "corp.pptx")
    assert restore_template(local, storage) is False
    assert not os.path.exists(local)


def test_restore_creates_parent_dirs(tmp_path):
    storage = FsStorage(str(tmp_path / "store"))
    storage.put(TEMPLATE_SNAPSHOT_KEY, b"X")
    local = str(tmp_path / "deep" / "nested" / "templates" / "corp.pptx")
    assert restore_template(local, storage) is True
    assert os.path.isfile(local)


def test_restore_overwrites_existing_local_file(tmp_path):
    storage = FsStorage(str(tmp_path / "store"))
    storage.put(TEMPLATE_SNAPSHOT_KEY, b"NEW")
    local = tmp_path / "data" / "templates" / "corp.pptx"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"OLD")
    assert restore_template(str(local), storage) is True
    assert local.read_bytes() == b"NEW"


def test_restore_never_raises_on_backend_error(tmp_path):
    """A storage hiccup must be swallowed (best-effort), returning False so the
    caller falls back to whatever template path already exists."""

    class BoomStorage(FsStorage):
        def exists(self, key):
            return True

        def get(self, key):
            raise RuntimeError("backend down")

    storage = BoomStorage(str(tmp_path / "store"))
    local = str(tmp_path / "data" / "templates" / "corp.pptx")
    assert restore_template(local, storage) is False
    assert not os.path.exists(local)


def test_custom_key_is_honored(tmp_path):
    storage = FsStorage(str(tmp_path / "store"))
    storage.put("templates/other.pptx", b"OTHER")
    local = str(tmp_path / "data" / "templates" / "corp.pptx")
    assert restore_template(local, storage, key="templates/other.pptx") is True
    with open(local, "rb") as fh:
        assert fh.read() == b"OTHER"


# ---------------------------------------------------------------------------
# Startup wiring: the lifespan restores the template in s3 mode only.
# ---------------------------------------------------------------------------


def _make_app_with_fake_s3(tmp_path, monkeypatch, backend, seed_template=True):
    """Build the app with build_storage() stubbed to an FsStorage-backed fake,
    so the s3 lifespan path runs without minio or credentials."""
    import aippt.web.app as app_mod
    from aippt.config import StorageConfig

    store = FsStorage(str(tmp_path / "objstore"))
    if seed_template:
        store.put(TEMPLATE_SNAPSHOT_KEY, b"CORP-PPTX")

    monkeypatch.setattr(app_mod, "build_storage", lambda cfg, fs_root: store)
    monkeypatch.setattr(
        app_mod,
        "load_storage_config",
        lambda backend_arg=None: StorageConfig(
            backend=backend, endpoint=None, bucket=None, prefix="asic/aippt/",
            access_key=None, secret_key=None, ca_bundle=None, secure=True,
        ),
    )
    # Point the resolved template path into the writable data dir.
    target = str(tmp_path / "data" / "templates" / "corp.pptx")
    monkeypatch.setenv("AIPPT_TEMPLATE_PATH", target)

    app = app_mod.create_app(
        db_path=str(tmp_path / "data" / "slides.db"),
        uploads_dir=str(tmp_path / "data" / "uploads"),
        images_dir=str(tmp_path / "data" / "images"),
        data_dir=str(tmp_path / "data"),
        storage_backend=backend,
        view_only=True,
    )
    return app, target


def test_lifespan_restores_template_in_s3_mode(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    app, target = _make_app_with_fake_s3(tmp_path, monkeypatch, backend="s3")
    with TestClient(app):  # triggers lifespan startup
        assert os.path.isfile(target)
        with open(target, "rb") as fh:
            assert fh.read() == b"CORP-PPTX"


def test_lifespan_skips_template_restore_in_fs_mode(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    app, target = _make_app_with_fake_s3(tmp_path, monkeypatch, backend="fs")
    with TestClient(app):
        assert not os.path.exists(target)
