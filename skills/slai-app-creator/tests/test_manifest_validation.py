"""Focused tests for slai-app-creator deployment bundle validation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    asset_submission_bundle,
    requires_asset_submission,
    requires_platform_auth,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = REPO_ROOT / "skills/slai-app-creator/scripts/main.py"


def _container(name: str, image: str, extra: str = "") -> str:
    return f"""\
        - name: {name}
          image: {json.dumps(image)}
          securityContext:
            allowPrivilegeEscalation: false
            capabilities: {{drop: [ALL]}}
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 250m
              memory: 512Mi
{extra}"""


def _bundle(
    tmp_path: Path,
    *,
    images: tuple[str, ...] = ("mkmhub.amd.com/hw-slaiapp-dev/example:abc123",),
    pod_fields: str = "",
    container_extra: str = "",
    metadata_fields: str = "",
    app_id: str = "example",
    namespace: str = "test-ns",
) -> Path:
    bundle = tmp_path / "deploy" / namespace / app_id
    bundle.mkdir(parents=True)
    containers = "\n".join(
        _container(f"app-{index}", image, container_extra if index == 1 else "")
        for index, image in enumerate(images, start=1)
    )
    (bundle / "deployment.yaml").write_text(
        f"""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_id}
  namespace: {namespace}
{metadata_fields}spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: {app_id}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {app_id}
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        seccompProfile: {{type: RuntimeDefault}}
{pod_fields}      containers:
{containers}
""",
        encoding="utf-8",
    )
    (bundle / "service.yaml").write_text(f"apiVersion: v1\nkind: Service\nmetadata: {{name: {app_id}, namespace: {namespace}}}\nspec:\n  selector: {{app.kubernetes.io/name: {app_id}}}\n  ports: [{{name: http, port: 80, targetPort: http}}]\n", encoding="utf-8")
    (bundle / "secrets.enc.yaml").write_text(
        f"apiVersion: v1\nkind: Secret\nmetadata: {{name: {app_id}-secrets, namespace: {namespace}}}\ndata:\n  test: ENC[AES256_GCM,data:dGVzdA==,iv:dGVzdA==,tag:dGVzdA==,type:str]\nsops:\n  age:\n    - recipient: age1r5cjptkyd4wn82y5flfte4lm7y67nk2wxqhm7ncg5v23ea6seq9sfyjl0l\n      enc: encrypted\n  mac: ENC[AES256_GCM,data:dGVzdA==,iv:dGVzdA==,tag:dGVzdA==,type:str]\n  encrypted_regex: ^(data|stringData)$\n  version: 3.9.4\n  lastmodified: \"2026-10-03T00:00:00Z\"\n",
        encoding="utf-8",
    )
    return bundle


def _run(bundle: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(bundle)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _add_auth_policy(bundle: Path, **overrides: object) -> None:
    policy = {
        "$schema": "../../../config/schemas/platform-auth-policy.schema.json",
        "apiVersion": "slai.amd.com/v1alpha1",
        "enabled": True,
        "mode": "forward-auth",
        "host": "example.slai-app.amd.com",
        "owner": "example-team",
        "protectedIngress": "z-ingress.yaml",
        "ldapGroups": {"enabled": False},
        "logout": "app-session",
    }
    policy.update(overrides)
    (bundle / "auth-policy.json").write_text(
        json.dumps(policy, indent=2) + "\n",
        encoding="utf-8",
    )
    (bundle / "z-ingress.yaml").write_text(
        """\
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: example
  namespace: test-ns
spec:
  rules:
    - host: example.slai-app.amd.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: example
                port:
                  name: http
  tls:
    - hosts:
        - example.slai-app.amd.com
      secretName: slai-app-wildcard-tls
