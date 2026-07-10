"""Tests for aippt.preview — Renderer, discover_local_imports, SessionRegistry."""
import asyncio
import os
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aippt.preview import (
    PreviewSession,
    Renderer,
    RenderResult,
    SessionRegistry,
    discover_local_imports,
)


# ---------------------------------------------------------------------------
# Renderer tests
# ---------------------------------------------------------------------------


class TestRenderer:
    def test_build_command_js(self, tmp_path):
        r = Renderer()
        script = tmp_path / "deck.js"
        script.touch()
        cmd, stage = r._build_command(script)
        assert cmd[0] == "node"
        assert stage == "node"

    def test_build_command_mjs(self, tmp_path):
        r = Renderer()
        script = tmp_path / "deck.mjs"
        script.touch()
        cmd, stage = r._build_command(script)
        assert cmd[0] == "node"
        assert stage == "node"

    def test_build_command_py(self, tmp_path):
        r = Renderer()
        script = tmp_path / "deck.py"
        script.touch()
        cmd, stage = r._build_command(script)
        assert "python" in cmd[0].lower()
        assert stage == "python"

    def test_render_fails_on_nonzero_exit(self, tmp_path):
        r = Renderer()
        script = tmp_path / "bad.js"
        script.write_text("process.exit(1);")
        out = tmp_path / "out"

        fake_result = MagicMock()
        fake_result.returncode = 1
        fake_result.stderr = "SyntaxError: bad script"
        fake_result.stdout = ""

        with patch.object(r, "_run", return_value=fake_result):
            result = r.render(str(script), str(out))

        assert not result.success
        assert result.stage == "node"
        assert result.exit_code == 1
        assert "SyntaxError" in (result.stderr_tail or "")

    def test_render_fails_when_no_pptx_found(self, tmp_path):
        r = Renderer()
        script = tmp_path / "deck.js"
        script.write_text("// ok")
        out = tmp_path / "out"
        out.mkdir()

        ok_result = MagicMock()
        ok_result.returncode = 0
        ok_result.stderr = ""
        ok_result.stdout = ""

        with patch.object(r, "_run", return_value=ok_result):
            result = r.render(str(script), str(out))

        assert not result.success
        assert "No .pptx" in (result.stderr_tail or "")

    def test_find_pptx_picks_newest(self, tmp_path):
        import time
        old = tmp_path / "old.pptx"
        new = tmp_path / "new.pptx"
        old.write_bytes(b"PK")
        time.sleep(0.01)
        new.write_bytes(b"PK")

        start = time.time() - 1
        found = Renderer._find_pptx(tmp_path / "script.js", tmp_path, wall_start=start)
        assert found is not None
        assert found.name == "new.pptx"

    def test_find_pptx_rejects_stale_files(self, tmp_path):
        """A .pptx older than wall_start must not count as a fresh render.

        Regression: the mtime cutoff used to compare epoch mtimes against a
        ``time.monotonic()`` start, which is always smaller, so any pre-existing
        .pptx was returned as a false success.
        """
        import time
        stale = tmp_path / "stale.pptx"
        stale.write_bytes(b"PK")
        # Backdate the file well before the render started.
        old_ts = time.time() - 3600
        os.utime(stale, (old_ts, old_ts))

        start = time.time()
        found = Renderer._find_pptx(tmp_path / "script.js", tmp_path, wall_start=start)
        assert found is None

    def test_render_fails_when_script_writes_nothing(self, tmp_path):
        """Script exits 0 but emits no fresh .pptx → failure, not stale reuse."""
        import time
        r = Renderer(project_root=str(tmp_path))
        script = tmp_path / "noop.js"
        script.write_text("// writes nothing")
        out = tmp_path / "out"
        out.mkdir()
        # A stale, pre-existing pptx that must NOT be served as success.
        stale = out / "stale.pptx"
        stale.write_bytes(b"PK")
        old_ts = time.time() - 3600
        os.utime(stale, (old_ts, old_ts))

        ok = MagicMock(returncode=0, stderr="", stdout="")
        with patch.object(r, "_run", return_value=ok):
            result = r.render(str(script), str(out))

        assert not result.success
        assert "No .pptx" in (result.stderr_tail or "")

    def test_render_success_returns_pptx(self, tmp_path):
        """A successful script run that emits a .pptx yields success + pptx_path.

        PptxViewJS mode stops at the .pptx — there is no LibreOffice/pdftoppm
        stage — so the script running cleanly and a fresh .pptx existing is the
        whole success path.
        """
        r = Renderer(project_root=str(tmp_path))
        script = tmp_path / "deck.js"
        script.write_text("// ok")
        out = tmp_path / "out"
        out.mkdir()
        pptx = out / "deck.pptx"

        # Simulate the script writing the .pptx during the run, so its mtime is
        # after the render's wall_start (mirrors a real render).
        def fake_run(cmd, **kwargs):
            pptx.write_bytes(b"PK")
            return MagicMock(returncode=0, stderr="", stdout="")

        with patch.object(r, "_run", side_effect=fake_run):
            result = r.render(str(script), str(out))

        assert result.success
        assert result.pptx_path == str(pptx.resolve())
        assert result.duration_ms is not None


