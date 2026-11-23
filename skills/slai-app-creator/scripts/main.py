#!/usr/bin/env python12
"""
Validate deploy/<namespace>/<app_id>/ manifest bundles before platform deploy.

This is machine-checkable validation (CI / pre-PR), not manifest scaffolding.
Scaffolding is markdown + templates in the skill; this script only verifies a directory.

Usage:
  python12 main.py [--strict] <path-to-deploy/<namespace>/<app_id>>

Exits 0 if required manifests exist, images and resources are valid, and production
Ingress routes satisfy config/ingress-policy.yaml. New apps must use their exact
subdomain and the platform-owned slai-app-wildcard-tls Secret. Grandfathered
path-under-apex TLS changes use the platform-owned workflow.
Does not decrypt SOPS.

Default-deny namespaces (currently: slai-app-prod) also require networkpolicy.yaml,
and the validator cross-checks that the policy's ingress ports allow every
deployment.yaml containerPort and that egress allows TCP 4317 when
OTEL_EXPORTER_OTLP_ENDPOINT is set in the deployment env. Pod template
app.kubernetes.io/name must equal the bundle directory name (app_id).

With --strict, networkpolicy.yaml and OTEL env are required for ALL namespaces
(not only the default-deny ones).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
import subprocess
import json
from functools import lru_cache
from types import SimpleNamespace

from pathlib import Path

try:
    import yaml as _yaml
except ImportError:
    raise SystemExit("PyYAML is required for manifest validation. Install it with python -m pip install PyYAML.")

from yaml_limits import bounded_loader, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, WALL_SECONDS, YamlLimitError, read_file_bytes

# Namespaces known to run with default-deny network posture (Calico GlobalNetworkPolicy
# or namespace-wide deny-all). Per-app NetworkPolicy is mandatory for these — without
# one, even healthy pods are unreachable from the Ingress controller and other pods.
# Keep this list in sync with platform reality (see specs/07-network-ingress-dns.md).
DEFAULT_DENY_NAMESPACES = {"slai-app-prod"}

# Standard egress destinations the platform requires when used.
OTLP_PORT = 4317
SHARED_LDAP_SECRET_NAME = "slai-shared-ldap-bind"
SHARED_LDAP_CONSUMER_LABEL = "slai.amd.com/shared-ldap-consumer"
SHARED_LDAP_ENV_KEYS = {"LDAP_BIND_UPN", "LDAP_BIND_PASSWORD"}
# Generated auth-proxy NetworkPolicy selects pods by this label == app_id
# (the bundle directory name). Object metadata.name may differ.
APP_K8S_NAME_LABEL = "app.kubernetes.io/name"



class _ManifestYamlError(_yaml.YAMLError):
    def __init__(self, category, line=None, column=None):
        self.safe_message = "invalid YAML" if category == "invalid_yaml" else "manifest exceeds YAML size/complexity/resource limits"
        super().__init__(self.safe_message)
        self.problem_mark = None
        if type(line) is int and type(column) is int and 0 <= line <= MAX_INPUT_BYTES and 0 <= column <= MAX_INPUT_BYTES:
            self.problem_mark = SimpleNamespace(line=line, column=column)


def _parser_environment():
    environment = {"HOME": str(Path.home()), "PATH": os.defpath, "LANG": "C.UTF-8"}
    if "SystemRoot" in os.environ:
        environment["SystemRoot"] = os.environ["SystemRoot"]
    # The worker independently verifies the fixed protected image and manifest.
    # Client checkout paths and authentication material are never forwarded.
    if os.environ.get('SLAI_HOSTED_VALIDATOR_MODE') == 'immutable-image':
        environment['SLAI_HOSTED_VALIDATOR_MODE'] = 'immutable-image'
    return environment


@lru_cache(maxsize=2)
def _manifest_yaml_evidence(text):
    if len(text) > MAX_INPUT_BYTES:
        return {"ok": False, "category": "limits"}
    data = text.encode("utf-8")
    if len(data) > MAX_INPUT_BYTES:
        return {"ok": False, "category": "limits"}
    worker = Path(__file__).with_name("manifest_yaml.py")
    try:
        result = subprocess.run(
            [sys.executable, "-E", "-B", str(worker)], input=data,
            env=_parser_environment(), capture_output=True, timeout=WALL_SECONDS, check=False,
        )
        if result.returncode != 0 or len(result.stdout) > MAX_OUTPUT_BYTES:
            return {"ok": False, "category": "limits"}
        evidence = json.loads(result.stdout)
        if not isinstance(evidence, dict) or type(evidence.get("ok")) is not bool:
            return {"ok": False, "category": "limits"}
        return evidence
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"ok": False, "category": "limits"}


def _bounded_yaml_document(text):
    evidence = _manifest_yaml_evidence(text)
    if not evidence["ok"]:
        raise _ManifestYamlError(evidence.get("category"), evidence.get("line"), evidence.get("column"))
    return evidence.get("document")


def _manifest_file_text(path, errors):
    try:
        return read_file_bytes(path).decode("utf-8")
    except (OSError, UnicodeDecodeError, YamlLimitError):
        errors.append(f"{path}: manifest is unavailable or exceeds file-size/type limits")
        return ""


def ciphertext_errors(path: Path, namespace: str | None = None, app_id: str | None = None) -> list[str]:
    """Validate ciphertext in a byte-, complexity-, memory-, and time-bounded worker."""
    import json
    worker = Path(__file__).with_name("ciphertext_validation.py")
    environment = _parser_environment()
    arguments = [str(path)] + ([namespace] if namespace is not None else []) + ([app_id] if app_id is not None else [])
    allocations = None
    if namespace == 'slai-app-prod':
        try:
            allocations = json.dumps(sorted(_trusted_allocated_app_ids())).encode()
        except (OSError, ValueError, subprocess.SubprocessError):
            return [f'{path}: trusted platform application allocations are unavailable']
        arguments.append('--allocated-app-ids-stdin')
    try:
        result = subprocess.run(
            [sys.executable, "-E", "-B", str(worker), *arguments], input=allocations,
            env=environment, capture_output=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [f"{path}: ciphertext validation failed or exceeded time/resource limits"]
    if result.returncode != 0 or len(result.stdout) > 4096:
        return [f"{path}: ciphertext validation failed or exceeded time/resource limits"]
    try:
        messages = json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError):
        return [f"{path}: ciphertext validation returned invalid evidence"]
    if not isinstance(messages, list) or len(messages) > 1 or any(not isinstance(item, str) for item in messages):
        return [f"{path}: ciphertext validation returned invalid evidence"]
    return [f"{path}: {message}" for message in messages]


def _skill_layout_root() -> Path:
    """Plugin root or slai-app-platform root: parents[3] from scripts/main.py."""
    return Path(__file__).resolve().parents[3]


def platform_repo_root() -> Path:
    """Require an explicitly selected, validated private platform checkout."""
    packaged = Path(__file__).resolve().parents[3]
    mode = os.environ.get('SLAI_HOSTED_VALIDATOR_MODE', '')
    if mode:
        if mode != 'immutable-image' or packaged != Path('/opt/slai-app-platform'):
            raise ValueError('Hosted validator mode requires its fixed protected image root')
        from hosted_validator_provenance import verify_hosted_root
        return verify_hosted_root(packaged)
    from prepare_platform_checkout import trusted_validator_checkout
    override = os.environ.get('SLAI_PLATFORM_CLONE_DIR', '').strip()
    if not override:
        raise ValueError('Set SLAI_PLATFORM_CLONE_DIR to a private checkout prepared by prepare_platform_checkout.py')
    root = trusted_validator_checkout()
    # The selected handoff checkout is never imported or executed.
    # Imported validators can load sibling modules. Validate all scripts and
    # config entries, rather than only the two direct import targets.
    import stat
    for subtree in ('scripts', 'config'):
        directory = root / subtree
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('Platform scripts/config must be real directories')
        for base, dirs, files in os.walk(directory, followlinks=False):
            for name in dirs + files:
                path = Path(base) / name
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                    raise ValueError('Validator sources must be owned, not symlinked or writable by others')
                if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    raise ValueError('Validator sources must be regular files or directories')
                if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                    raise ValueError('Validator sources must have one link')
    return root


def _ingress_policy_errors(manifest_dir: Path) -> list[str]:
    """Run the repository's canonical route validator when available."""
    try:
        repo_root = platform_repo_root()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        return [str(error)]
    script = repo_root / "scripts/validate-ingress-policy.py"
    policy = repo_root / "config/ingress-policy.yaml"
    if not script.is_file() or not policy.is_file():
        return [
            "cannot validate production Ingress policy: expected "
            f"{script} and {policy}"
        ]
    spec = importlib.util.spec_from_file_location("slai_ingress_policy", script)
    if spec is None or spec.loader is None:
        return [f"cannot load production Ingress validator: {script}"]
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.validate_tree(repo_root, policy, manifest_dir)


