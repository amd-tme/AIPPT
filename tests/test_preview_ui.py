"""Tests for Live Preview UI — static assets, view-only behaviour."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aippt.web.app import create_app


STATIC_DIR = Path(__file__).parent.parent / "aippt" / "web" / "static"


@pytest.fixture
def app(tmp_path):
    return create_app(
        db_path=str(tmp_path / "test.db"),
        uploads_dir=str(tmp_path / "uploads"),
        images_dir=str(tmp_path / "images"),
        project_root=str(tmp_path),
        view_only=False,
        preview_allow_dirs=[str(tmp_path / "output")],
    )


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def view_only_app(tmp_path):
    return create_app(
        db_path=str(tmp_path / "test.db"),
        uploads_dir=str(tmp_path / "uploads"),
        images_dir=str(tmp_path / "images"),
        project_root=str(tmp_path),
        view_only=True,
        preview_allow_dirs=[str(tmp_path / "output")],
    )


@pytest.fixture
def view_only_client(view_only_app):
    return TestClient(view_only_app)


class TestStaticAssets:
    def test_preview_js_served(self, client):
        resp = client.get("/static/preview.js")
        assert resp.status_code == 200
        assert "javascript" in resp.headers.get("content-type", "")

    def test_preview_css_served(self, client):
        resp = client.get("/static/preview.css")
        assert resp.status_code == 200
        assert "css" in resp.headers.get("content-type", "")

    def test_index_references_preview_js(self):
        html = (STATIC_DIR / "index.html").read_text()
        assert "preview.js" in html

    def test_index_references_preview_css(self):
        html = (STATIC_DIR / "index.html").read_text()
        assert "preview.css" in html

    def test_index_has_live_preview_nav(self):
        html = (STATIC_DIR / "index.html").read_text()
        assert "Live Preview" in html

    def test_index_has_preview_section(self):
        html = (STATIC_DIR / "index.html").read_text()
        assert 'id="preview-view"' in html

    def test_index_hides_preview_in_view_only(self):
        """Verify applyViewOnlyMode hides nav-preview-item."""
        html = (STATIC_DIR / "index.html").read_text()
        assert "nav-preview-item" in html
        assert "previewItem" in html or "nav-preview-item" in html


class TestViewOnlyAPI:
    def test_config_reports_view_only(self, view_only_client):
        resp = view_only_client.get("/api/config")
        assert resp.status_code == 200
        assert resp.json().get("view_only") is True

    def test_config_reports_not_view_only(self, client):
        resp = client.get("/api/config")
        assert resp.status_code == 200
        assert resp.json().get("view_only") is False

    def test_preview_sessions_blocked_in_view_only(self, view_only_client, tmp_path):
        resp = view_only_client.post(
            "/api/preview/sessions",
            json={"script": str(tmp_path / "output" / "deck.js")},
        )
        assert resp.status_code == 403


class TestScriptsEndpoint:
    def test_scripts_endpoint_exists(self, client):
        resp = client.get("/api/preview/scripts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_scripts_picks_up_js_files(self, client, app, tmp_path):
        out = Path(app.state.project_root) / "output"
        out.mkdir(exist_ok=True)
        (out / "mydeck.js").write_text("// deck")
        resp = client.get("/api/preview/scripts")
        names = [r["name"] for r in resp.json()]
        assert "mydeck.js" in names