# ---------------------------------------------------------------------------
# discover_local_imports tests
# ---------------------------------------------------------------------------


class TestImportDiscovery:
    def test_finds_require_relative(self, tmp_path):
        helper = tmp_path / "helpers.js"
        helper.write_text("// helper")
        script = tmp_path / "deck.js"
        script.write_text("const h = require('./helpers.js');")

        found = discover_local_imports(str(script), str(tmp_path))
        assert str(helper.resolve()) in found

    def test_finds_es_import(self, tmp_path):
        helper = tmp_path / "lib.mjs"
        helper.write_text("// lib")
        script = tmp_path / "deck.mjs"
        script.write_text("import stuff from './lib.mjs';")

        found = discover_local_imports(str(script), str(tmp_path))
        assert str(helper.resolve()) in found

    def test_ignores_node_modules(self, tmp_path):
        script = tmp_path / "deck.js"
        script.write_text("const x = require('node_modules/pptxgenjs');")

        found = discover_local_imports(str(script), str(tmp_path))
        assert found == []

    def test_ignores_bare_specifiers(self, tmp_path):
        script = tmp_path / "deck.js"
        script.write_text("const x = require('pptxgenjs');")

        found = discover_local_imports(str(script), str(tmp_path))
        assert found == []

    def test_ignores_nonexistent_paths(self, tmp_path):
        script = tmp_path / "deck.js"
        script.write_text("const x = require('./does-not-exist.js');")

        found = discover_local_imports(str(script), str(tmp_path))
        assert found == []

    def test_ignores_paths_outside_project_root(self, tmp_path):
        outside = tmp_path.parent / "outside.js"
        outside.write_text("// outside")
        script = tmp_path / "deck.js"
        script.write_text(f"const x = require('../outside.js');")

        found = discover_local_imports(str(script), str(tmp_path))
        assert found == []

    def test_no_duplicates(self, tmp_path):
        helper = tmp_path / "helper.js"
        helper.write_text("// h")
        script = tmp_path / "deck.js"
        script.write_text(
            "const a = require('./helper.js');\nconst b = require('./helper.js');"
        )

        found = discover_local_imports(str(script), str(tmp_path))
        assert found.count(str(helper.resolve())) == 1


# ---------------------------------------------------------------------------
# SessionRegistry tests
# ---------------------------------------------------------------------------