def _platform_auth_policy_validation(
    manifest_dir: Path,
) -> tuple[list[str], list[str]]:
    """Delegate opt-in SSO validation to the canonical repository validator."""
    policy_path = manifest_dir / "auth-policy.json"
    if not policy_path.exists():
        return [], []

    try:
        repo_root = platform_repo_root()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        return [str(error)], []
    script = repo_root / "scripts/validate-platform-auth-policy.py"
    schema = repo_root / "config/schemas/platform-auth-policy.schema.json"
    if not script.is_file() or not schema.is_file():
        return [
            "cannot validate platform SSO enrollment: expected "
            f"{script} and {schema}"
        ], []
    spec = importlib.util.spec_from_file_location("slai_platform_auth_policy", script)
    if spec is None or spec.loader is None:
        return [f"cannot load platform SSO validator: {script}"], []
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        results, errors = module.validate_tree(
            repo_root,
            schema,
            only_dir=manifest_dir,
        )
    except Exception as exc:
        return [f"platform SSO policy validation failed to run: {exc}"], []

    notes = []
    for result in results:
        identity = result.identity
        cli_note = (
            f", cli_client_id={identity.client_id}-cli"
            if result.cli_enabled is not None
            else ""
        )
        notes.append(
            "note: platform SSO enrollment validates; derived "
            f"mode={result.mode}, client_id={identity.client_id}, "
            f"callback={identity.callback}{cli_note}. Policy validation alone does not "
            "provision the sidecar; require platform reconciliation status Ready."
        )
    return errors, notes


_CONTAINER_PORT_RE = re.compile(r"^\s*-\s*containerPort:\s*(\d+)\s*$", re.MULTILINE)
_OTEL_ENDPOINT_RE = re.compile(
    r"-\s*name:\s*OTEL_EXPORTER_OTLP_ENDPOINT\s*\n\s*value:\s*[\"']?\S+",
)
_PORT_LINE_RE = re.compile(r"^\s*(?:-\s*)?port:\s*(\d+)\b")
_RESOURCE_FIELD_RE = re.compile(r"^(cpu|memory):\s*(.+?)\s*$")
_REQUIRED_RESOURCE_FIELDS = (
    ("requests", "cpu"),
    ("requests", "memory"),
)
_DEFAULT_RESOURCE_HINT = (
    "resources: requests cpu=100m memory=256Mi"
)
_REGISTRY_HOST_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)
_IMAGE_PATH_SEGMENT_RE = re.compile(
    r"^[a-z0-9]+(?:(?:[._]|__|[-]+)[a-z0-9]+)*$"
)
_IMAGE_TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_IMAGE_DIGEST_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_+.-]*:[A-Fa-f0-9]{32,}$")
_SECRET_NAME_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[-a-z0-9]*[a-z0-9])?)*$"
)


def _container_ports(dep_text: str) -> list:
    return [int(m.group(1)) for m in _CONTAINER_PORT_RE.finditer(dep_text)]


def _has_otel_endpoint(dep_text: str) -> bool:
    return bool(_OTEL_ENDPOINT_RE.search(dep_text))


def _has_value(value) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() not in {"", "null", "~"}


def _image_reference_error(
    ref: object, *, require_digest: bool = False, approved_images: frozenset[str] = frozenset()
) -> str | None:
    """Validate a rendered Harbor-style registry/project/image reference."""
    if not isinstance(ref, str) or not ref:
        return "image must be a non-empty string"
    if ref != ref.strip() or any(char.isspace() for char in ref):
        return "image must not contain leading, trailing, or embedded whitespace"
    if "://" in ref:
        return "image must not include a URL scheme (use hostname/project/image:tag)"
    first_at = ref.find("@")
    first_slash = ref.find("/")
    if first_at != -1 and (first_slash == -1 or first_at < first_slash):
        return "registry hostname must not contain userinfo"
    if "@" in ref:
        image_path, digest = ref.rsplit("@", 1)
        if not _IMAGE_DIGEST_RE.fullmatch(digest):
            return "image digest must use algorithm:hex (at least 32 hex characters)"
    else:
        image_path, digest = ref, None

    parts = image_path.split("/")
    if len(parts) < 3:
        return "image must include registry hostname, Harbor project, and image name"
    if any(part in {"", ".", ".."} for part in parts):
        return "image path must not contain empty, '.' or '..' traversal segments"

    registry = parts[0]
    host, separator, port = registry.rpartition(":")
    if not separator:
        host, port = registry, ""
    elif not port.isdigit() or not (1 <= int(port) <= 65535):
        return "registry port must be an integer from 1 to 65535"
    if not _REGISTRY_HOST_RE.fullmatch(host):
        return "registry must be a hostname without a scheme, userinfo, or path"

    final_segment = parts[-1]
    tag = None
    if ":" in final_segment:
        final_segment, tag = final_segment.rsplit(":", 1)
    path_segments = [*parts[1:-1], final_segment]
    if not all(_IMAGE_PATH_SEGMENT_RE.fullmatch(part) for part in path_segments):
        return (
            "Harbor project and image path segments must be lowercase alphanumeric "
            "with valid '.', '_' or '-' separators"
        )
    if tag is not None and not _IMAGE_TAG_RE.fullmatch(tag):
        return "image tag has invalid syntax"
    if digest is None:
        if tag is None:
            return (
                "image must use an explicit immutable tag or digest "
                "(do not rely on :latest)"
            )
        if tag.lower() == "latest":
            return "avoid :latest for production-like deploys; use immutable tag (e.g. git SHA)"
    if require_digest and (tag is not None or digest is None or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)):
        return "production image must be pinned to repository@sha256:<64 lowercase hex>"
    if require_digest and ref not in approved_images and (registry != 'mkmhub.amd.com' or parts[1] != 'hw-slaiapp-dev'):
        return "production image must be under mkmhub.amd.com/hw-slaiapp-dev/"
    return None


