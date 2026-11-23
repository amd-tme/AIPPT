"""Per-user asset library: /api/assets upload, list, file, delete."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from aippt import user_assets
from aippt.user_assets import AssetError

SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
       b'<script>alert(1)</script><rect width="5" height="5" onclick="x()"/></svg>')


def _raster(fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "#00C2DE").save(buf, fmt)
    return buf.getvalue()


@pytest.fixture
def app(tmp_path):
    from aippt.web.app import create_app
    return create_app(db_path=str(tmp_path / "slides.db"), uploads_dir=str(tmp_path / "uploads"),
                      images_dir=str(tmp_path / "images"), view_only=False)


def _client(app, ntid="alice"):
    client = TestClient(app)
    if ntid is not None:
        client.headers["X-AIPPT-NTID"] = ntid
    return client


def _upload(client, filename, data, kind="icon", **form):
    return client.post("/api/assets", data={"kind": kind, **form},
                       files={"file": (filename, data)})


# ── module ──────────────────────────────────────────────────────────────

def test_add_list_delete(tmp_path):
    folder = str(tmp_path / "u")
    icon = user_assets.add_asset(folder, "icon", "cloud.svg", SVG, name="Partner  Cloud",
                                 tags="Cloud, hosting cloud bad/tag")
    assert icon["name"] == "Partner Cloud"
    assert icon["tags"] == ["cloud", "hosting"]
    assert icon["file"] == icon["id"] + ".svg"
    saved = (tmp_path / "u" / icon["file"]).read_bytes()
    assert b"<rect" in saved and b"script" not in saved and b"onclick" not in saved

    logo = user_assets.add_asset(folder, "logo", "Acme_Corp.jpeg", _raster("JPEG"), tags="ignored")
    assert logo["name"] == "Acme Corp" and logo["tags"] == [] and logo["file"].endswith(".jpg")
    assert [a["id"] for a in user_assets.list_assets(folder)] == [icon["id"], logo["id"]]

    assert user_assets.delete_asset(folder, icon["id"])["id"] == icon["id"]
    assert not (tmp_path / "u" / icon["file"]).exists()
    assert [a["id"] for a in user_assets.list_assets(folder)] == [logo["id"]]
    assert user_assets.delete_asset(folder, icon["id"]) is None
    assert user_assets.delete_asset(folder, "../manifest") is None


@pytest.mark.parametrize("kind,filename,data,message", [
    ("photo", "a.png", _raster(), "kind must be"),
    ("icon", "a.jpg", _raster("JPEG"), "Unsupported icon type"),
    ("logo", "run.sh", b"echo", "Unsupported logo type"),
    ("logo", "a.png", _raster("JPEG"), "not PNG"),
    ("logo", "a.png", b"not an image", "not a readable image"),
    ("logo", "a.png", b"x" * (user_assets.MAX_RASTER_BYTES + 1), "too large"),
    ("icon", "a.svg", b"<html/>", "Not an SVG"),
    ("icon", "_.svg", SVG, "name is required"),
])
def test_bad_uploads_are_rejected(tmp_path, kind, filename, data, message):
    with pytest.raises(AssetError, match=message):
        user_assets.add_asset(str(tmp_path / "u"), kind, filename, data)
    assert user_assets.list_assets(str(tmp_path / "u")) == []


def test_library_size_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(user_assets, "MAX_ASSETS", 2)
    folder = str(tmp_path / "u")
    for i in range(2):
        user_assets.add_asset(folder, "icon", f"i{i}.svg", SVG)
    with pytest.raises(AssetError, match="full"):
        user_assets.add_asset(folder, "icon", "i3.svg", SVG)


@pytest.mark.parametrize("ntid", ["", "..", "a/b", "a b"])
def test_user_dir_needs_a_safe_ntid(tmp_path, ntid):
    with pytest.raises(AssetError):
        user_assets.user_dir(str(tmp_path), ntid)


# ── routes ──────────────────────────────────────────────────────────────

def test_upload_list_file_delete_over_http(app, tmp_path):
    alice = _client(app)
    resp = _upload(alice, "cloud.svg", SVG, name="Partner Cloud", tags="cloud,hosting")
    assert resp.status_code == 200, resp.text
    icon = resp.json()["asset"]
    folder = tmp_path / "uploads" / "assets" / "users" / "alice"
    assert json.loads((folder / "manifest.json").read_text())["assets"] == [icon]

    listed = alice.get("/api/assets").json()
    assert listed["assets"] == [icon] and listed["max_assets"] == user_assets.MAX_ASSETS

    got = alice.get(f"/api/assets/{icon['id']}/file")
    assert got.status_code == 200 and b"<rect" in got.content and b"script" not in got.content
    assert "default-src 'none'" in got.headers["content-security-policy"]

    assert alice.delete(f"/api/assets/{icon['id']}").json() == {"deleted": icon["id"]}
    assert alice.get("/api/assets").json()["assets"] == []
    assert alice.get(f"/api/assets/{icon['id']}/file").status_code == 404


def test_users_only_see_their_own_assets(app):
    alice, bob = _client(app, "alice"), _client(app, "bob")
    icon = _upload(alice, "cloud.svg", SVG).json()["asset"]
    assert bob.get("/api/assets").json()["assets"] == []
    assert bob.get(f"/api/assets/{icon['id']}/file").status_code == 404
    assert bob.delete(f"/api/assets/{icon['id']}").status_code == 404
    assert [a["id"] for a in alice.get("/api/assets").json()["assets"]] == [icon["id"]]


@pytest.mark.parametrize("ntid,status", [(None, 400), ("a/b", 400)])
def test_ntid_is_required(app, ntid, status):
    client = _client(app, ntid)
    assert client.get("/api/assets").status_code == status
    assert _upload(client, "cloud.svg", SVG).status_code == status


def test_bad_upload_is_a_400(app):
    resp = _upload(_client(app), "run.sh", b"echo hi", kind="logo")
    assert resp.status_code == 400
    assert "Unsupported logo type" in resp.json()["error"]


def test_view_only_blocks_changes(tmp_path):
    from aippt.web.app import create_app
    app = create_app(db_path=str(tmp_path / "slides.db"), uploads_dir=str(tmp_path / "uploads"),
                     images_dir=str(tmp_path / "images"), view_only=True)
    client = _client(app)
    assert _upload(client, "cloud.svg", SVG).status_code == 403
    assert client.delete("/api/assets/0123456789").status_code == 403
    assert client.get("/api/assets").json()["assets"] == []
