"""Security regression tests for Harbor override credential binding."""

from __future__ import annotations

import json
import hashlib
import io
import os
import re
import subprocess
import tarfile
from pathlib import Path
from typing import Callable

import pytest
import yaml


from conftest import platform_publish_script, requires_platform_publisher

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_TEMPLATES = (
    REPO_ROOT
    / "skills/slai-app-creator/assets/templates/deploy-app-platform-reusable.yml.example",
)
PUBLISH_TEMPLATE = (
    REPO_ROOT
    / "skills/slai-app-creator/assets/templates/publish-image-harbor.sh.example"
)
STANDARD_SECRET_TEMPLATE = (
    REPO_ROOT / "skills/slai-app-creator/assets/templates/secrets.raw.yaml.example"
)
EXCEPTION_PULL_SECRET_TEMPLATE = (
    REPO_ROOT
    / "skills/slai-app-creator/assets/templates/harbor-pull-secret.raw.yaml.example"
)
PROBE_SMOKE = REPO_ROOT / "skills/slai-app-creator/scripts/probe-smoke.sh"
AUTHORIZE_EXISTING_TEMPLATE = (
    REPO_ROOT
    / "skills/slai-app-creator/assets/templates/authorize-existing-image.yml.example"
)


def _podman_publish_env(
    tmp_path: Path,
    temp_parent: str,
    runroot_parent: str | None = "/tmp",
) -> tuple[dict[str, str], Path]:
    build_context = tmp_path / "app"
    build_context.mkdir(exist_ok=True)
    (build_context / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    log = tmp_path / "podman.log"
    podman = tmp_path / "podman"
    podman.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
root=""
runroot=""
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[$i]}" in
    --root) root="${args[$((i + 1))]}" ;;
    --runroot) runroot="${args[$((i + 1))]}" ;;
  esac
done
touch -- "$REGISTRY_AUTH_FILE"
{
  printf 'COMMAND='
  printf '%q ' "$@"
  printf '\n'
  printf 'ROOT=%s\n' "$root"
  printf 'RUNROOT=%s\n' "$runroot"
  printf 'AUTH=%s\n' "$REGISTRY_AUTH_FILE"
  printf 'BASE_MODE=%s\n' "$(stat -c %a -- "$(dirname -- "$REGISTRY_AUTH_FILE")")"
  printf 'AUTH_MODE=%s\n' "$(stat -c %a -- "$REGISTRY_AUTH_FILE")"
} >> "$PODMAN_TEST_LOG"
cat >/dev/null || true
case " $* " in
  *" image inspect "*)
    if [[ -n "${PODMAN_TEST_REPODIGESTS:-}" ]]; then
      printf '%s\\n' "$PODMAN_TEST_REPODIGESTS"
    else
      printf '["%s@sha256:%s"]\\n' "$HARBOR_REGISTRY/$HARBOR_PROJECT/$IMAGE_NAME" aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    fi
    ;;
esac
""",
        encoding="utf-8",
    )
    podman.chmod(0o700)
    mock_dir = tmp_path / "registry-mock"
    mock_dir.mkdir(exist_ok=True)
    (mock_dir / "sitecustomize.py").write_text(r"""
import hashlib, http.client, json, os
BODY = b'{"schemaVersion":2,"layers":[]}'
DIGEST = 'sha256:' + hashlib.sha256(BODY).hexdigest()
class Response:
    def __init__(self, path):
        self.path = path
        self.status = 200
        self.body = BODY
        self.headers = [('Docker-Content-Digest', DIGEST)]
        mode = os.environ.get('HARBOR_TEST_MODE', '')
        if mode == 'tag-mismatch' and '/manifests/sha256:' not in path:
            self.headers = [('Docker-Content-Digest', 'sha256:' + 'a'*64)]
        elif mode == 'digest-mismatch' and '/manifests/sha256:' in path:
            self.body = b'wrong bytes'
        elif mode == 'notfound' and '/manifests/sha256:' in path:
            self.status = 404
        elif mode == 'error':
            self.status = 500
        elif mode == 'oversized':
            self.headers.append(('Content-Length', '1048577'))
        elif mode == 'oversized-body':
            self.body = b'x' * 1048577
        elif mode == 'redirect':
            self.status = 302
            self.headers = [('Location', 'https://evil.example/')]
        elif mode.startswith('challenge') and '/service/token' not in path and not os.environ.get('HARBOR_TEST_TOKEN_USED'):
            self.status = 401
            realm = 'https://mkmhub.amd.com/service/token'
            if mode == 'challenge-evil':
                realm = 'https://evil.example/service/token'
            self.headers = [('WWW-Authenticate', 'Bearer realm="' + realm + '",service="harbor-registry",scope="repository:hw-slaiapp-dev/example-app:pull"')]
        elif '/service/token' in path:
            self.body = b'{"token":"safe-token"}'
    def getheaders(self): return self.headers
    def read(self, limit): return self.body[:limit]