""",
        encoding="utf-8",
    )


@requires_platform_auth
@pytest.mark.platform_repo
def test_platform_sso_policy_delegates_to_canonical_validator(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _add_auth_policy(bundle)

    result = _run(bundle)

    assert result.returncode == 0, result.stderr
    assert "client_id=slai-test-ns-example" in result.stdout
    assert "does not provision the sidecar" in result.stdout


@requires_platform_auth
@pytest.mark.platform_repo
def test_platform_sso_policy_rejects_direct_okta_fields(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    _add_auth_policy(bundle, oktaIssuer="https://amdsso.okta.com")

    result = _run(bundle)

    assert result.returncode == 1
    assert "Additional properties are not allowed" in result.stderr
    assert "oktaIssuer" in result.stderr


@requires_platform_auth
@pytest.mark.platform_repo
def test_platform_sso_policy_rejects_manual_ingress_auth_annotations(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path)
    _add_auth_policy(bundle)
    ingress = bundle / "z-ingress.yaml"
    ingress.write_text(
        ingress.read_text(encoding="utf-8").replace(
            "  namespace: test-ns\n",
            "  namespace: test-ns\n  annotations:\n"
            "    nginx.ingress.kubernetes.io/auth-url: http://unmanaged\n",
        ),
        encoding="utf-8",
    )

    result = _run(bundle)

    assert result.returncode == 1
    assert "auth annotations are platform-managed" in result.stderr


def test_default_registry_without_pull_secret_is_backward_compatible(
    tmp_path: Path,
) -> None:
    result = _run(_bundle(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "imagePullSecrets" not in result.stdout


def test_alternate_registry_and_project_do_not_force_credentials(
    tmp_path: Path,
) -> None:
    bundle = _bundle(
        tmp_path,
        images=("harbor.team.example:8443/private-project/example:deadbeef",),
    )

    result = _run(bundle)

    assert result.returncode == 0, result.stderr


def test_valid_pod_image_pull_secret_emits_non_decrypting_reminder(
    tmp_path: Path,
) -> None:
    bundle = _bundle(
        tmp_path,
        images=("harbor.team.example/private-project/example:deadbeef",),
        pod_fields="      imagePullSecrets:\n        - name: example-harbor-pull\n",
    )

    result = _run(bundle)

    assert result.returncode == 0, result.stderr
    assert "does not decrypt secrets.enc.yaml" in result.stdout
    assert "kubernetes.io/dockerconfigjson" in result.stdout


@pytest.mark.parametrize(
    ("image", "message"),
    [
        ("https://harbor.example/team/app:abc123", "must not include a URL scheme"),
        ("robot@harbor.example/team/app:abc123", "must not contain userinfo"),
        ("harbor.example/team/../app:abc123", "traversal segments"),
        ("harbor.example/Team/app:abc123", "must be lowercase"),
        ("harbor.example/team/app:latest", "avoid :latest"),
        ("harbor.example/team/app", "explicit immutable tag or digest"),
        ("harbor.example/team/app :abc123", "embedded whitespace"),
        ("harbor.example/team:abc123", "registry hostname, Harbor project"),
    ],
)
def test_rejects_malformed_or_mutable_image_locations(
    tmp_path: Path, image: str, message: str
) -> None:
    result = _run(_bundle(tmp_path, images=(image,)))

    assert result.returncode == 1
    assert message in result.stderr


@pytest.mark.parametrize(
    ("pod_fields", "container_extra", "message"),
    [
        ("      imagePullSecrets: []\n", "", "must be a non-empty list"),
        (
            "      imagePullSecrets:\n        - secret: pull-secret\n",
            "",
            "mapping with only a name field",
        ),
        (
            "      imagePullSecrets:\n        - name: Invalid_Name\n",
            "",
            "valid DNS-1123 Secret name",
        ),
        (
            "",
            "          imagePullSecrets:\n            - name: pull-secret\n",
            "move it to spec.template.spec.imagePullSecrets",
        ),
    ],
)
def test_rejects_invalid_pull_secret_structure_or_placement(
    tmp_path: Path, pod_fields: str, container_extra: str, message: str
) -> None:
    result = _run(
        _bundle(tmp_path, pod_fields=pod_fields, container_extra=container_extra)
    )

    assert result.returncode == 1
    assert message in result.stderr


def test_validates_every_container_image(tmp_path: Path) -> None:
    bundle = _bundle(
        tmp_path,
        images=(
            "mkmhub.amd.com/hw-slaiapp-dev/api:abc123",
            "mkmhub.amd.com/hw-slaiapp-dev/worker:latest",
        ),
    )

    result = _run(bundle)

    assert result.returncode == 1
    assert "container 'app-2' image: avoid :latest" in result.stderr


def test_rejects_missing_app_name_pod_label(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    deployment = bundle / "deployment.yaml"
    deployment.write_text(
        deployment.read_text(encoding="utf-8").replace(
            "        app.kubernetes.io/name: example\n",
            "",
        ),
        encoding="utf-8",
    )

    result = _run(bundle)

    assert result.returncode == 1
    assert "app.kubernetes.io/name" in result.stderr
    assert "example-auth-proxy" in result.stderr


def test_rejects_pod_label_that_does_not_match_app_id(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    deployment = bundle / "deployment.yaml"
    deployment.write_text(
        deployment.read_text(encoding="utf-8").replace(
            "app.kubernetes.io/name: example",
            "app.kubernetes.io/name: example-gateway",
        ),
        encoding="utf-8",
    )

    result = _run(bundle)

    assert result.returncode == 1
    assert "example-gateway" in result.stderr
    assert "bundle directory name 'example'" in result.stderr


def test_allows_deployment_object_name_to_differ_from_app_id(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    deployment = bundle / "deployment.yaml"
    deployment.write_text(
        deployment.read_text(encoding="utf-8").replace(
            "  name: example\n",
            "  name: example-gateway\n",
            1,
        ),
        encoding="utf-8",
    )

    result = _run(bundle)

    assert result.returncode == 0, result.stderr


@requires_asset_submission
@pytest.mark.platform_repo
def test_legacy_asset_submission_requires_canonical_republish() -> None:
    bundle = asset_submission_bundle()

    result = _run(bundle)

    assert result.returncode != 0
    assert 'every document must be a Kubernetes Secret' in result.stderr
    assert 'ingress rules require explicit peers and ports' in result.stderr


SHARED_LDAP_ENV = """\
          env:
            - name: LDAP_BIND_UPN
              valueFrom:
                secretKeyRef:
                  name: slai-shared-ldap-bind
                  key: LDAP_BIND_UPN
            - name: LDAP_BIND_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: slai-shared-ldap-bind
                  key: LDAP_BIND_PASSWORD
