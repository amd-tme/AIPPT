"""Regression tests for broker-first SSO onboarding guidance."""

from __future__ import annotations

import json
import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

from conftest import requires_platform_auth


SKILL_ROOT = Path(__file__).resolve().parents[1]


def test_auth_policy_template_has_no_caller_controlled_oauth_or_image_fields() -> None:
    template = json.loads(
        (SKILL_ROOT / "assets/templates/auth-policy.json.example").read_text(
            encoding="utf-8"
        )
    )

    assert template["mode"] == "forward-auth"
    assert template["ldapGroups"] == {"enabled": False}
    forbidden = {
        "issuer",
        "oktaOrg",
        "oktaIssuer",
        "clientId",
        "clientSecret",
        "callback",
        "redirectUris",
        "audience",
        "image",
        "sidecarImage",
    }
    assert forbidden.isdisjoint(template)


def test_cli_auth_policy_template_is_minimal_explicit_opt_in() -> None:
    template = (
        SKILL_ROOT / "assets/templates/cli-auth-policy.yaml.example"
    ).read_text(encoding="utf-8")
    assert template == (
        "apiVersion: slai.amd.com/v1alpha1\n"
        "kind: PlatformCliAuthPolicy\n"
        "enabled: true\n"
    )
    for forbidden in ("clientId", "audience", "redirect", "secret", "scope", "offline_access"):
        assert forbidden not in template


@requires_platform_auth
@pytest.mark.platform_repo
def test_auth_policy_template_passes_skill_and_canonical_validation(
    tmp_path: Path,
) -> None:
    from test_manifest_validation import _add_auth_policy, _bundle, _run

    bundle = _bundle(tmp_path)
    _add_auth_policy(bundle)
    rendered = (
        SKILL_ROOT / "assets/templates/auth-policy.json.example"
    ).read_text(encoding="utf-8")
    rendered = rendered.replace("YOUR_APP_ID", "example").replace(
        "YOUR_OWNER", "example-team"
    )
    (bundle / "auth-policy.json").write_text(rendered, encoding="utf-8")

    result = _run(bundle)

    assert result.returncode == 0, result.stderr
    assert "client_id=slai-test-ns-example" in result.stdout


def test_standard_guidance_forbids_per_app_okta_registration() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL_ROOT / "references/okta-oauth-web.md").read_text(
        encoding="utf-8"
    )
    normalized_reference = " ".join(reference.split())

    assert "register a per-app Okta application" in skill
    assert "one platform-owned AMD Okta registration" in normalized_reference
    assert "An `auth-policy.json` file alone has no runtime effect" in normalized_reference
    assert "com.amd.slai.auth-proxy.contract=v1" in normalized_reference
    assert "all-zero" in normalized_reference
    assert "do not fall back to a new per-app Okta registration" in normalized_reference


def test_guidance_executes_platform_enrollment_until_ready() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL_ROOT / "references/okta-oauth-web.md").read_text(
        encoding="utf-8"
    )

    version = re.search(
        r'metadata:\n(?:.*\n)*?  version: ["\']?(\d+)\.(\d+)\.(\d+)["\']?$',
        skill,
        re.M,
    )
    assert version is not None
    assert tuple(map(int, version.groups())) >= (0, 0, 63)
    assert 'requires SSO enrollment `Ready`' in skill
    assert 'scripts/reconcile-platform-sso-enrollment.py' in reference
    assert '.github/workflows/platform-sso-enrollment.yml' in reference
    assert 'independent platform-maintainer approval' in reference
    assert 'submission ID' in skill
    assert 'CLI and device refresh tokens' in reference
    assert 'Do **not** request `offline_access`' in reference
    assert 'refresh grant MUST omit `scope`' in reference


def test_app_templates_do_not_wire_direct_okta_credentials() -> None:
    deployment = (
        SKILL_ROOT / "assets/templates/deployment.yaml.example"
    ).read_text(encoding="utf-8")
    assert "your-app-okta-credentials" not in deployment
    assert "SLAI_OAUTH_REDIRECT_URI" not in deployment
    assert not (SKILL_ROOT / "assets/templates/okta-registration.yaml.example").exists()


def test_ldap_guidance_distinguishes_anonymous_posix_from_ad_resolver() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL_ROOT / "references/shared-ldap.md").read_text(
        encoding="utf-8"
    )
    deployment = (
        SKILL_ROOT / "assets/templates/deployment.yaml.example"
    ).read_text(encoding="utf-8")
    egress = (SKILL_ROOT / "references/network-egress.md").read_text(
        encoding="utf-8"
    )

    for content in (reference, deployment):
        assert "ldaps://ldap.amd.com:636" in content
        assert "dc=amdldap,dc=com" in content
        assert "ou=People" in content
        assert "ou=UnixGroups,ou=Groups" in content

    assert "POSIX-group" in reference
    assert "`is-member`" in reference
    assert "Bind DN / password | Unset; anonymous bind" in reference
    assert "complete direct-and-transitive Active Directory" in reference
    assert "`ldapGroups.enabled` false" in reference
    assert "reference `slai-shared-ldap-bind`" in reference
    assert "membership uses the platform resolver" in skill
    assert "never mount" in skill
    assert "TCP **636**" in egress
    assert "Kubernetes NetworkPolicy" in egress


def test_retired_deploy_workflows_require_hosted_creator() -> None:
    for name in ('deploy-app-platform-reusable.yml.example', 'deploy-development.yml.example', 'deploy-production.yml.example'):
        workflow = (SKILL_ROOT / 'assets/templates' / name).read_text()
        assert 'slai-app-creator' in workflow
        assert 'exit 1' in workflow
        assert 'self-hosted, linux, x64' in workflow
        assert 'docker build' not in workflow
        assert 'PLATFORM_PR_TOKEN' not in workflow