def _yaml_error_message(error: Exception) -> str:
    """Retain numeric parser locations without quoting manifest contents."""
    mark = getattr(error, "problem_mark", None)
    if isinstance(error, _ManifestYamlError) and mark is None:
        return error.safe_message
    if mark is not None and isinstance(mark.line, int) and isinstance(mark.column, int):
        return f"invalid YAML at line {mark.line + 1}, column {mark.column + 1}"
    return "invalid YAML"


@lru_cache(maxsize=1)
def _trusted_allocated_app_ids():
    """Read allocations only from the authenticated, pinned platform snapshot."""
    namespace = platform_repo_root() / 'deploy' / 'slai-app-prod'
    if not namespace.is_dir() or namespace.is_symlink():
        raise ValueError('trusted platform application allocations are unavailable')
    return frozenset(path.name for path in namespace.iterdir() if path.is_dir() and not path.is_symlink())


def _application_owns(name, app_id, path, allocated_app_ids=None):
    if allocated_app_ids is None:
        allocated_app_ids = _trusted_allocated_app_ids() if path.parent.parent.name == 'slai-app-prod' else ()
    return (isinstance(name, str) and (name == app_id or name.startswith(app_id + '-'))
            and not any(other != app_id and other.startswith(app_id + '-')
                        and (name == other or name.startswith(other + '-'))
                        for other in allocated_app_ids))


def _reviewed_legacy_deployment(document, path, app_id):
    if document.get('kind') != 'Deployment' or document.get('metadata', {}).get('name') != 'hosted-slai-' + str(app_id):
        return False
    from bundle_resources import reviewed_baseline_files
    from yaml_limits import bounded_loader
    raw = reviewed_baseline_files().get('deploy/slai-app-prod/' + str(app_id) + '/' + path.name)
    if not raw:
        return False
    loader = bounded_loader(raw)
    try:
        while loader.check_data():
            base = loader.get_data()
            if isinstance(base, dict) and base.get('kind') == 'Deployment' and base.get('metadata', {}).get('name') == document['metadata']['name'] and base.get('metadata', {}).get('namespace') == 'slai-app-prod':
                return True
    finally:
        loader.dispose()
    return False


def _bundle_resource_errors(document, path, app_id=None):
    """Fence resources whose security validators are bound to canonical filenames."""
    canonical = {
        "deployment.yaml": (("apps/v1",), "Deployment"),
        "service.yaml": (("v1",), "Service"),
        "z-ingress.yaml": (("networking.k8s.io/v1",), "Ingress"),
        "networkpolicy.yaml": (("networking.k8s.io/v1",), "NetworkPolicy"),
        "image-policy.yaml": (("slai.amd.com/v1alpha2", "slai.amd.com/v1alpha3"), "AppImagePolicy"),
        "cli-auth-policy.yaml": (("slai.amd.com/v1alpha1",), "PlatformCliAuthPolicy"),
    }
    if not isinstance(document, dict):
        return [f"{path}: expected one supported resource mapping"]
    kind = document.get("kind")
    api = document.get("apiVersion")
    if kind in {'ServiceAccount', 'Role', 'RoleBinding'}:
        from bundle_resources import reviewed_baseline_files
        baseline = reviewed_baseline_files()
        reviewed = baseline.get('deploy/slai-app-prod/' + str(app_id) + '/' + path.name)
        matches = []
        if reviewed is not None:
            loader = bounded_loader(reviewed)
            try:
                while loader.check_data(): matches.append(loader.get_data())
            finally:
                loader.dispose()
        if document not in matches:
            return [f'{path}: controller identity and RBAC require exact reviewed platform baseline']

    expected = canonical.get(path.name)
    if expected is not None:
        if api not in expected[0] or kind != expected[1]:
            return [f"{path}: resource apiVersion/kind must match the canonical bundle filename"]
        if kind in ('AppImagePolicy', 'PlatformCliAuthPolicy'):
            return []
        if app_id is not None:
            metadata = document.get('metadata', {})
            name = metadata.get('name') if isinstance(metadata, dict) else None
            owned = _application_owns(name, app_id, path) or _reviewed_legacy_deployment(document, path, app_id)
            if kind == 'Ingress':
                owned = owned or name == 'hosted-slai-' + app_id
            if not owned:
                return [f'{path}: canonical resource name must belong to the application']
            if kind == 'Service':
                spec = document.get('spec', {})
                if not isinstance(spec, dict):
                    return [f'{path}: Service spec must be a mapping']
                ports = spec.get('ports', [])
                if not isinstance(ports, list) or any(not isinstance(port, dict) for port in ports):
                    return [f'{path}: Service ports must be a list of mappings']
                from bundle_resources import service_spec_errors
                service_errors = service_spec_errors(spec)
                if service_errors:
                    return [f'{path}: {error}' for error in service_errors]
                selector = spec.get('selector')
                if not isinstance(selector, dict) or selector.get(APP_K8S_NAME_LABEL) != app_id:
                    return [f'{path}: Service selector must select the bundle application']
        return []
    if (api, kind) not in (("v1", "ServiceAccount"), ("rbac.authorization.k8s.io/v1", "Role"), ("rbac.authorization.k8s.io/v1", "RoleBinding"), ("v1", "ConfigMap"), ("v1", "PersistentVolumeClaim"), ("v1", "Service"), ("apps/v1", "Deployment"), ("apps/v1", "StatefulSet"), ("apps/v1", "DaemonSet"), ("batch/v1", "Job"), ("batch/v1", "CronJob"), ("networking.k8s.io/v1", "NetworkPolicy"), ("networking.k8s.io/v1", "Ingress")):
        return [f"{path}: unsupported additional resource; workloads and network policies must use their canonical bundle filenames"]
    if app_id is not None:
        metadata = document.get('metadata', {})
        name = metadata.get('name') if isinstance(metadata, dict) else None
        if not (_application_owns(name, app_id, path) or _reviewed_legacy_deployment(document, path, app_id) or kind == 'Ingress' and name == 'hosted-slai-' + app_id + '-cimd' and path.name == 'z-ingress-cimd.yaml'):
            return [f'{path}: additional resource names must start with the application id and a hyphen']
    if kind == 'PersistentVolumeClaim':
        spec = document.get('spec')
        if not isinstance(spec, dict):
            return [f'{path}: PVC spec must be a mapping']
        errors = []
        for field in ('volumeName', 'selector', 'dataSource', 'dataSourceRef'):
            if field in spec:
                errors.append(f'{path}: PVC {field} is not supported; request newly provisioned application storage')
        if spec.get('storageClassName') != 'nfs-network':
            errors.append(f'{path}: PVC storageClassName must be nfs-network')
        return errors
    return []