"""


def test_rejects_direct_shared_ldap_wiring(tmp_path: Path) -> None:
    bundle = _bundle(
        tmp_path,
        metadata_fields='  labels:\n    slai.amd.com/shared-ldap-consumer: "true"\n',
        container_extra=SHARED_LDAP_ENV,
    )

    result = _run(bundle)

    assert result.returncode == 1
    assert "must not reference deprecated slai-shared-ldap-bind" in result.stderr


def test_rejects_formerly_allowlisted_ldap_app_shared_ldap_wiring(tmp_path: Path) -> None:
    bundle = _bundle(
        tmp_path,
        app_id="ldap-app",
        metadata_fields='  labels:\n    slai.amd.com/shared-ldap-consumer: "true"\n',
        container_extra=SHARED_LDAP_ENV,
    )

    result = _run(bundle)

    assert result.returncode == 1
    assert "deprecated slai-shared-ldap-bind" in result.stderr


def test_formerly_allowlisted_ldap_app_rejects_credentials_without_label(tmp_path: Path) -> None:
    bundle = _bundle(
        tmp_path,
        app_id="ldap-app",
        container_extra=SHARED_LDAP_ENV,
    )

    result = _run(bundle)

    assert result.returncode == 1
    assert "deprecated slai-shared-ldap-bind" in result.stderr


def test_shared_ldap_is_rejected_without_legacy_label(tmp_path: Path) -> None:
    result = _run(_bundle(tmp_path, container_extra=SHARED_LDAP_ENV))

    assert result.returncode == 1
    assert "must not reference deprecated slai-shared-ldap-bind" in result.stderr


def test_shared_ldap_is_rejected_even_with_one_explicit_key(tmp_path: Path) -> None:
    only_upn = """\
          env:
            - name: LDAP_BIND_UPN
              valueFrom:
                secretKeyRef:
                  name: slai-shared-ldap-bind
                  key: LDAP_BIND_UPN
"""
    bundle = _bundle(
        tmp_path,
        metadata_fields='  labels:\n    slai.amd.com/shared-ldap-consumer: "true"\n',
        container_extra=only_upn,
    )

    result = _run(bundle)

    assert result.returncode == 1
    assert "must not reference deprecated slai-shared-ldap-bind" in result.stderr


def test_rejects_literal_ldap_credentials(tmp_path: Path) -> None:
    literal_password = """\
          env:
            - name: LDAP_BIND_PASSWORD
              value: do-not-commit