class Connection:
    def __init__(self, host, port, **kwargs):
        assert host == 'mkmhub.amd.com' and port == 443
    def request(self, method, path, headers):
        self.path = path
        with open(os.environ['HARBOR_TEST_REQUEST_LOG'], 'a') as f:
            f.write(path + '\n')
        if headers['Authorization'] == 'Bearer safe-token':
            os.environ['HARBOR_TEST_TOKEN_USED'] = '1'
    def getresponse(self): return Response(self.path)
    def close(self): pass
http.client.HTTPSConnection = Connection
""")
    env = os.environ.copy()
    env.update(
        {
            "SKIP_DOTENV": "1",
            "FORCE_PODMAN": "1",
            "PODMAN": str(podman),
            "PODMAN_TEST_LOG": str(log),
            "PODMAN_TEMP_PARENT": temp_parent,
            "HARBOR_REGISTRY": "mkmhub.amd.com",
            "HARBOR_PROJECT": "hw-slaiapp-dev",
            "IMAGE_NAME": "example-app",
            "BUILD_CONTEXT": str(build_context),
            "HARBOR_USERNAME": "fake-robot",
            "HARBOR_PASSWORD": "fake-secret",
            "HARBOR_CREDENTIAL_LOCATION": "mkmhub.amd.com/hw-slaiapp-dev",
            "HARBOR_LAST_IMAGE_FILE": str(tmp_path / "last-image.env"),
        }
    )
    env["PYTHONPATH"] = str(mock_dir)
    env["HARBOR_TEST_REQUEST_LOG"] = str(tmp_path / "registry-requests")
    env["IMAGE_TAG"] = "slai-sc-" + "a" * 40 + "-1-1"
    if runroot_parent is None:
        env.pop("PODMAN_RUNROOT_PARENT", None)
    else:
        env["PODMAN_RUNROOT_PARENT"] = runroot_parent
    return env, log


def _image_build_lsf_job(tmp_path: Path, job_id: str = "12345") -> Path:
    job = tmp_path / ".oci-build" / "jobs" / "job.abcdefgh"
    output = job / "output"
    output.mkdir(parents=True)
    job.chmod(0o700)
    output.chmod(0o700)
    manifest = (
        b'{"schemaVersion":2,"config":{"digest":"sha256:'
        + b"b" * 64
        + b'"},"layers":[]}'
    )
    manifest_digest = "sha256:" + hashlib.sha256(manifest).hexdigest()
    index = json.dumps(
        {
            "schemaVersion": 2,
            "manifests": [
                {
                    "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "digest": manifest_digest,
                    "size": len(manifest),
                }
            ],
        },
        separators=(",", ":"),
    ).encode()
    archive = output / "result.oci.tar"
    with tarfile.open(archive, "w") as bundle:
        for name, data in (
            ("oci-layout", b'{"imageLayoutVersion":"1.0.0"}'),
            ("index.json", index),
            ("blobs/sha256/" + manifest_digest.split(":", 1)[1], manifest),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            bundle.addfile(info, io.BytesIO(data))
    archive.chmod(0o600)
    artifact_digest = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
    evidence = {
        "schema_version": 1,
        "lsf_job_id": job_id,
        "profile": "slai-web-app-v1",
        "build_context": ".",
        "dockerfile": "Dockerfile",
        "build_network": "host",
        "storage_driver": "overlay",
        "source_digest": "sha256:" + "c" * 64,
        "artifact_digest": artifact_digest,
        "manifest_digest": manifest_digest,
        "platform": "linux/amd64",
        "artifact_bytes": archive.stat().st_size,
        "probe_status": 200,
    }
    success = output / "success.json"
    success.write_text(json.dumps(evidence) + "\n", encoding="utf-8")
    success.chmod(0o600)
    return job


def _run_podman_publish(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(PUBLISH_TEMPLATE)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_verified_image_build_lsf_result_is_loaded_and_pushed_without_rebuild(
    tmp_path: Path,
) -> None:
    env, log = _podman_publish_env(tmp_path, "/tmp")
    env["IMAGE_BUILD_LSF_JOB_DIR"] = str(_image_build_lsf_job(tmp_path))
    env.pop("BUILD_CONTEXT")

    result = _run_podman_publish(env)

    assert result.returncode == 0, result.stdout + result.stderr
    commands = [
        line
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.startswith("COMMAND=")
    ]
    assert any(
        " load " in f" {line} " and "result.oci.tar" in line for line in commands
    )
    assert any(
        " tag " in f" {line} " and "localhost/oci-build-lsf:12345" in line
        for line in commands
    )
    assert not any(" build " in f" {line} " for line in commands)
    assert "Loading verified image-build-lsf result sha256:" in result.stdout


def test_image_build_lsf_archive_tampering_fails_before_podman(
    tmp_path: Path,
) -> None:
    env, log = _podman_publish_env(tmp_path, "/tmp")
    job = _image_build_lsf_job(tmp_path)
    archive = job / "output" / "result.oci.tar"
    with archive.open("ab") as stream:
        stream.write(b"tampered")
    env["IMAGE_BUILD_LSF_JOB_DIR"] = str(job)
    env.pop("BUILD_CONTEXT")

    result = _run_podman_publish(env)

    assert result.returncode != 0
    assert "archive length does not match success evidence" in result.stderr
    assert not log.exists()
    assert "fake-secret" not in result.stdout + result.stderr


def test_image_build_lsf_job_path_rejects_symlink(tmp_path: Path) -> None:
    env, log = _podman_publish_env(tmp_path, "/tmp")
    job = _image_build_lsf_job(tmp_path)
    link = tmp_path / "linked-job"
    link.symlink_to(job, target_is_directory=True)
    env["IMAGE_BUILD_LSF_JOB_DIR"] = str(link)
    env.pop("BUILD_CONTEXT")

    result = _run_podman_publish(env)

    assert result.returncode != 0
    assert "must not contain symlinks" in result.stderr
    assert not log.exists()


def _resolve_script(path: Path) -> str:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == "Resolve configuration":
                return step["run"]
    raise AssertionError(f"Resolve configuration step not found in {path}")


def test_probe_smoke_parses_image_stamp_without_sourcing_shell() -> None:
    script = PROBE_SMOKE.read_text(encoding="utf-8")

    assert "source .cache/harbor-last-image.env" not in script
    assert "while IFS='=' read -r key value" in script
    assert '[[ "$key" == "FULL_IMAGE" ]]' in script
    assert "invalid FULL_IMAGE" in script


def test_podman_security_contract_is_present_in_template() -> None:
    script = PUBLISH_TEMPLATE.read_text(encoding="utf-8")
    _assert_podman_security_contract(script)


@requires_platform_publisher
@pytest.mark.platform_repo
def test_podman_security_contract_is_present_in_root_mirror() -> None:
    script = platform_publish_script().read_text(encoding="utf-8")
    _assert_podman_security_contract(script)


def _assert_podman_security_contract(script: str) -> None:

    for required in (
        "canonical_secure_parent",
        "must not contain symlink components",
        "final directory must be EUID-owned",
        "ancestor must not be group/world writable",
        "umask 077",
        'mktemp -d -- "$PODMAN_TEMP_PARENT/pmXXXXXX"',
        'mktemp -d -- "$PODMAN_RUNROOT_PARENT/prXXXXXX"',
        'export REGISTRY_AUTH_FILE="$BASE/auth.json"',
        'rm -rf -- "$child"',
        "--password-stdin",
        "HARBOR_CREDENTIAL_LOCATION",
    ):
        assert required in script


def test_lsf_handoff_contract_is_present_in_template() -> None:
    template = PUBLISH_TEMPLATE.read_text(encoding="utf-8")
    for required in (
        "IMAGE_BUILD_LSF_JOB_DIR",
        "success.json",
        "result.oci.tar",
        'evidence.get("profile") != "slai-web-app-v1"',
        'evidence.get("platform") != "linux/amd64"',
        'evidence.get("probe_status") != 200',
        "archive length does not match success evidence",
        "archive digest does not match success evidence",
        "OCI manifest bytes do not match their digest",
        '"${pm[@]}" load --input "$LSF_ARCHIVE"',
        '"${pm[@]}" tag "$LSF_SOURCE_IMAGE" "$FULL_IMAGE"',
    ):
        assert required in template


@requires_platform_publisher
@pytest.mark.platform_repo
def test_lsf_handoff_publishers_are_identical() -> None:
    template = PUBLISH_TEMPLATE.read_text(encoding="utf-8")
    platform = platform_publish_script().read_text(encoding="utf-8")
    assert platform == template


def test_retired_remote_build_service_is_absent_from_creator() -> None:
    creator = REPO_ROOT / "skills" / "slai-app-creator"
    retired_names = (
        "-".join(("oci", "build", "service")),
        "-".join(("docker", "build", "service")),
    )
    documents = [creator / "SKILL.md", creator / "DESCRIPTION.md"]
    documents.extend((creator / "references").glob("*.md"))
    documents.extend((creator / "assets" / "templates").glob("*"))
    for path in documents:
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        assert all(name not in text for name in retired_names)
    assert not (creator / "references" / f"{retired_names[1]}.md").exists()
    assert not (
        creator / "assets" / "templates" / f"request-{retired_names[1]}.yml.example"
    ).exists()


def test_byoi_authorization_template_is_a_thin_pinned_caller() -> None:
    text = AUTHORIZE_EXISTING_TEMPLATE.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    trigger = workflow.get("on", workflow.get(True))
    authorize = workflow["jobs"]["authorize"]

    assert set(trigger["workflow_dispatch"]["inputs"]) == {
        "image_tag",
        "image_digest",
    }
    assert authorize["uses"] == (
        "AMD-SLAI/slai-app-platform/.github/workflows/app-image-publish.yml@"
        "6d3aaf56c3db7c1d19758c0d3b53ac0d672cd16e"
    )
    assert "slai-sc-<full-commit-sha>-<run-id>-<attempt>" in (
        trigger["workflow_dispatch"]["inputs"]["image_tag"]["description"]
    )
    assert "slai-sc-${GITHUB_SHA}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}" in text
    assert authorize["with"]["app_id"] == "${{ vars.APP_ID }}"
    assert authorize["with"]["image_repository"] == (
        "mkmhub.amd.com/hw-slaiapp-dev/${{ vars.APP_ID }}"
    )
    assert set(authorize["secrets"]) == {"HARBOR_USERNAME", "HARBOR_PASSWORD"}
    assert authorize["permissions"] == {
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
    }
    for forbidden in (
        "actions/checkout",
        "docker build",
        "podman build",
        "buildx",
        "upload-artifact",
        "phase0-image.tar",
    ):
        assert forbidden not in yaml.safe_dump(authorize)


@pytest.mark.parametrize('template', WORKFLOW_TEMPLATES)
@pytest.mark.parametrize('binding', ['', 'untrusted.example.test/private-project'])
def test_retired_deploy_template_cannot_publish_or_submit(tmp_path, template, binding):
    workflow = yaml.safe_load(template.read_text())
    assert set(workflow['jobs']) == {'update-creator'}
    job = workflow['jobs']['update-creator']
    assert job['runs-on'] == ['self-hosted', 'linux', 'x64']
    steps = job['steps']
    assert all('uses' not in step for step in steps)
    env = dict(os.environ, HARBOR_CREDENTIAL_LOCATION=binding, HARBOR_USERNAME='unused', HARBOR_PASSWORD='unused')
    result = subprocess.run(['bash', '-eu', '-c', steps[0]['run']], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert 'slai-app-creator' in result.stdout + result.stderr
    assert list(tmp_path.iterdir()) == []

def test_local_publisher_refuses_unbound_direct_credentials(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "SKIP_DOTENV": "1",
            "HARBOR_REGISTRY": "untrusted.example.test",
            "HARBOR_PROJECT": "private-project",
            "IMAGE_NAME": "example-app",
            "BUILD_CONTEXT": "tools/slai-asset-submission",
            "HARBOR_USERNAME": "fake-robot",
            "HARBOR_PASSWORD": "fake-secret",
        }
    )
    env.pop("HARBOR_CREDENTIAL_LOCATION", None)

    result = subprocess.run(
        ["bash", str(PUBLISH_TEMPLATE)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "not bound to the selected registry/project" in result.stderr
    assert "fake-secret" not in result.stdout + result.stderr


def test_local_publisher_refuses_cli_credentials_for_another_registry(
    tmp_path: Path,
) -> None:
    harbor = tmp_path / "harbor"
    harbor.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    harbor.chmod(0o700)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "credentials").write_text(
        """\