def _namespace_errors(document, path, namespace):
    if not isinstance(document, dict):
        return [f"{path}: expected a Kubernetes manifest mapping"]
    metadata = document.get("metadata", {})
    if not isinstance(metadata, dict):
        return [f"{path}: metadata must be a mapping"]
    declared = metadata.get("namespace")
    if document.get("kind") == "PlatformCliAuthPolicy":
        return []
    if declared != namespace:
        return [f"{path}: manifest namespace must match bundle namespace"]
    # Kubernetes List items also need namespace consistency.
    if document.get("kind") == "List":
        items = document.get("items")
        if not isinstance(items, list):
            return [f"{path}: List items must be an array of manifests"]
        errors = []
        for item in items:
            errors.extend(_namespace_errors(item, path, namespace))
        return errors
    return []


def _secret_reference_errors(pod_spec: dict, dep: Path) -> list[str]:
    """Restrict every supported pod Secret reference to the allocated app names."""
    errors = []
    app_id = dep.parent.name
    from bundle_resources import reviewed_baseline_files
    reviewed_text = reviewed_baseline_files().get('deploy/slai-app-prod/' + app_id + '/' + dep.name)
    reviewed = _bounded_yaml_document(reviewed_text) if reviewed_text else {}
    reviewed_pod = reviewed.get('spec', {}).get('template', {}).get('spec', {})
    reviewed_volumes = reviewed_pod.get('volumes', [])
    approved_tls = [v.get('secret') for v in pod_spec.get('volumes', [])
                    if isinstance(v, dict) and v in reviewed_volumes and isinstance(v.get('secret'), dict)
                    and v['secret'].get('secretName') == 'slai-app-wildcard-tls']
    def visit(value, ancestry=()):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ('secretKeyRef', 'secretRef', 'secret', 'nodePublishSecretRef'):
                    field = 'name' if key != 'secret' or ancestry[-2:] == ('projected', 'sources') else 'secretName'
                    name = child.get(field) if isinstance(child, dict) else None
                    if isinstance(child, dict) and ('secretName' if field == 'name' else 'name') in child:
                        errors.append(f'{dep}: Secret reference contains an unsupported identity field')
                    if name == app_id + '-harbor-pull':
                        errors.append(f'{dep}: harbor-pull Secret is restricted to imagePullSecrets')
                    if name == app_id + '-tls':
                        errors.append(f'{dep}: platform-managed TLS private keys must not be mounted or injected into application pods')
                    if not (key == 'secret' and child in approved_tls) and not _application_owns(name, app_id, dep):
                        errors.append(f'{dep}: environment and volume Secrets must be application-owned')
                elif key in ('persistentVolumeClaim', 'configMap', 'configMapKeyRef', 'configMapRef'):
                    name = child.get('name', child.get('claimName')) if isinstance(child, dict) else None
                    if not _application_owns(name, app_id, dep):
                        errors.append(f'{dep}: ConfigMap and PVC references must be application-owned')
                elif key == 'imagePullSecrets':
                    if not isinstance(child, list) or any(not isinstance(item, dict) or (item.get('name') != app_id + '-harbor-pull' or not _application_owns(item.get('name'), app_id, dep)) for item in child):
                        errors.append(f'{dep}: imagePullSecrets must use the application-owned harbor-pull Secret')
                visit(child, ancestry + (key,))
        elif isinstance(value, list):
            for child in value:
                visit(child, ancestry)
    visit(pod_spec)
    return errors


def _pod_security_errors(pod_spec: dict, dep: Path) -> list[str]:
    """Enforce the restricted pod settings used by the bundled template."""
    errors = []
    if pod_spec.get('serviceAccountName', 'default') != 'default' or pod_spec.get('serviceAccount', 'default') != 'default':
        errors.append(f'{dep}: application pods must use the default service account')
    if pod_spec.get('automountServiceAccountToken') is not False:
        errors.append(f'{dep}: application pods must disable service-account token mounting')
    for field in ('hostNetwork', 'hostPID', 'hostIPC'):
        if pod_spec.get(field, False) is not False:
            errors.append(f'{dep}: {field} is forbidden')
    volumes = pod_spec.get('volumes', [])
    supported = {'emptyDir', 'persistentVolumeClaim', 'secret', 'configMap', 'projected'}
    if not isinstance(volumes, list):
        errors.append(f'{dep}: volumes must be a list of mappings')
    else:
        for volume in volumes:
            if not isinstance(volume, dict):
                errors.append(f'{dep}: volumes must be mappings')
                continue
            kinds = set(volume) - {'name'}
            if len(kinds) != 1 or not kinds <= supported:
                errors.append(f'{dep}: volume must use exactly one supported source; hostPath and inline NFS/CSI are forbidden')
                continue
            kind = next(iter(kinds))
            if not isinstance(volume[kind], dict):
                errors.append(f'{dep}: volume source must be a mapping')
                continue
            if kind == 'projected':
                sources = volume[kind].get('sources', [])
                if not isinstance(sources, list):
                    errors.append(f'{dep}: projected sources must be a list')
                    continue
                for source in sources:
                    if (not isinstance(source, dict) or len(source) != 1
                            or not set(source) <= {'secret', 'configMap', 'downwardAPI'}
                            or not isinstance(next(iter(source.values())), dict)):
                        errors.append(f'{dep}: projected sources must use secret, configMap, or downwardAPI; service-account tokens are forbidden')
        errors.extend(_secret_reference_errors({'volumes': volumes}, dep))
    pod_context = pod_spec.get('securityContext', {})
    if not isinstance(pod_context, dict):
        return errors + [f'{dep}: pod securityContext must be a mapping']
    if pod_context.get('sysctls', []) != []:
        errors.append(f'{dep}: pod sysctls are not supported; omit securityContext.sysctls')
    for group in ('containers', 'initContainers', 'ephemeralContainers'):
        entries = pod_spec.get(group, [])
        if not isinstance(entries, list):
            errors.append(f'{dep}: {group} must be a list')
            continue
        for container in entries:
            if not isinstance(container, dict):
                errors.append(f'{dep}: {group} entries must be mappings')
                continue
            ports = container.get('ports', [])
            if (not isinstance(ports, list) or any(not isinstance(port, dict)
                    or port.get('hostPort', 0) != 0 for port in ports)):
                errors.append(f'{dep}: container ports must be mappings without hostPort exposure')
            context = container.get('securityContext', {})
            if not isinstance(context, dict):
                errors.append(f'{dep}: container securityContext must be a mapping')
                continue
            if context.get('procMount', 'Default') != 'Default':
                errors.append(f'{dep}: containers must use Default procMount')
            if context.get('privileged', False) is not False or context.get('allowPrivilegeEscalation') is not False:
                errors.append(f'{dep}: containers must disable privilege escalation and privileged mode')
            if context.get('runAsNonRoot', pod_context.get('runAsNonRoot')) is not True or context.get('runAsUser', pod_context.get('runAsUser')) == 0:
                errors.append(f'{dep}: containers must run as non-root')
            capabilities = context.get('capabilities', {})
            if not isinstance(capabilities, dict) or not isinstance(capabilities.get('drop'), list) or 'ALL' not in capabilities['drop'] or capabilities.get('add', []):
                errors.append(f'{dep}: containers must drop ALL capabilities without adding any')
            seccomp = context.get('seccompProfile', pod_context.get('seccompProfile', {}))
            if not isinstance(seccomp, dict) or seccomp.get('type') != 'RuntimeDefault':
                errors.append(f'{dep}: containers must use RuntimeDefault seccomp')
    return errors