"""

    result = _run(_bundle(tmp_path, container_extra=literal_password))

    assert result.returncode == 1
    assert "must not set LDAP_BIND_PASSWORD as a literal value" in result.stderr


def test_rejects_shared_ldap_env_from(tmp_path: Path) -> None:
    env_from = """\
          envFrom:
            - secretRef:
                name: slai-shared-ldap-bind
"""
    bundle = _bundle(
        tmp_path,
        metadata_fields='  labels:\n    slai.amd.com/shared-ldap-consumer: "true"\n',
        container_extra=env_from,
    )

    result = _run(bundle)

    assert result.returncode == 1
    assert "must not reference deprecated slai-shared-ldap-bind" in result.stderr


def test_deployment_template_uses_requests_without_cpu_memory_limits() -> None:
    import yaml
    template = Path(__file__).parents[1] / 'assets/templates/deployment.yaml.example'
    deployment = yaml.safe_load(template.read_text())
    containers = deployment['spec']['template']['spec']['containers']
    for container in containers:
        resources = container['resources']
        assert resources['requests']['cpu'] == '100m'
        assert resources['requests']['memory'] == '256Mi'
        assert 'cpu' not in resources.get('limits', {})
        assert 'memory' not in resources.get('limits', {})


@pytest.mark.parametrize("source", [
    "secret:\n              secretName: slai-shared-ldap-bind",
    "projected:\n              sources:\n                - secret:\n                    name: slai-shared-ldap-bind",
])
def test_rejects_deprecated_ldap_secret_volumes(tmp_path: Path, source: str) -> None:
    result = _run(_bundle(tmp_path, pod_fields="      volumes:\n        - name: ldap\n          " + source + "\n"))
    assert result.returncode == 1
    assert "deprecated slai-shared-ldap-bind" in result.stderr


def test_accepts_anonymous_ldap_configuration(tmp_path: Path) -> None:
    result = _run(_bundle(tmp_path, container_extra="""          env:
            - name: LDAP_URL
              value: ldaps://ldap.amd.com:636
            - name: LDAP_BASE_DN
              value: dc=amdldap,dc=com
            - name: LDAP_PEOPLE_BASE_DN
              value: ou=People,dc=amdldap,dc=com
            - name: LDAP_POSIX_GROUPS_BASE_DN
              value: ou=UnixGroups,ou=Groups,dc=amdldap,dc=com
