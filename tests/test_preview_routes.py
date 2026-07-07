"""Tests for preview REST + WebSocket endpoints."""
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from aippt.preview import PreviewSession, SessionRegistry, Renderer, RenderResult
from aippt.web.app import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def script_file(tmp_path):
    """A minimal script file inside the allow-listed output dir."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    script = output_dir / "deck.js"
    script.write_text("// test deck")
    return script


@pytest.fixture
def app(tmp_path, script_file):
    """FastAPI app with preview registry allow-listing tmp_path/output."""
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


# ---------------------------------------------------------------------------
# Helper: stub a session in the registry
# ---------------------------------------------------------------------------


def _stub_session(registry, script_path, token="testtoken123"):
    """Insert a fake PreviewSession into the registry without actually running."""
    session = MagicMock(spec=PreviewSession)
    session.token = token
    session.script_path = str(Path(script_path).resolve())
    session.out_dir = "/tmp/preview/deck"
    session.last_state = {"event": "idle"}
    session.add_client = MagicMock()
    session.remove_client = MagicMock()
    session.force_render = AsyncMock()
    session.stop = AsyncMock()
    registry._sessions[token] = session
    return session


# ---------------------------------------------------------------------------
# REST endpoint tests
# ---------------------------------------------------------------------------


class TestPreviewAPI:
    def test_create_session_view_only_returns_403(self, view_only_client, script_file):
        resp = view_only_client.post(
            "/api/preview/sessions",
            json={"script": str(script_file)},
        )
        assert resp.status_code == 403

    def test_create_session_missing_script_field_returns_400(self, client):
        resp = client.post("/api/preview/sessions", json={})
        assert resp.status_code == 400

    def test_create_session_outside_allowlist_returns_403(self, client, tmp_path):
        outside = tmp_path / "sneaky.js"
        outside.write_text("// evil")
        resp = client.post(
            "/api/preview/sessions",
            json={"script": str(outside)},
        )
        assert resp.status_code == 403

    def test_create_session_missing_file_returns_404(self, client, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir(exist_ok=True)
        missing = output_dir / "missing.js"
        resp = client.post(
            "/api/preview/sessions",
            json={"script": str(missing)},
        )
        assert resp.status_code == 404

    def test_create_session_success(self, client, app, script_file):
        registry = app.state.preview_registry

        async def _fake_start(self):
            pass

        with patch.object(PreviewSession, "start", _fake_start):
            resp = client.post(
                "/api/preview/sessions",
                json={"script": str(script_file)},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["ws_url"].startswith("/ws/preview/")
        assert data["script"] == str(script_file.resolve())

    def test_get_session_not_found_returns_404(self, client):
        resp = client.get("/api/preview/sessions/badtoken")
        assert resp.status_code == 404

    def test_get_session_returns_state(self, client, app, script_file):
        session = _stub_session(app.state.preview_registry, str(script_file))
        resp = client.get(f"/api/preview/sessions/{session.token}")
        assert resp.status_code == 200
        assert resp.json()["token"] == session.token

    def test_delete_session_not_found_returns_404(self, client):
        resp = client.delete("/api/preview/sessions/badtoken")
        assert resp.status_code == 404

    def test_delete_session_success(self, client, app, script_file):
        session = _stub_session(app.state.preview_registry, str(script_file))
        resp = client.delete(f"/api/preview/sessions/{session.token}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"
        assert app.state.preview_registry.get(session.token) is None

    def test_pptx_not_found_session(self, client):
        resp = client.get("/api/preview/sessions/badtoken/pptx")
        assert resp.status_code == 404

    def test_pptx_no_render_yet(self, client, app, script_file):
        session = _stub_session(app.state.preview_registry, str(script_file))
        session.last_pptx_path = None
        resp = client.get(f"/api/preview/sessions/{session.token}/pptx")
        assert resp.status_code == 404


class TestPreviewScripts:
    def test_list_scripts_returns_list(self, client, app, script_file):
        resp = client.get("/api/preview/scripts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_excludes_preview_artifacts(self, client, app):
        root = Path(app.state.project_root)
        preview_dir = root / "output" / ".preview" / "deck"
        preview_dir.mkdir(parents=True, exist_ok=True)
        (preview_dir / "hidden.js").write_text("// should be hidden")
        resp = client.get("/api/preview/scripts")
        paths = [r["path"] for r in resp.json()]
        assert not any(".preview" in Path(p).parts for p in paths)

    def test_excludes_node_modules(self, client, app):
        root = Path(app.state.project_root)
        nm = root / "output" / "node_modules"
        nm.mkdir(parents=True, exist_ok=True)
        (nm / "pkg.js").write_text("// npm")
        resp = client.get("/api/preview/scripts")
        paths = [r["path"] for r in resp.json()]
        assert not any("node_modules" in Path(p).parts for p in paths)


class TestViewOnlyPreview:
    def test_create_session_blocked(self, view_only_client, script_file):
        resp = view_only_client.post(
            "/api/preview/sessions",
            json={"script": str(script_file)},
        )
        assert resp.status_code == 403
        assert "view-only" in resp.json()["error"].lower()
