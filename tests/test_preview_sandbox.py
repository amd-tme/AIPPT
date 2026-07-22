"""Runtime sandbox tests for the preview Renderer (security boundary).

These assert the deterministic execution controls that make it safe to run
LLM-generated / user-authored scripts:

- the subprocess environment is scrubbed (no parent credentials leak);
- Node runs under the permission model: filesystem writes are confined to the
  output dir, and child-process spawning is denied.

Gated on a Node runtime that supports ``--permission`` (Node >= 20). Skipped
cleanly otherwise, mirroring other Node-dependent tests.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from aippt.preview import Renderer


def _node_supports_permission() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10)
    except Exception:
        return False
    m = re.match(r"v(\d+)\.", out.stdout.strip())
    return bool(m) and int(m.group(1)) >= 20


pytestmark = pytest.mark.skipif(
    not _node_supports_permission(),
    reason="node >= 20 (with --permission) not available",
)


@pytest.fixture
def renderer(tmp_path):
    # project_root has a node_modules? Not required for these minimal scripts,
    # which don't import the helper lib. Use the real repo root so NODE_PATH is
    # wired the same way production renders are.
    root = str(Path(__file__).resolve().parents[1])
    return Renderer(project_root=root)


def _write(tmp_path, name, code):
    p = tmp_path / f"{name}.mjs"
    p.write_text(code, encoding="utf-8")
    return str(p)


def test_env_is_scrubbed_of_credentials(renderer, tmp_path, monkeypatch):
    """A secret in the parent env must not be visible to the script."""
    monkeypatch.setenv("AMD_LLM_KEY", "SUPER_SECRET_TEST_VALUE")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ANOTHER_SECRET")
    out = tmp_path / "out"
    out.mkdir()
    # Build the exact command + env the Renderer would use and run directly so
    # we can capture stdout (render() only returns the pptx path).
    script = Path(_write(tmp_path, "env", "console.log('K=' + (process.env.AMD_LLM_KEY || 'NONE'));\n"))
    cmd = renderer._build_command(script, out)[0]
    env = renderer._child_env(out)
    assert "AMD_LLM_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    res = subprocess.run(cmd, cwd=renderer.project_root, env=env, capture_output=True, text=True)
    assert "K=NONE" in res.stdout, res.stdout


def test_allowed_env_passes_through(renderer, tmp_path):
    """Non-secret allow-listed vars (PATH) and the injected out dir survive."""
    out = tmp_path / "out"
    out.mkdir()
    env = renderer._child_env(out)
    assert env.get("PATH")
    assert env["AIPPT_PREVIEW_OUT"] == str(out)


def test_fs_write_outside_out_dir_is_denied(renderer, tmp_path):
    """Writing into the project root (not the out dir) must fail."""
    out = tmp_path / "out"
    out.mkdir()
    target = Path(renderer.project_root) / "SANDBOX_PWNED.txt"
    code = (
        "import { writeFileSync } from 'fs';\n"
        f"writeFileSync({str(target)!r}, 'x');\n"
    )
    script = _write(tmp_path, "escape", code)
    try:
        res = renderer.render(script, str(out))
        assert res.success is False
        assert not target.exists(), "script escaped the fs-write sandbox"
    finally:
        if target.exists():
            target.unlink()


def test_fs_write_inside_out_dir_is_allowed(renderer, tmp_path):
    """Writing within the out dir is permitted (the deck itself lands here)."""
    out = tmp_path / "out"
    out.mkdir()
    marker = out / "marker.txt"
    code = f"import {{ writeFileSync }} from 'fs';\nwriteFileSync({str(marker)!r}, 'ok');\n"
    script = _write(tmp_path, "writeok", code)
    # render() reports failure (no .pptx produced), but the write must succeed.
    renderer.render(script, str(out))
    assert marker.exists() and marker.read_text() == "ok"


def test_child_process_spawn_is_denied(renderer, tmp_path):
    """A script cannot spawn subprocesses (no --allow-child-process)."""
    out = tmp_path / "out"
    out.mkdir()
    code = "import { execSync } from 'child_process';\nexecSync('id');\n"
    script = _write(tmp_path, "spawn", code)
    res = renderer.render(script, str(out))
    assert res.success is False


def test_known_good_deck_still_renders(renderer, tmp_path):
    """Regression: a real helper-based example renders under the sandbox."""
    example = Path(renderer.project_root) / "examples" / "instinct-demo" / "instinct-demo.mjs"
    if not example.exists():
        pytest.skip("example deck not present")
    out = tmp_path / "out"
    out.mkdir()
    res = renderer.render(str(example), str(out))
    assert res.success is True, res.stderr_tail
    assert res.pptx_path and Path(res.pptx_path).exists()
