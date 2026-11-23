"""Shared pytest helpers. Platform-repo files are never vendored into the plugin."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from main import platform_repo_root  # noqa: E402


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "platform_repo: requires a slai-app-platform checkout (nested or SLAI_PLATFORM_CLONE_DIR)",
    )


def platform_auth_available() -> bool:
    try:
        root = platform_repo_root()
    except (ValueError, OSError):
        return False
    return (root / "scripts" / "validate-platform-auth-policy.py").is_file() and (
        root / "config" / "schemas" / "platform-auth-policy.schema.json"
    ).is_file()


def platform_publish_script() -> Path:
    return platform_repo_root() / "scripts" / "publish-image-harbor.sh"


def asset_submission_bundle() -> Path:
    return platform_repo_root() / "deploy" / "slai-app-prod" / "slai-asset-submission"


requires_platform_auth = pytest.mark.skipif(
    not platform_auth_available(),
    reason="requires slai-app-platform SSO validator and schema",
)
requires_platform_publisher = pytest.mark.skipif(
    not platform_auth_available() or not platform_publish_script().is_file(),
    reason="requires slai-app-platform scripts/publish-image-harbor.sh",
)
requires_asset_submission = pytest.mark.skipif(
    not platform_auth_available() or not asset_submission_bundle().is_dir(),
    reason="requires slai-app-platform deploy/slai-app-prod/slai-asset-submission",
)