def _deployment_reference_errors(
    dep_text: str, dep: Path
) -> tuple[list[str], list[str]] | None:
    """Validate container images and optional pod-level imagePullSecrets with YAML."""
    require_digest = dep.parent.parent.name in DEFAULT_DENY_NAMESPACES
    if _yaml is None:
        if require_digest:
            return ([f"{dep}: PyYAML is required to validate production image digests"], [])
        return None
    try:
        doc = _bounded_yaml_document(dep_text)
    except Exception as exc:
        return ([f"{dep}: {_yaml_error_message(exc)}"], [])
    if not isinstance(doc, dict):
        return ([f"{dep}: expected a Kubernetes Deployment document"], [])

    namespace_errors = _namespace_errors(doc, dep, dep.parent.parent.name)
    if namespace_errors:
        return (namespace_errors, [])

    spec = doc.get("spec")
    tmpl = spec.get("template") if isinstance(spec, dict) else None
    pod_spec = tmpl.get("spec") if isinstance(tmpl, dict) else None
    containers = pod_spec.get("containers") if isinstance(pod_spec, dict) else None
    if not isinstance(containers, list) or not containers:
        return ([f"{dep}: expected spec.template.spec.containers[]"], [])

    errors = _pod_security_errors(pod_spec, dep) + _secret_reference_errors(pod_spec, dep)
    # Hosted callers derive these exact pins from an authenticated immutable
    # platform base. Preserve that existing compatibility exception; submitted
    # image-release.json is never an authority for bypassing the registry rule.
    try:
        approved = json.loads(os.environ.get('SLAI_BASELINE_APPROVED_IMAGES', '[]'))
        if not isinstance(approved, list) or any(not isinstance(image, str) for image in approved):
            raise ValueError('invalid approved image context')
        approved = frozenset(approved)
    except (ValueError, TypeError):
        return ([f"{dep}: invalid approved image context"], [])
    notes = []
    groups = [("containers", containers)]
    init_containers = pod_spec.get("initContainers")
    if init_containers is not None:
        if not isinstance(init_containers, list):
            errors.append(f"{dep}: expected spec.template.spec.initContainers[]")
        else:
            groups.append(("initContainers", init_containers))
    for group, entries in groups:
        kind = "container" if group == "containers" else "init container"
        for idx, container in enumerate(entries, start=1):
            location = f"spec.template.spec.{group}[{idx - 1}]"
            if not isinstance(container, dict):
                errors.append(f"{dep}: {location} must be a container mapping")
                continue
            name = container.get("name") or f"#{idx}"
            if "imagePullSecrets" in container:
                errors.append(
                    f"{dep}: {kind} {name!r} has imagePullSecrets at container level; "
                    f"move it to spec.template.spec.imagePullSecrets ({location})"
                )
            image_error = _image_reference_error(
                container.get("image"), require_digest=require_digest, approved_images=approved
            )
            if image_error:
                errors.append(f"{dep}: {kind} {name!r} image: {image_error} ({location})")

    pull_secrets = pod_spec.get("imagePullSecrets")
    if pull_secrets is not None:
        if not isinstance(pull_secrets, list) or not pull_secrets:
            errors.append(
                f"{dep}: spec.template.spec.imagePullSecrets must be a non-empty list "
                "of name mappings, or be omitted when credentials are unnecessary"
            )
        else:
            names = []
            for idx, item in enumerate(pull_secrets, start=1):
                if not isinstance(item, dict) or set(item) != {"name"}:
                    errors.append(
                        f"{dep}: imagePullSecrets item #{idx} must be a mapping "
                        "with only a name field"
                    )
                    continue
                name = item.get("name")
                if not isinstance(name, str) or not _SECRET_NAME_RE.fullmatch(name):
                    errors.append(
                        f"{dep}: imagePullSecrets item #{idx} name must be a valid "
                        "DNS-1123 Secret name"
                    )
                    continue
                names.append(name)
            if len(names) != len(set(names)):
                errors.append(
                    f"{dep}: spec.template.spec.imagePullSecrets contains duplicate names"
                )
            if names and not errors:
                joined = ", ".join(repr(name) for name in names)
                notes.append(
                    f"note: {dep}: imagePullSecrets {joined} structurally valid; this validator "
                    "does not decrypt secrets.enc.yaml. Ensure each matching encrypted Secret has "
                    "type kubernetes.io/dockerconfigjson and a .dockerconfigjson key."
                )
    return errors, notes


