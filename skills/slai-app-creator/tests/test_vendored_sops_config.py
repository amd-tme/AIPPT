"""Vendored public SOPS config must match platform-repo creation_rules."""

from __future__ import annotations

from pathlib import Path

import yaml
import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_SOPS = REPO_ROOT / ".sops.yaml"
SKILL_SOPS = REPO_ROOT / "skills/slai-app-creator/assets/platform.sops.yaml"
ENCRYPT_SCRIPT = REPO_ROOT / "skills/slai-app-creator/scripts/encrypt-secrets-yaml.sh"


@pytest.mark.skipif(not REPO_SOPS.is_file(), reason="requires platform repository root SOPS config")
def test_vendored_sops_creation_rules_match_repo() -> None:
    repo = yaml.safe_load(REPO_SOPS.read_text(encoding="utf-8"))
    skill = yaml.safe_load(SKILL_SOPS.read_text(encoding="utf-8"))
    assert skill["creation_rules"] == repo["creation_rules"]
    recipient = skill["creation_rules"][0]["age"]
    assert recipient.startswith("age1")
    assert len(recipient) > 20


def test_encrypt_script_does_not_clone_platform_repo() -> None:
    text = ENCRYPT_SCRIPT.read_text(encoding="utf-8")
    assert "git clone" not in text
    assert "SLAI_PLATFORM_CLONE_DIR" not in text
    assert "platform.sops.yaml" in text
    assert "--config" in text
    assert "encrypt" in text