[project.private-project]
harbor_registry = trusted.example.test
robot_name = fake-robot
robot_secret = fake-secret
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "SKIP_DOTENV": "1",
            "HARBOR_REGISTRY": "untrusted.example.test",
            "HARBOR_PROJECT": "private-project",
            "IMAGE_NAME": "example-app",
            "BUILD_CONTEXT": "tools/slai-asset-submission",
            "HARBOR_CLI_BIN": str(harbor),
            "HARBOR_CONFIG_DIR": str(config_dir),
        }
    )
    for name in (
        "HARBOR_USERNAME",
        "HARBOR_PASSWORD",
        "HARBOR_CREDENTIAL_LOCATION",
    ):
        env.pop(name, None)

    result = subprocess.run(
        ["bash", str(PUBLISH_TEMPLATE)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "credential registry does not match HARBOR_REGISTRY" in result.stderr
    assert "fake-secret" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("parent_factory", "expected"),
    (
        (lambda tmp: str(tmp / "missing"), "existing directory"),
        (lambda tmp: "-leading-dash", "leading-dash paths are not allowed"),
    ),
)
def test_podman_temp_parent_rejects_invalid_paths(
    tmp_path: Path,
    parent_factory: Callable[[Path], str],
    expected: str,
) -> None:
    parent = parent_factory(tmp_path)
    env, _ = _podman_publish_env(tmp_path, parent)

    result = _run_podman_publish(env)

    assert result.returncode != 0
    assert expected in result.stderr
    assert "fake-secret" not in result.stdout + result.stderr


def test_podman_temp_parent_rejects_symlink_component(tmp_path: Path) -> None:
    target = tmp_path / "target"
    child = target / "private"
    child.mkdir(parents=True)
    target.chmod(0o700)
    child.chmod(0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    env, _ = _podman_publish_env(tmp_path, str(link / "private"))

    result = _run_podman_publish(env)

    assert result.returncode != 0
    assert "must not contain symlink components" in result.stderr


def test_podman_temp_parent_rejects_hostile_final_directory(tmp_path: Path) -> None:
    hostile = tmp_path / "hostile-final"
    hostile.mkdir()
    hostile.chmod(0o777)
    env, _ = _podman_publish_env(tmp_path, str(hostile))

    result = _run_podman_publish(env)

    assert result.returncode != 0
    assert "final directory must be EUID-owned" in result.stderr


def test_podman_temp_parent_rejects_hostile_ancestor(tmp_path: Path) -> None:
    hostile = tmp_path / "hostile-ancestor"
    private = hostile / "private"
    private.mkdir(parents=True)
    hostile.chmod(0o777)
    private.chmod(0o700)
    env, _ = _podman_publish_env(tmp_path, str(private))

    result = _run_podman_publish(env)

    assert result.returncode != 0
    assert "ancestor must not be group/world writable" in result.stderr


@pytest.mark.parametrize("parent_kind", ("tmp", "private"))
def test_podman_temp_parent_accepts_secure_parent_and_uses_private_auth(
    tmp_path: Path,
    parent_kind: str,
) -> None:
    if parent_kind == "tmp":
        parent = Path("/tmp")
    else:
        parent = tmp_path / "private"
        parent.mkdir()
        parent.chmod(0o700)
    env, log = _podman_publish_env(tmp_path, str(parent))

    result = _run_podman_publish(env)

    assert result.returncode == 0, result.stdout + result.stderr
    logged = log.read_text(encoding="utf-8")
    auth = Path(re.search(r"^AUTH=(.+)$", logged, re.MULTILINE).group(1))
    assert auth.parent.parent == parent.resolve()
    assert auth.parent.name.startswith("pm") and len(auth.parent.name) == 8
    assert "BASE_MODE=700" in logged
    assert "AUTH_MODE=600" in logged
    assert not auth.parent.exists()


def test_podman_uses_short_separate_runroot_for_long_secure_storage(
    tmp_path: Path,
) -> None:
    parent = tmp_path
    for segment in ("private-storage-with-a-long-name", "another-long-component"):
        parent = parent / segment
        parent.mkdir()
        parent.chmod(0o700)
    env, log = _podman_publish_env(tmp_path, str(parent), runroot_parent=None)

    result = _run_podman_publish(env)

    assert result.returncode == 0, result.stdout + result.stderr
    logged = log.read_text(encoding="utf-8")
    root = Path(re.search(r"^ROOT=(.+)$", logged, re.MULTILINE).group(1))
    runroot = Path(re.search(r"^RUNROOT=(.+)$", logged, re.MULTILINE).group(1))
    assert root.parent.parent == parent.resolve()
    assert runroot.parent == Path("/tmp")
    assert len(str(runroot)) <= 50
    assert runroot.name.startswith("pr") and len(runroot.name) == 8
    assert not root.parent.exists()
    assert not runroot.exists()


def test_podman_rejects_runroot_parent_that_cannot_meet_length_limit(
    tmp_path: Path,
) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    storage.chmod(0o700)
    runroot_parent = tmp_path
    for segment in ("runroot-parent-is-deliberately", "far-too-long"):
        runroot_parent = runroot_parent / segment
        runroot_parent.mkdir()
        runroot_parent.chmod(0o700)
    env, _ = _podman_publish_env(
        tmp_path,
        str(storage),
        runroot_parent=str(runroot_parent),
    )

    result = _run_podman_publish(env)

    assert result.returncode != 0
    assert "runroot would exceed Podman's 50-character limit" in result.stderr


def test_podman_cleanup_is_limited_to_exact_generated_children(tmp_path: Path) -> None:
    parent = tmp_path / "private"
    parent.mkdir()
    parent.chmod(0o700)
    sibling = parent / "pm123456-keep"
    sibling.mkdir()
    marker = sibling / "marker"
    marker.write_text("keep\n", encoding="utf-8")
    env, log = _podman_publish_env(tmp_path, str(parent), runroot_parent="/tmp")

    result = _run_podman_publish(env)

    assert result.returncode == 0, result.stdout + result.stderr
    logged = log.read_text(encoding="utf-8")
    root = Path(re.search(r"^ROOT=(.+)$", logged, re.MULTILINE).group(1))
    runroot = Path(re.search(r"^RUNROOT=(.+)$", logged, re.MULTILINE).group(1))
    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert not root.parent.exists()
    assert not runroot.exists()
    script = PUBLISH_TEMPLATE.read_text(encoding="utf-8")
    assert '"$prefix"??????)' in script
    assert 'rm -rf -- "$child"' in script
    assert 'mktemp -d -- "$PODMAN_TEMP_PARENT/pmXXXXXX"' in script


def test_standard_secret_template_does_not_surface_exception_pull_secret() -> None:
    standard_docs = list(
        yaml.safe_load_all(STANDARD_SECRET_TEMPLATE.read_text(encoding="utf-8"))
    )
    exception_docs = list(
        yaml.safe_load_all(EXCEPTION_PULL_SECRET_TEMPLATE.read_text(encoding="utf-8"))
    )

    assert len(standard_docs) == 1
    assert standard_docs[0]["type"] == "Opaque"
    assert len(exception_docs) == 1
    pull = exception_docs[0]
    assert pull["type"] == "kubernetes.io/dockerconfigjson"
    docker_config = json.loads(pull["stringData"][".dockerconfigjson"])
    assert set(next(iter(docker_config["auths"].values()))) == {"auth"}


def test_lsf_push_submits_verified_archive_without_local_podman(tmp_path: Path) -> None:
    env, podman_log = _podman_publish_env(tmp_path, "/tmp")
    job = _image_build_lsf_job(tmp_path)
    env["IMAGE_BUILD_LSF_JOB_DIR"] = str(job)
    env["IMAGE_TAG"] = "slai-sc-" + "a" * 40 + "-1-1"
    env["IMAGE_PUSH_LSF_PROJECT"] = "authorized-test-project"
    env.pop("BUILD_CONTEXT")
    push_job = tmp_path / "push-job"
    push_job.mkdir(mode=0o700)
    credential_input = tmp_path / "credentials-input.json"
    argument_log = tmp_path / "submit-arguments"
    submit = tmp_path / "submit.sh"
    submit.write_text(
        "#!/bin/sh\ncat > "+str(credential_input)+"\nprintf '%s\\n' \"$@\" > "+str(argument_log)+
        "\nprintf 'IMAGE_PUSH_LSF_JOB_DIR="+str(push_job)+"\\n'\n"
    )
    submit.chmod(0o700)
    result = tmp_path / "result.sh"
    result.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > "+str(tmp_path / "result-arguments")+"\n")
    result.chmod(0o700)
    env["IMAGE_PUSH_LSF_SUBMIT"] = str(submit)
    observed = _run_podman_publish(env)
    assert observed.returncode == 0, observed.stdout + observed.stderr
    assert not podman_log.exists()
    credential = json.loads(credential_input.read_text())
    assert credential["location"] == "mkmhub.amd.com/hw-slaiapp-dev"
    assert credential["password"] == "fake-secret"
    arguments = argument_log.read_text()
    assert str(job) in arguments and "authorized-test-project" in arguments
    assert "fake-secret" not in arguments + observed.stdout + observed.stderr
    assert str(push_job) in (tmp_path / "result-arguments").read_text()


def test_lsf_push_failure_does_not_record_harbor_stamp(tmp_path: Path) -> None:
    env, podman_log = _podman_publish_env(tmp_path, "/tmp")
    env["IMAGE_BUILD_LSF_JOB_DIR"] = str(_image_build_lsf_job(tmp_path))
    env["IMAGE_TAG"] = "slai-sc-" + "a" * 40 + "-1-1"
    env["IMAGE_PUSH_LSF_PROJECT"] = "authorized-test-project"
    submit = tmp_path / "submit.sh"
    submit.write_text("#!/bin/sh\ncat >/dev/null\nprintf 'IMAGE_PUSH_LSF_JOB_DIR=/tmp/test-push-job\\n'\n")
    submit.chmod(0o700)
    result = tmp_path / "result.sh"
    result.write_text("#!/bin/sh\nexit 1\n")
    result.chmod(0o700)
    env["IMAGE_PUSH_LSF_SUBMIT"] = str(submit)
    observed = _run_podman_publish(env)
    assert observed.returncode != 0
    assert not podman_log.exists()
    assert not Path(env["HARBOR_LAST_IMAGE_FILE"]).exists()
    assert "fake-secret" not in observed.stdout + observed.stderr


def test_publisher_records_repository_digest_and_keeps_release_tag(tmp_path: Path) -> None:
    env, _ = _podman_publish_env(tmp_path, "/tmp")
    env["IMAGE_TAG"] = "slai-sc-" + "a" * 40 + "-1-1"
    observed = _run_podman_publish(env)
    assert observed.returncode == 0, observed.stdout + observed.stderr
    record = Path(env["HARBOR_LAST_IMAGE_FILE"]).read_text()
    assert "FULL_IMAGE=mkmhub.amd.com/hw-slaiapp-dev/example-app@sha256:" + hashlib.sha256(b'{"schemaVersion":2,"layers":[]}').hexdigest() in record
    assert "IMAGE_TAG=" + env["IMAGE_TAG"] in record


def test_publisher_refuses_missing_destination_digest(tmp_path: Path) -> None:
    env, _ = _podman_publish_env(tmp_path, "/tmp")
    env["IMAGE_TAG"] = "slai-sc-" + "a" * 40 + "-1-1"
    env["HARBOR_TEST_MODE"] = "notfound"
    observed = _run_podman_publish(env)
    assert observed.returncode != 0
    assert not Path(env["HARBOR_LAST_IMAGE_FILE"]).exists()


@pytest.mark.parametrize("mode", ["tag-mismatch", "digest-mismatch", "notfound", "error", "oversized", "oversized-body", "redirect", "challenge-evil"])
def test_registry_verification_failure_never_stamps(tmp_path, mode):
    env, _ = _podman_publish_env(tmp_path, "/tmp")
    env["HARBOR_TEST_MODE"] = mode
    observed = _run_podman_publish(env)
    assert observed.returncode != 0
    assert not Path(env["HARBOR_LAST_IMAGE_FILE"]).exists()
    assert "Harbor manifest verification failed" in observed.stderr
    assert "fake-secret" not in observed.stdout + observed.stderr
    requests = Path(env["HARBOR_TEST_REQUEST_LOG"]).read_text()
    assert "evil.example" not in requests
    assert "fake-secret" not in requests


def test_registry_bearer_auth_and_digest_lookup(tmp_path):
    env, log = _podman_publish_env(tmp_path, "/tmp")
    env["HARBOR_TEST_MODE"] = "challenge-safe"
    observed = _run_podman_publish(env)
    assert observed.returncode == 0, observed.stdout + observed.stderr
    requests = Path(env["HARBOR_TEST_REQUEST_LOG"]).read_text()
    assert "/service/token?service=harbor-registry&scope=repository%3A" in requests
    assert "/manifests/sha256:" in requests
    assert " image inspect " not in log.read_text()


def test_python_discovery_without_python12_alias(tmp_path):
    env, _ = _podman_publish_env(tmp_path, "/tmp")
    # This host provides python3.12, but has no python12 alias.
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    import shutil
    runtime = shutil.which("python3.12")
    assert runtime
    (runtime_dir / "python12").write_text("#!/bin/sh\nexit 1\n")
    (runtime_dir / "python12").chmod(0o700)
    (runtime_dir / "python3.12").symlink_to(runtime)
    env["PATH"] = str(runtime_dir) + ":" + env["PATH"]
    observed = _run_podman_publish(env)
    assert observed.returncode == 0, observed.stdout + observed.stderr


def test_docker_publish_uses_registry_manifest_digest(tmp_path):
    env, _ = _podman_publish_env(tmp_path, "/tmp")
    bin_dir = tmp_path / "docker-bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_TEST_LOG"\nif [ "$1" = login ]; then cat >/dev/null; fi\n')
    docker.chmod(0o700)
    env.pop("FORCE_PODMAN")
    env["PATH"] = str(bin_dir) + ":" + env["PATH"]
    env["DOCKER_TEST_LOG"] = str(tmp_path / "docker.log")
    observed = _run_podman_publish(env)
    assert observed.returncode == 0, observed.stdout + observed.stderr
    commands = Path(env["DOCKER_TEST_LOG"]).read_text()
    assert "push " in commands and "build --platform linux/amd64" in commands
    assert "image inspect" not in commands
    assert "/manifests/sha256:" in Path(env["HARBOR_TEST_REQUEST_LOG"]).read_text()


@pytest.mark.parametrize("supported_name", ["python3.12", "python3"])
def test_python_discovery_falls_back_to_supported_name(tmp_path, supported_name):
    import sys
    env, _ = _podman_publish_env(tmp_path, "/tmp")
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    for name in ("python12", "python3.12", "python3"):
        target = runtime_dir / name
        if name == supported_name:
            target.symlink_to(sys.executable)
        else:
            target.write_text("#!/bin/sh\nexit 1\n")
            target.chmod(0o700)
    env["PATH"] = str(runtime_dir) + ":" + env["PATH"]
    observed = _run_podman_publish(env)
    assert observed.returncode == 0, observed.stdout + observed.stderr


def test_python_discovery_rejects_old_runtimes_before_credentials(tmp_path):
    env, log = _podman_publish_env(tmp_path, "/tmp")
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    for name in ("python12", "python3.12", "python3"):
        target = runtime_dir / name
        target.write_text("#!/bin/sh\nexit 1\n")
        target.chmod(0o700)
    env["PATH"] = str(runtime_dir) + ":" + env["PATH"]
    observed = _run_podman_publish(env)
    assert observed.returncode != 0
    assert "Python >=3.12 is required" in observed.stderr
    assert not log.exists()
    assert not Path(env["HARBOR_LAST_IMAGE_FILE"]).exists()
