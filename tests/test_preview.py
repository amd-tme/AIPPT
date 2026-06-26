"""Tests for aippt.preview — Renderer, discover_local_imports, SessionRegistry."""
import asyncio
import os
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aippt.preview import (
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

        start = time.monotonic() - 1
        found = Renderer._find_pptx(tmp_path / "script.js", tmp_path, start)
        assert found is not None
        assert found.name == "new.pptx"

    def test_render_soffice_failure(self, tmp_path):
        r = Renderer()
        script = tmp_path / "deck.js"
        script.write_text("// ok")
        out = tmp_path / "out"
        out.mkdir()
        pptx = out / "deck.pptx"
        pptx.write_bytes(b"PK")

        ok = MagicMock(returncode=0, stderr="", stdout="")
        fail = MagicMock(returncode=1, stderr="soffice crashed", stdout="")

        call_count = [0]

        def fake_run(cmd, **kwargs):
            call_count[0] += 1
            return ok if call_count[0] == 1 else fail

        with patch.object(r, "_run", side_effect=fake_run):
            result = r.render(str(script), str(out))

        assert not result.success
        assert result.stage == "soffice"


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
            asyncio.get_event_loop().run_until_complete(registry.create(str(script)))

    def test_rejects_missing_script(self, tmp_path):
        registry = SessionRegistry(allow_dirs=[str(tmp_path)])

        with pytest.raises(FileNotFoundError):
            asyncio.get_event_loop().run_until_complete(
                registry.create(str(tmp_path / "missing.js"))
            )

    def test_returns_existing_session_for_same_script(self, tmp_path):
        script = tmp_path / "deck.js"
        script.write_text("// ok")

        registry = SessionRegistry(allow_dirs=[str(tmp_path)])

        async def _run():
            with patch("aippt.preview.PreviewSession.start", new_callable=lambda: lambda self: asyncio.coroutine(lambda: None)()):
                pass
            # Patch start to be a no-op
            with patch.object(registry, "create", wraps=registry.create):
                s1 = await registry.create(str(script))
                s2 = await registry.create(str(script))
                assert s1 is s2
                await registry.shutdown()

        asyncio.get_event_loop().run_until_complete(_run())

    def test_get_returns_none_for_unknown_token(self, tmp_path):
        registry = SessionRegistry(allow_dirs=[str(tmp_path)])
        assert registry.get("nonexistent") is None

    def test_delete_is_idempotent(self, tmp_path):
        registry = SessionRegistry(allow_dirs=[str(tmp_path)])

        async def _run():
            await registry.delete("nonexistent")  # should not raise

        asyncio.get_event_loop().run_until_complete(_run())
