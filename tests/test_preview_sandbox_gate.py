"""Version gate for the Node permission sandbox tests.

Independent of the runtime sandbox tests so it runs even when they are skipped.
Stable ``--permission`` requires Node 22.13+ LTS or >= 23.5.
"""
import subprocess

import pytest

from tests import test_preview_sandbox as sandbox

gate = sandbox._node_supports_permission


def _patch(monkeypatch, stdout="", returncode=0, which="/usr/bin/node", exc=None):
    monkeypatch.setattr(sandbox.shutil, "which", lambda _n: which)

    def run(*_a, **_k):
        if exc:
            raise exc
        return subprocess.CompletedProcess(["node"], returncode, stdout, "")

    monkeypatch.setattr(sandbox.subprocess, "run", run)


@pytest.mark.parametrize("v", ["v20.0.0", "v21.7.3", "v22.12.0", "v22.12.99", "v23.0.0", "v23.4.0", "v23.4.9"])
def test_old_node_rejected(monkeypatch, v):
    _patch(monkeypatch, v + "\n")
    assert gate() is False


@pytest.mark.parametrize("v", ["v22.13.0", "v22.13.1", "v22.99.0", "v23.5.0", "v23.10.1", "v24.0.0", "v26.13.0"])
def test_supported_node_accepted(monkeypatch, v):
    _patch(monkeypatch, v + "\n")
    assert gate() is True


def test_missing_node(monkeypatch):
    _patch(monkeypatch, which=None)
    assert gate() is False


@pytest.mark.parametrize("exc", [OSError("boom"), subprocess.TimeoutExpired("node", 10)])
def test_command_errors(monkeypatch, exc):
    _patch(monkeypatch, exc=exc)
    assert gate() is False


@pytest.mark.parametrize("out", ["", "\n", "garbage", "v24", "24.0.0"])
def test_malformed_output(monkeypatch, out):
    _patch(monkeypatch, out)
    assert gate() is False


def test_nonzero_returncode_rejected(monkeypatch):
    _patch(monkeypatch, "v26.13.0\n", returncode=1)
    assert gate() is False