class TestSessionRegistry:
    def test_rejects_script_outside_allow_list(self, tmp_path):
        registry = SessionRegistry(allow_dirs=[str(tmp_path / "allowed")])
        script = tmp_path / "bad.js"
        script.write_text("// bad")

        with pytest.raises(ValueError, match="outside the allowed"):
            asyncio.run(registry.create(str(script)))

    def test_rejects_missing_script(self, tmp_path):
        registry = SessionRegistry(allow_dirs=[str(tmp_path)])

        with pytest.raises(FileNotFoundError):
            asyncio.run(registry.create(str(tmp_path / "missing.js")))

    def test_returns_existing_session_for_same_script(self, tmp_path):
        script = tmp_path / "deck.js"
        script.write_text("// ok")

        registry = SessionRegistry(allow_dirs=[str(tmp_path)])

        async def _run():
            # Patch start to a no-op so create() doesn't spawn a watcher.
            async def _noop_start(self):
                pass
            with patch.object(PreviewSession, "start", _noop_start):
                s1 = await registry.create(str(script))
                s2 = await registry.create(str(script))
                assert s1 is s2
                await registry.shutdown()

        asyncio.run(_run())

    def test_out_base_places_artifacts_on_configured_path(self, tmp_path):
        """Session out_dir must derive from the registry's configured out_base.

        Regression: out_base was hardcoded cwd-relative ('output/.preview'),
        which is read-only under a container's readOnlyRootFilesystem. It must
        be configurable so deploys can point it at the writable data volume.
        """
        script = tmp_path / "deck.js"
        script.write_text("// ok")
        out_base = tmp_path / "data" / ".preview"

        registry = SessionRegistry(allow_dirs=[str(tmp_path)], out_base=str(out_base))

        async def _run():
            async def _noop_start(self):
                pass
            with patch.object(PreviewSession, "start", _noop_start):
                session = await registry.create(str(script))
                assert session.out_dir == str(out_base / "deck")
                await registry.shutdown()

        asyncio.run(_run())

    def test_out_base_defaults_to_cwd_relative(self, tmp_path):
        """Unset out_base keeps the historical cwd-relative default."""
        script = tmp_path / "deck.js"
        script.write_text("// ok")
        registry = SessionRegistry(allow_dirs=[str(tmp_path)])

        async def _run():
            async def _noop_start(self):
                pass
            with patch.object(PreviewSession, "start", _noop_start):
                session = await registry.create(str(script))
                assert session.out_dir == str(Path("output/.preview") / "deck")
                await registry.shutdown()

        asyncio.run(_run())

    def test_create_out_base_arg_overrides_registry_default(self, tmp_path):
        """Per-call out_base still overrides the registry-configured base."""
        script = tmp_path / "deck.js"
        script.write_text("// ok")
        registry = SessionRegistry(allow_dirs=[str(tmp_path)], out_base=str(tmp_path / "reg"))

        async def _run():
            async def _noop_start(self):
                pass
            with patch.object(PreviewSession, "start", _noop_start):
                session = await registry.create(str(script), out_base=str(tmp_path / "override"))
                assert session.out_dir == str(tmp_path / "override" / "deck")
                await registry.shutdown()

        asyncio.run(_run())

    def test_get_returns_none_for_unknown_token(self, tmp_path):
        registry = SessionRegistry(allow_dirs=[str(tmp_path)])
        assert registry.get("nonexistent") is None

    def test_delete_is_idempotent(self, tmp_path):
        registry = SessionRegistry(allow_dirs=[str(tmp_path)])

        async def _run():
            await registry.delete("nonexistent")  # should not raise

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# render_complete pptx_url — must carry the BASE_PATH prefix
# ---------------------------------------------------------------------------

class TestPptxUrlPrefix:
    def _run_one_render(self, tmp_path):
        """Drive one render and return the broadcast render_complete payload."""
        script = tmp_path / "deck.js"
        script.write_text("// ok")

        renderer = MagicMock()
        renderer.render.return_value = RenderResult(
            success=True, pptx_path=str(tmp_path / "deck.pptx"), duration_ms=5
        )
        session = PreviewSession(
            script_path=str(script),
            token="tok123",
            out_dir=str(tmp_path / "out"),
            renderer=renderer,
            semaphore=asyncio.Semaphore(1),
        )

        captured = {}

        class _FakeWS:
            async def send_text(self, text):
                import json
                msg = json.loads(text)
                if msg.get("event") == "render_complete":
                    captured["payload"] = msg

        session.add_client(_FakeWS())
        asyncio.run(session._run_render(trigger="test"))
        return captured.get("payload")

    def test_pptx_url_prefixed_under_base_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASE_PATH", "/aippt/")
        payload = self._run_one_render(tmp_path)
        assert payload is not None
        assert payload["pptx_url"] == "/aippt/api/preview/sessions/tok123/pptx"

    def test_pptx_url_bare_at_apex(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BASE_PATH", raising=False)
        payload = self._run_one_render(tmp_path)
        assert payload is not None
        assert payload["pptx_url"] == "/api/preview/sessions/tok123/pptx"