def _app_name_label_errors(dep_text: str, dep: Path) -> list[str]:
    """Require pod labels to match the bundle directory (SSO NetworkPolicy contract)."""
    if _yaml is None:
        return []
    try:
        doc = _bounded_yaml_document(dep_text)
    except Exception:
        return []
    if not isinstance(doc, dict):
        return []

    app_id = dep.parent.name
    spec = doc.get("spec")
    spec = spec if isinstance(spec, dict) else {}
    template = spec.get("template")
    template = template if isinstance(template, dict) else {}
    tmpl_meta = template.get("metadata")
    tmpl_meta = tmpl_meta if isinstance(tmpl_meta, dict) else {}
    labels = tmpl_meta.get("labels")
    labels = labels if isinstance(labels, dict) else {}
    actual = labels.get(APP_K8S_NAME_LABEL)
    if actual != app_id:
        shown = "<missing>" if actual is None else repr(actual)
        return [
            f"{dep}: spec.template.metadata.labels[{APP_K8S_NAME_LABEL!r}] must equal "
            f"the bundle directory name {app_id!r} (got {shown}). "
            f"Enrollment NetworkPolicy {app_id}-auth-proxy selects that label; a "
            f"mismatch drops inbound 4180 in default-deny and the site returns 504. "
            f"Deployment object names may differ from app_id."
        ]

    selector = spec.get("selector")
    selector = selector if isinstance(selector, dict) else {}
    match = selector.get("matchLabels")
    match = match if isinstance(match, dict) else {}
    selected = match.get(APP_K8S_NAME_LABEL)
    if selected != app_id:
        return [
            f"{dep}: spec.selector.matchLabels[{APP_K8S_NAME_LABEL!r}] must equal "
            f"{app_id!r} (got {selected!r})."
        ]
    if any(labels.get(key) != value for key, value in match.items()):
        return [f'{dep}: Deployment selector must match every selected pod template label']
    expressions = selector.get('matchExpressions', [])
    if not isinstance(expressions, list):
        return [f'{dep}: selector matchExpressions must be a list']
    for expression in expressions:
        if not isinstance(expression, dict) or set(expression) - {'key', 'operator', 'values'}:
            return [f'{dep}: invalid selector matchExpression']
        key, operator = expression.get('key'), expression.get('operator')
        values = expression.get('values', [])
        if not isinstance(key, str) or not key or not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            return [f'{dep}: invalid selector matchExpression key or values']
        if operator in ('In', 'NotIn'):
            if not values:
                return [f'{dep}: selector In/NotIn requires nonempty values']
            matches = key in labels and labels[key] in values if operator == 'In' else key not in labels or labels[key] not in values
        elif operator in ('Exists', 'DoesNotExist'):
            if values:
                return [f'{dep}: selector Exists/DoesNotExist forbids values']
            matches = key in labels if operator == 'Exists' else key not in labels
        else:
            return [f'{dep}: unsupported selector matchExpression operator']
        if not matches:
            return [f'{dep}: Deployment selector matchExpression does not match pod template']
    return []


def _shared_ldap_errors_from_yaml(dep_text: str, dep: Path) -> list[str]:
    """Reject deprecated platform bind credentials in all pod reference forms."""
    try:
        doc = _bounded_yaml_document(dep_text)
    except Exception:
        return [f"{dep}: invalid YAML for LDAP credential validation"]
    if not isinstance(doc, dict):
        return []
    pod = ((doc.get("spec") or {}).get("template") or {}).get("spec") or {}
    errors: list[str] = []
    references = False
    for group in ("containers", "initContainers", "ephemeralContainers"):
        for container in pod.get(group) or []:
            if not isinstance(container, dict):
                continue
            for env in container.get("env") or []:
                if not isinstance(env, dict):
                    continue
                if env.get("name") in SHARED_LDAP_ENV_KEYS:
                    errors.append(
                        f"{dep}: must not set {env['name']} as a literal value or credential reference; "
                        "use anonymous LDAPS with bind DN and password unset"
                    )
                value_from = env.get("valueFrom") or {}
                ref = value_from.get("secretKeyRef") or {}
                references |= ref.get("name") == SHARED_LDAP_SECRET_NAME
            for env_from in container.get("envFrom") or []:
                if isinstance(env_from, dict):
                    references |= (env_from.get("secretRef") or {}).get("name") == SHARED_LDAP_SECRET_NAME
    for volume in pod.get("volumes") or []:
        if not isinstance(volume, dict):
            continue
        references |= (volume.get("secret") or {}).get("secretName") == SHARED_LDAP_SECRET_NAME
        for source in (volume.get("projected") or {}).get("sources") or []:
            if isinstance(source, dict):
                references |= (source.get("secret") or {}).get("name") == SHARED_LDAP_SECRET_NAME
    if references:
        errors.append(
            f"{dep}: applications must not reference deprecated {SHARED_LDAP_SECRET_NAME}; "
            "use anonymous LDAPS at ldaps://ldap.amd.com:636 with bind DN and password unset"
        )
    labels = (doc.get("metadata") or {}).get("labels") or {}
    if str(labels.get(SHARED_LDAP_CONSUMER_LABEL, "")).lower() == "true":
        errors.append(f"{dep}: remove deprecated {SHARED_LDAP_CONSUMER_LABEL} consumer label")
    return errors


def _resource_errors_from_yaml(dep_text: str, dep: Path) -> list[str] | None:
    if _yaml is None:
        return None
    try:
        doc = _bounded_yaml_document(dep_text)
    except Exception:
        return None
    if not isinstance(doc, dict):
        return [f"{dep}: expected a Kubernetes Deployment document"]
    spec = doc.get("spec")
    tmpl = spec.get("template") if isinstance(spec, dict) else None
    pod_spec = tmpl.get("spec") if isinstance(tmpl, dict) else None
    containers = pod_spec.get("containers") if isinstance(pod_spec, dict) else None
    if not isinstance(containers, list) or not containers:
        return [f"{dep}: expected spec.template.spec.containers[]"]

    errors = []
    for idx, container in enumerate(containers, start=1):
        if not isinstance(container, dict):
            errors.append(f"{dep}: container #{idx} is not a mapping")
            continue
        name = container.get("name") or f"#{idx}"
        resources = container.get("resources")
        resources = resources if isinstance(resources, dict) else {}
        missing = []
        for group, key in _REQUIRED_RESOURCE_FIELDS:
            values = resources.get(group)
            values = values if isinstance(values, dict) else {}
            if not _has_value(values.get(key)):
                missing.append(f"resources.{group}.{key}")
        if missing:
            errors.append(
                f"{dep}: container {name!r} missing {', '.join(missing)}. "
                f"Add {_DEFAULT_RESOURCE_HINT} or an app-specific equivalent."
            )
    return errors


def _resource_errors_from_lines(dep_text: str, dep: Path) -> list[str]:
    containers = []
    in_containers = False
    containers_indent = -1
    item_indent = None
    current = None
    resources_indent = None
    resource_group = None
    resource_group_indent = -1

    def finish_current():
        nonlocal current
        if current is not None:
            containers.append(current)
            current = None

    for line_no, line in enumerate(dep_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())

        if not in_containers:
            if stripped == "containers:":
                in_containers = True
                containers_indent = indent
            continue

        if indent <= containers_indent and not stripped.startswith("-"):
            finish_current()
            break

        if stripped.startswith("- name:") and indent > containers_indent:
            if item_indent is None:
                item_indent = indent
            if indent == item_indent:
                finish_current()
                name = stripped.split(":", 1)[1].strip().strip("\"'")
                current = {"name": name or f"line {line_no}", "fields": set()}
                resources_indent = None
                resource_group = None
                resource_group_indent = -1
                continue

        if current is None:
            continue

        if resources_indent is not None and indent <= resources_indent:
            resources_indent = None
            resource_group = None
            resource_group_indent = -1

        if stripped == "resources:" and indent > (item_indent or containers_indent):
            resources_indent = indent
            resource_group = None
            resource_group_indent = -1
            continue

        if resources_indent is not None and indent > resources_indent:
            if stripped in {"requests:", "limits:"}:
                resource_group = stripped[:-1]
                resource_group_indent = indent
                continue
            if resource_group and indent > resource_group_indent:
                m = _RESOURCE_FIELD_RE.match(stripped)
                if m and _has_value(m.group(2).split("#", 1)[0]):
                    current["fields"].add((resource_group, m.group(1)))

    finish_current()

    if not containers:
        return [f"{dep}: expected spec.template.spec.containers[]"]

    errors = []
    for container in containers:
        missing = [
            f"resources.{group}.{key}"
            for group, key in _REQUIRED_RESOURCE_FIELDS
            if (group, key) not in container["fields"]
        ]
        if missing:
            errors.append(
                f"{dep}: container {container['name']!r} missing {', '.join(missing)}. "
                f"Add {_DEFAULT_RESOURCE_HINT} or an app-specific equivalent."
            )
    return errors