"""))
    assert result.returncode == 0, result.stderr


def test_malformed_yaml_diagnostic_omits_source_secret(tmp_path):
    import main

    import secrets

    canary = "synthetic-" + secrets.token_hex(16)
    malformed = "apiVersion: apps/v1\nkind: Deployment\npassword: [" + canary + "\n"
    errors, images = main._deployment_reference_errors(malformed, tmp_path / "deployment.yaml")
    assert images == []
    diagnostic = " ".join(errors)
    assert "invalid YAML" in diagnostic
    assert "line" in diagnostic and "column" in diagnostic
    assert canary not in diagnostic
    assert "password" not in diagnostic


@pytest.mark.parametrize(
    "image, rejected",
    [
        ("mkmhub.amd.com/hw-slaiapp-dev/setup:latest", True),
        ("mkmhub.amd.com/hw-slaiapp-dev/setup:abc123", False),
        ("mkmhub.amd.com/hw-slaiapp-dev/setup@sha256:" + "a" * 64, False),
    ],
)
def test_init_container_image_uses_regular_container_rules(tmp_path, image, rejected):
    import main

    bundle = _bundle(tmp_path, pod_fields=(
        "      initContainers:\n"
        "        - name: setup\n"
        "          image: " + json.dumps(image) + "\n"
        "          securityContext:\n"
        "            allowPrivilegeEscalation: false\n"
        "            capabilities: {drop: [ALL]}\n"
    ))
    deployment = bundle / "deployment.yaml"
    errors, _ = main._deployment_reference_errors(deployment.read_text(), deployment)
    assert bool(errors) is rejected
    if rejected:
        assert "init container 'setup' image: avoid :latest" in " ".join(errors)
        assert "initContainers[0]" in " ".join(errors)


def test_init_container_without_image_is_rejected(tmp_path):
    import main

    bundle = _bundle(tmp_path, pod_fields="      initContainers:\n        - name: setup\n")
    deployment = bundle / "deployment.yaml"
    errors, _ = main._deployment_reference_errors(deployment.read_text(), deployment)
    assert any("init container 'setup' image:" in error for error in errors)


@pytest.mark.parametrize("image, rejected", [
    ("mkmhub.amd.com/hw-slaiapp-dev/example:abc123", True),
    ("mkmhub.amd.com/hw-slaiapp-dev/example@sha256:" + "a" * 64, False),
    ("mkmhub.amd.com/hw-slaiapp-dev/example:abc123@sha256:" + "a" * 64, True),
    ("mkmhub.amd.com/hw-slaiapp-dev/example@sha256:" + "a" * 32, True),
])
def test_production_images_require_exact_sha256_reference(tmp_path, image, rejected):
    import main

    bundle = _bundle(tmp_path, namespace="slai-app-prod", images=(image,))
    deployment = bundle / "deployment.yaml"
    errors, _ = main._deployment_reference_errors(deployment.read_text(), deployment)
    assert bool(errors) is rejected
    if rejected:
        assert "repository@sha256" in " ".join(errors)


def test_production_init_image_requires_digest(tmp_path):
    import main

    bundle = _bundle(tmp_path, namespace="slai-app-prod",
                     images=("mkmhub.amd.com/hw-slaiapp-dev/example@sha256:" + "a" * 64,),
                     pod_fields="      initContainers:\n        - name: setup\n          image: mkmhub.amd.com/hw-slaiapp-dev/setup:abc123\n")
    deployment = bundle / "deployment.yaml"
    errors, _ = main._deployment_reference_errors(deployment.read_text(), deployment)
    assert any("init container" in error and "repository@sha256" in error for error in errors)


@pytest.mark.parametrize('repository', [
    'docker.io/library/example',
    'mkmhub.amd.com/other-project/example',
    'mkmhub.amd.com.evil.example/hw-slaiapp-dev/example',
    'mkmhub.amd.com:443/hw-slaiapp-dev/example',
    'mkmhub.amd.com/hw-slaiapp-dev-evil/example',
    'mkmhub.amd.com/hw-slaiapp-dev/example',
])
@pytest.mark.parametrize('group', ['containers', 'initContainers'])
def test_canonical_only_production_requires_approved_harbor(tmp_path, repository, group, monkeypatch):
    import main
    monkeypatch.delenv('SLAI_BASELINE_APPROVED_IMAGES', raising=False)
    image = repository + '@sha256:' + 'a' * 64
    bundle = _bundle(tmp_path, namespace='slai-app-prod',
                     images=(image if group == 'containers' else 'mkmhub.amd.com/hw-slaiapp-dev/example@sha256:' + 'b' * 64,))
    path = bundle / 'deployment.yaml'
    document = main._yaml.safe_load(path.read_text())
    if group == 'initContainers':
        import copy
        container = copy.deepcopy(document['spec']['template']['spec']['containers'][0])
        container.update(name='setup', image=image)
        document['spec']['template']['spec']['initContainers'] = [container]
    text = main._yaml.safe_dump(document)
    path.write_text(text)
    errors, _ = main._deployment_reference_errors(text, path)
    registry_errors = [e for e in errors if 'production image must be under' in e]
    assert bool(registry_errors) == (repository != 'mkmhub.amd.com/hw-slaiapp-dev/example')
    if registry_errors:
        assert group + '[0]' in registry_errors[0]


def test_canonical_production_preserves_only_exact_hosted_approved_pin(tmp_path, monkeypatch):
    import main
    image = 'docker.io/library/example@sha256:' + 'a' * 64
    bundle = _bundle(tmp_path, namespace='slai-app-prod', images=(image,))
    path = bundle / 'deployment.yaml'
    monkeypatch.setenv('SLAI_BASELINE_APPROVED_IMAGES', json.dumps([image]))
    errors, _ = main._deployment_reference_errors(path.read_text(), path)
    assert not errors
    changed = path.read_text().replace('a' * 64, 'b' * 64)
    errors, _ = main._deployment_reference_errors(changed, path)
    assert any('production image must be under' in e for e in errors)


def test_declared_release_is_not_registry_authority(tmp_path, monkeypatch):
    import main
    monkeypatch.delenv('SLAI_BASELINE_APPROVED_IMAGES', raising=False)
    image = 'docker.io/library/example@sha256:' + 'a' * 64
    bundle = _bundle(tmp_path, namespace='slai-app-prod', images=(image,))
    (bundle / 'image-release.json').write_text(json.dumps({'repository': 'docker.io/library/example', 'digest': 'sha256:' + 'a' * 64}))
    path = bundle / 'deployment.yaml'
    errors, _ = main._deployment_reference_errors(path.read_text(), path)
    assert any('production image must be under' in e for e in errors)


@requires_platform_auth
def test_forward_auth_loopback_port_does_not_require_ingress(tmp_path):
    import importlib.util
    import json
    import yaml
    script = Path(__file__).resolve().parents[1] / 'scripts/main.py'
    spec = importlib.util.spec_from_file_location('loopback_validator', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = tmp_path / 'slai-app-prod' / 'charter'
    app.mkdir(parents=True)
    source = Path(__file__).resolve().parents[3] / 'deploy/slai-app-prod/charter'
    deployment = yaml.safe_load((source / 'deployment.yaml').read_text())
    policy = yaml.safe_load((source / 'networkpolicy.yaml').read_text())
    controller = {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}}, 'podSelector': {'matchLabels': {'app.kubernetes.io/component': 'controller', 'app.kubernetes.io/instance': 'rke2-ingress-nginx', 'app.kubernetes.io/name': 'rke2-ingress-nginx'}}}
    policy['spec']['ingress'] = [{'from': [controller], 'ports': [{'protocol': 'TCP', 'port': 8081}]}]
    policy['spec']['egress'] = [{'to': [{'ipBlock': {'cidr': '10.180.95.212/32'}}], 'ports': [{'protocol': 'TCP', 'port': 443}]}]
    (app / 'auth-policy.json').write_text(json.dumps({'enabled': True, 'mode': 'forward-auth'}))
    check = lambda: module._networkpolicy_errors(yaml.safe_dump(policy), yaml.safe_dump(deployment), app / 'networkpolicy.yaml')
    assert not check()
    deployment['spec']['template']['spec']['containers'][0]['env'] = [{'name': 'CHARTER_APP_BIND', 'value': '0.0.0.0'}]
    assert any('8080' in error for error in check())
    deployment['spec']['template']['spec']['containers'][0]['env'] = [{'name': 'CHARTER_APP_BIND', 'value': '127.0.0.1'}]
    policy['spec']['ingress'][0]['ports'][0]['port'] = 8080
    assert any('8081' in error for error in check())
    (app / 'auth-policy.json').unlink()
    assert any('8081' in error for error in check())


@requires_platform_auth
def test_otlp_egress_matches_declared_endpoint_port(tmp_path):
    import importlib.util
    import json
    import yaml
    script = Path(__file__).resolve().parents[1] / 'scripts/main.py'
    spec = importlib.util.spec_from_file_location('otlp_port_validator', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = tmp_path / 'slai-app-prod' / 'charter'
    app.mkdir(parents=True)
    source = Path(__file__).resolve().parents[3] / 'deploy/slai-app-prod/charter'
    deployment = yaml.safe_load((source / 'deployment.yaml').read_text())
    policy = yaml.safe_load((source / 'networkpolicy.yaml').read_text())
    controller = {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}}, 'podSelector': {'matchLabels': {'app.kubernetes.io/component': 'controller', 'app.kubernetes.io/instance': 'rke2-ingress-nginx', 'app.kubernetes.io/name': 'rke2-ingress-nginx'}}}
    policy['spec']['ingress'] = [{'from': [controller], 'ports': [{'protocol': 'TCP', 'port': 8081}]}]
    policy['spec']['egress'] = [{'to': [{'ipBlock': {'cidr': '10.180.93.117/32'}}], 'ports': [{'protocol': 'TCP', 'port': 443}]}]
    (app / 'auth-policy.json').write_text(json.dumps({'enabled': True, 'mode': 'forward-auth'}))
    env = deployment['spec']['template']['spec']['containers'][0]['env']
    endpoint = next(item for item in env if item['name'] == 'OTEL_EXPORTER_OTLP_ENDPOINT')
    check = lambda: module._networkpolicy_errors(yaml.safe_dump(policy), yaml.safe_dump(deployment), app / 'networkpolicy.yaml')
    endpoint['value'] = 'https://collector.example'
    assert not check()
    endpoint['value'] = 'http://collector.example:4317'
    assert check()
    policy['spec']['egress'][0]['ports'][0]['port'] = 4317
    assert not check()
    endpoint['value'] = 'https://collector.example:8443'
    assert check()
