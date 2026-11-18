"""IMAGE: uploads on POST /api/decks/create: saved per job, safely named,
and readable by the pptxgenjs render (which used to show a placeholder)."""
import os
import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aippt.web.routes import _image_upload_error, _stage_image_uploads

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _png():
    """A valid 1x1 PNG."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\x00\x00\x00')) + chunk(b'IEND', b''))


def test_images_are_saved_in_the_job_folder_and_lines_rewritten(tmp_path):
    job = tmp_path / "assets" / "jobs" / "abc"
    md = "# A\nIMAGE: imgs/photo.png\n# B\nIMAGE: missing.png\n"
    out = _stage_image_uploads(md, str(job), [("photo.png", b"x")])
    saved = job.resolve() / "photo.png"
    assert saved.read_bytes() == b"x"
    assert f"IMAGE: {saved}" in out
    # Lines without an upload are left alone
    assert "IMAGE: missing.png" in out


def test_upload_names_cannot_leave_the_job_folder(tmp_path):
    job = tmp_path / "jobs" / "abc"
    md = "IMAGE: ../../evil.png\nIMAGE: my logo.png\n"
    out = _stage_image_uploads(md, str(job), [("../../evil.png", b"e"), ("my logo.png", b"l")])
    assert sorted(p.name for p in job.iterdir()) == ["evil.png", "my_logo.png"]
    assert not (tmp_path / "evil.png").exists()
    assert f"IMAGE: {job.resolve() / 'evil.png'}" in out
    assert f"IMAGE: {job.resolve() / 'my_logo.png'}" in out


def test_two_jobs_with_the_same_name_do_not_collide(tmp_path):
    a = _stage_image_uploads("IMAGE: logo.png", str(tmp_path / "a"), [("logo.png", b"A")])
    b = _stage_image_uploads("IMAGE: logo.png", str(tmp_path / "b"), [("logo.png", b"B")])
    assert a != b
    assert (tmp_path / "a" / "logo.png").read_bytes() == b"A"
    assert (tmp_path / "b" / "logo.png").read_bytes() == b"B"


def test_upload_type_and_size_are_checked():
    assert _image_upload_error([("a.png", b"x"), ("b.JPG", b"x")]) is None
    assert "Unsupported image type" in _image_upload_error([("run.sh", b"x")])
    assert "too large" in _image_upload_error([("big.png", b"x" * (10 * 1024 * 1024 + 1))])


def test_route_rejects_unsupported_uploads(tmp_path):
    from aippt.web.app import create_app

    app = create_app(db_path=str(tmp_path / "slides.db"), uploads_dir=str(tmp_path / "uploads"),
                     images_dir=str(tmp_path / "images"), view_only=False)
    resp = TestClient(app).post(
        "/api/decks/create",
        data={"outline_text": "# A\nIMAGE: run.sh\n", "engine": "pptxgenjs-direct"},
        files=[("image_files", ("run.sh", b"echo hi", "text/plain"))],
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 400
    assert "Unsupported image type" in resp.json()["error"]
    assert not (tmp_path / "uploads" / "assets" / "jobs").exists()


def test_staged_image_renders_in_a_pptxgenjs_deck(tmp_path):
    """The no-LLM deck embeds the uploaded picture instead of a placeholder."""
    import shutil
    from pptx import Presentation

    from aippt.pptxgenjs_direct import generate_script
    from aippt.preview import Renderer
    from aippt.web.routes import _stage_render_workspace

    if not shutil.which("node") or Renderer(project_root=str(PROJECT_ROOT))._find_node_modules() is None:
        pytest.skip("node / node_modules not available")
    # Same layout as the app: uploads/ inside the project root (gitignored)
    uploads = PROJECT_ROOT / "uploads"
    job_id = f"pytest-image-{tmp_path.name}"
    try:
        md = _stage_image_uploads("# Deck\n\n# Photo\nIMAGE: photo.png\n",
                                  str(uploads / "assets" / "jobs" / job_id), [("photo.png", _png())])
        script, out = _stage_render_workspace(str(uploads), job_id, "deck", str(PROJECT_ROOT))
        generate_script(outline_text=md, output_script_path=script, theme="amd")
        result = Renderer(project_root=str(PROJECT_ROOT)).render(script, out)
        assert result.success, result.stderr_tail
        slides = list(Presentation(result.pptx_path).slides)
    finally:
        shutil.rmtree(uploads / job_id, ignore_errors=True)
        shutil.rmtree(uploads / "assets" / "jobs" / job_id, ignore_errors=True)

    texts = [s.text_frame.text for sl in slides for s in sl.shapes if s.has_text_frame]
    assert not [t for t in texts if t.startswith("[Image:")]
    blobs = [s.image.blob for sl in slides for s in sl.shapes if s.shape_type == 13]
    assert _png() in blobs