def _resource_errors(dep_text: str, dep: Path) -> list[str]:
    parsed = _resource_errors_from_yaml(dep_text, dep)
    if parsed is not None:
        return parsed
    return _resource_errors_from_lines(dep_text, dep)


def _networkpolicy_errors(np_text: str, dep_text: str, path: Path) -> list[str]:
    """Validate the restricted onboarding policy, including its access peers."""
    import ipaddress
    try:
        policy = _bounded_yaml_document(np_text)
        deployment = _bounded_yaml_document(dep_text)
        if not isinstance(policy, dict) or policy.get('kind') != 'NetworkPolicy' or policy.get('apiVersion') != 'networking.k8s.io/v1':
            raise ValueError('expected networking.k8s.io/v1 NetworkPolicy')
        spec = policy['spec']
        template = deployment['spec']['template']
        labels = template['metadata']['labels']
        selector = spec['podSelector']
        selected = selector.get('matchLabels', {})
        if (not selected or selector.get('matchExpressions') or
                selected.get('app.kubernetes.io/name') != labels.get('app.kubernetes.io/name') or
                any(labels.get(k) != v for k, v in selected.items())):
            raise ValueError('podSelector must select the application by matching pod labels')
        if policy.get('metadata', {}).get('namespace', path.parent.parent.name) != path.parent.parent.name:
            raise ValueError('NetworkPolicy namespace must match the deployment bundle')
        if set(spec.get('policyTypes', [])) != {'Ingress', 'Egress'}:
            raise ValueError('policyTypes must include Ingress and Egress')
        allowed = {'ingress': set(), 'egress': set()}
        controller = {
            'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
            'podSelector': {'matchLabels': {
                'app.kubernetes.io/component': 'controller',
                'app.kubernetes.io/instance': 'rke2-ingress-nginx',
                'app.kubernetes.io/name': 'rke2-ingress-nginx'}},
        }
        for direction, peer_key in (('ingress', 'from'), ('egress', 'to')):
            rules = spec.get(direction, [])
            if not isinstance(rules, list):
                raise ValueError(f'{direction} must be a list')
            for rule in rules:
                if not isinstance(rule, dict) or set(rule) - {peer_key, 'ports'}:
                    raise ValueError(f'invalid {direction} rule')
                peers = rule.get(peer_key)
                ports = rule.get('ports')
                if not isinstance(peers, list) or not peers or not isinstance(ports, list) or not ports:
                    raise ValueError(f'{direction} rules require explicit peers and ports')
                for peer in peers:
                    if direction == 'ingress' and peer == controller:
                        continue
                    if isinstance(peer, dict) and set(peer) == {'podSelector'}:
                        selector = peer['podSelector']
                        if (not isinstance(selector, dict) or set(selector) != {'matchLabels'}
                                or not isinstance(selector['matchLabels'], dict)
                                or not isinstance(selector['matchLabels'].get('app.kubernetes.io/name'), str)
                                or not selector['matchLabels']['app.kubernetes.io/name']):
                            raise ValueError('same-namespace ingress requires an explicit application pod selector')
                    elif isinstance(peer, dict) and set(peer) == {'ipBlock'}:
                        block = peer['ipBlock']
                        network = ipaddress.ip_network(block['cidr'], strict=True)
                        if set(block) != {'cidr'} or (direction != 'egress' and network.prefixlen != network.max_prefixlen):
                            raise ValueError('egress ipBlock must name an individual destination (/32 or /128)')
                        if direction != 'egress' and (network.is_unspecified or network.is_multicast or network.is_loopback):
                            raise ValueError('invalid egress destination address')
                    elif isinstance(peer, dict) and set(peer) == {'namespaceSelector', 'podSelector'}:
                        for key in ('namespaceSelector', 'podSelector'):
                            value = peer[key]
                            if not isinstance(value, dict) or set(value) != {'matchLabels'} or not value['matchLabels']:
                                raise ValueError('egress namespace and pod selectors require nonempty matchLabels')
                    else:
                        raise ValueError('egress requires an explicit CIDR ipBlock or namespace-and-pod selectors together')
                for port in ports:
                    if not isinstance(port, dict) or set(port) - {'port', 'protocol'}:
                        raise ValueError('ports require individual numeric ports and protocols')
                    number = port.get('port')
                    protocol = port.get('protocol', 'TCP')
                    if type(number) is not int or not 1 <= number <= 65535 or protocol not in ('TCP', 'UDP', 'SCTP'):
                        raise ValueError('invalid NetworkPolicy port/protocol')
                    allowed[direction].add((number, protocol))
        # Forward-auth's first application port is pod-local. Require the
        # reviewed auth declaration and an explicit loopback bind, rather than
        # adding network ingress to satisfy a containerPort declaration.
        auth_path = path.parent / 'auth-policy.json'
        auth = json.loads(auth_path.read_text()) if auth_path.is_file() else {}
        containers = template['spec'].get('containers', [])
        for index, container in enumerate(containers):
            env = {item.get('name'): item.get('value') for item in container.get('env', [])}
            bind_name = 'CHARTER_APP_BIND' if path.parent.name == 'charter' else 'SLAI_APP_BIND_ADDRESS'
            loopback = (index == 0 and auth.get('enabled') is True and auth.get('mode') == 'forward-auth'
                        and env.get(bind_name) == '127.0.0.1')
            for port_index, port in enumerate(container.get('ports', [])):
                if loopback and port_index == 0:
                    continue
                pair = (port['containerPort'], port.get('protocol', 'TCP'))
                if pair not in allowed['ingress']:
                    raise ValueError(f'ingress must allow container port/protocol {pair}')
        if _has_otel_endpoint(dep_text):
            from urllib.parse import urlsplit
            endpoints = [item.get('value') for container in containers for item in container.get('env', [])
                         if item.get('name') == 'OTEL_EXPORTER_OTLP_ENDPOINT']
            required_ports = []
            for endpoint in endpoints:
                if not isinstance(endpoint, str):
                    raise ValueError('OTEL endpoint requires a literal URL for egress validation')
                parsed = urlsplit(endpoint)
                if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
                    raise ValueError('OTEL endpoint must use HTTP or HTTPS')
                required_ports.append(parsed.port or (443 if parsed.scheme == 'https' else 80))
            if not required_ports or any((port, 'TCP') not in allowed['egress'] for port in required_ports):
                raise ValueError('OTEL endpoint requires explicit destination and its actual TCP port in egress')
        return []
    except _yaml.YAMLError as error:
        return [f"{path}: {_yaml_error_message(error)}"]
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return [f'{path}: {error}']


def _managed_tls_errors(directory):
    path = directory / 'tls-policy.json'
    if not path.exists():
        return []
    try:
        from per_app_tls_inventory import target_from_policy, ingress_filename
        from ingress_policy import bounded_documents
        target = target_from_policy(directory.name, json.loads(read_file_bytes(path)))
        ingress = _bounded_yaml_document(read_file_bytes(directory / ingress_filename(target)).decode())
        if (not isinstance(ingress, dict) or ingress.get('kind') != 'Ingress'
                or ingress.get('metadata', {}).get('name') != target['ingress']
                or not any(t.get('hosts') == [target['hostname']] and t.get('secretName') == target['secret_name']
                           for t in ingress.get('spec', {}).get('tls', []))):
            return ['tls-policy.json must bind the app Ingress to its platform-managed per-app TLS Secret']
        for ciphertext in directory.glob('*.enc.yaml'):
            for doc in bounded_documents(ciphertext):
                if isinstance(doc, dict) and doc.get('kind') == 'Secret' and doc.get('metadata', {}).get('name') == target['secret_name']:
                    return ['App bundles cannot supply or overwrite the platform-managed TLS Secret']
        return []
    except (OSError, ValueError, KeyError, TypeError, AttributeError, _yaml.YAMLError, subprocess.TimeoutExpired):
        return ['Invalid tls-policy.json; update your slai-app-creator plugin']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--strict",
        action="store_true",
        help="Require networkpolicy.yaml and OTEL env (OTEL_EXPORTER_OTLP_ENDPOINT or OTEL_SERVICE_NAME) in deployment.yaml for ALL namespaces (not only default-deny)",
    )
    p.add_argument(
        "manifest_dir",
        type=Path,
        help="Directory deploy/<namespace>/<app_id>/",
    )
    args = p.parse_args()
    d = args.manifest_dir.resolve()

    errors: list[str] = []
    notes: list[str] = []
    if not d.is_dir():
        print(f"error: not a directory: {d}", file=sys.stderr)
        return 2

    namespace = d.parent.name
    is_default_deny_ns = namespace in DEFAULT_DENY_NAMESPACES

    required = ("deployment.yaml", "service.yaml", "secrets.enc.yaml")
    if namespace == "slai-app-prod":
        required += ("z-ingress.yaml",)
    for name in required:
        fp = d / name
        if not fp.is_file():
            errors.append(f"missing file: {fp}")

    # Apply consistency checks to every YAML resource before using directory-
    # selected production requirements. Encrypted multi-document Secrets are
    # checked by their resource-limited worker below.
    for manifest in sorted(set(d.glob("*.yaml")) | set(d.glob("*.yml"))):
        if manifest.name.endswith(".enc.yaml"):
            continue
        text = _manifest_file_text(manifest, errors)
        try:
            loader = bounded_loader(text)
            try:
                while loader.check_data():
                    document = loader.get_data()
                    errors.extend(_namespace_errors(document, manifest, namespace))
                    errors.extend(_bundle_resource_errors(document, manifest, d.name))
            finally:
                loader.dispose()
        except Exception as exc:
            errors.append(f"{manifest}: {_yaml_error_message(exc)}")

    from bundle_resources import local_bundle_errors
    errors.extend(local_bundle_errors(d))
    errors.extend(_managed_tls_errors(d))

    dep = d / "deployment.yaml"
    dep_text = ""
    if dep.is_file():
        dep_text = _manifest_file_text(dep, errors)
        reference_result = _deployment_reference_errors(dep_text, dep)
        if reference_result is None:
            # PyYAML is optional for backward compatibility. Retain the original
            # best-effort text check when it is unavailable.
            if "image:" not in dep_text:
                errors.append(f"{dep}: expected an 'image:' field")
            else:
                m = re.search(r"image:\s*(\S+)", dep_text)
                if m:
                    ref = m.group(1).strip("\"'")
                    if ref.endswith(":latest"):
                        errors.append(
                            f"{dep}: avoid :latest for production-like deploys; "
                            "use immutable tag (e.g. git SHA)"
                        )
        else:
            reference_errors, reference_notes = reference_result
            errors.extend(reference_errors)
            notes.extend(reference_notes)
        errors.extend(_resource_errors(dep_text, dep))
        errors.extend(_shared_ldap_errors_from_yaml(dep_text, dep))
        errors.extend(_app_name_label_errors(dep_text, dep))

    for ciphertext in sorted(d.glob('*.enc.yaml')):
        if ciphertext.is_file():
            errors.extend(ciphertext_errors(ciphertext, namespace, d.name))

    zing = d / "z-ingress.yaml"
    if zing.is_file():
        if namespace == "slai-app-prod":
            errors.extend(_ingress_policy_errors(d))
        # TLS is provisioned by the platform; app bundles only reference it.

    # Always validate Keycloak egress, including unchanged reviewed policies.
    auth_errors, auth_notes = _platform_auth_policy_validation(d)
    errors.extend(auth_errors)
    notes.extend(auth_notes)

    np = d / "networkpolicy.yaml"
    netpol_required = is_default_deny_ns or args.strict
    if netpol_required and not np.is_file():
        reason = (
            f"namespace {namespace!r} runs default-deny — per-app NetworkPolicy is mandatory"
            if is_default_deny_ns
            else "required with --strict"
        )
        errors.append(
            f"missing file: {np} — {reason}. "
            f"See skills/slai-app-creator/references/network-egress.md and "
            f"assets/templates/networkpolicy.yaml.example."
        )

    if dep_text and np.is_file():
        np_text = _manifest_file_text(np, errors)
        from bundle_resources import reviewed_baseline_files
        baseline = reviewed_baseline_files()
        reviewed = baseline.get('deploy/slai-app-prod/' + d.name + '/networkpolicy.yaml')
        if reviewed is None or _bounded_yaml_document(np_text) != _bounded_yaml_document(reviewed):
            errors.extend(_networkpolicy_errors(np_text, dep_text, np))

    if args.strict and dep.is_file():
        t = _manifest_file_text(dep, errors)
        if not re.search(
            r"OTEL_EXPORTER_OTLP_ENDPOINT|OTEL_SERVICE_NAME",
            t,
        ):
            errors.append(
                f"{dep}: with --strict, expected OTEL_EXPORTER_OTLP_ENDPOINT or OTEL_SERVICE_NAME in env (skills/slai-app-creator/references/platform-context.md)"
            )

    if errors:
        print("validation failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    for note in notes:
        print(note)
    print(f"ok: {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
