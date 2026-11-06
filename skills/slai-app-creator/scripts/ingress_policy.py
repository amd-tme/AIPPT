#!/usr/bin/env python3
"""Validate SLAI Ingress routes against the subdomain-only policy."""

import argparse
import json
import subprocess
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

try:
    import yaml
except ImportError as exc:  # pragma: no cover - CI and tests install PyYAML.
    raise SystemExit("PyYAML is required: python3 -m pip install 'PyYAML>=6.0'") from exc


try:
    from .yaml_limits import bounded_loader, read_file_bytes, apply_resource_limits, MAX_DOCUMENTS, MAX_OUTPUT_BYTES, WALL_SECONDS
except ImportError:
    import importlib.util
    _limits_spec = importlib.util.spec_from_file_location("ingress_yaml_limits", Path(__file__).with_name("yaml_limits.py"))
    _limits = importlib.util.module_from_spec(_limits_spec)
    _limits_spec.loader.exec_module(_limits)
    bounded_loader, read_file_bytes, apply_resource_limits = _limits.bounded_loader, _limits.read_file_bytes, _limits.apply_resource_limits
    MAX_DOCUMENTS, MAX_OUTPUT_BYTES, WALL_SECONDS = _limits.MAX_DOCUMENTS, _limits.MAX_OUTPUT_BYTES, _limits.WALL_SECONDS


def bounded_documents(path):
    raw = read_file_bytes(path)
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--yaml-worker'],
                            input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=WALL_SECONDS)
    if result.returncode or len(result.stdout) > MAX_OUTPUT_BYTES:
        category = 'worker failure'
        for marker in (b'SyntaxError', b'ImportError', b'ModuleNotFoundError', b'AttributeError', b'MemoryError'):
            if marker in result.stderr:
                category = marker.decode('ascii')
                break
        if result.returncode < 0:
            category = 'worker signal ' + str(-result.returncode)
        raise ValueError('YAML parsing failed or exceeded resource limits (' + category + '; Python ' + str(sys.version_info[0]) + '.' + str(sys.version_info[1]) + ')')
    documents = json.loads(result.stdout)
    if not isinstance(documents, list) or len(documents) > MAX_DOCUMENTS:
        raise ValueError('invalid bounded YAML result')
    return documents


def yaml_worker():
    apply_resource_limits()
    from yaml_limits import MAX_INPUT_BYTES
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        return 2
    loader = bounded_loader(raw)
    # Existing manifests use small label anchors. Bound alias references while
    # retaining the worker's CPU/memory/output limits on expanded serialization.
    original_compose = loader.compose_node
    alias_count = 0
    def compose(parent, index):
        nonlocal alias_count
        if loader.check_event(yaml.AliasEvent):
            alias_count += 1
            if alias_count > 32:
                raise ValueError('YAML alias limit exceeded')
            return yaml.SafeLoader.compose_node(loader, parent, index)
        return original_compose(parent, index)
    loader.compose_node = compose
    try:
        documents = []
        while loader.check_data():
            if len(documents) >= MAX_DOCUMENTS:
                return 2
            documents.append(loader.get_data())
        output = json.dumps(documents, default=str).encode()
        if len(output) > MAX_OUTPUT_BYTES:
            return 2
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        return 2
    finally:
        loader.dispose()


DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?$")

class Route(NamedTuple):
    app_id: str
    file: str
    host: str
    path: str
    secret_name: str
    path_type: str
    backend: object
    regex_or_rewrite: bool

    def policy_key(self) -> Tuple[str, str, str, str, str]:
        return (self.app_id, self.file, self.host, self.path, self.secret_name)

    def label(self) -> str:
        return f"{self.app_id}/{self.file}: host={self.host!r} path={self.path!r} secret={self.secret_name!r}"


def _mapping(value: object, label: str, errors: List[str]) -> dict:
    if isinstance(value, dict):
        return value
    errors.append(f"{label} must be a mapping")
    return {}


def load_policy(path: Path) -> Tuple[dict, Set[Tuple[str, str, str, str, str]]]:
    loader = bounded_loader(read_file_bytes(path))
    try:
        data = loader.get_single_data()
    finally:
        loader.dispose()
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError(f"{path}: expected policy version 1")
    standard = data.get("standard")
    if not isinstance(standard, dict):
        raise ValueError(f"{path}: standard must be a mapping")
    required = {"host_suffix", "path", "path_type", "tls_secret_name"}
    if set(standard) != required:
        raise ValueError(f"{path}: standard keys must be exactly {sorted(required)}")
    dedicated = data.get("dedicated_tls_secrets", {})
    if not isinstance(dedicated, dict):
        raise ValueError(f"{path}: dedicated_tls_secrets must be a mapping")
    legacy = data.get('legacy_tls_secrets', {})
    if not isinstance(legacy, dict) or any(not isinstance(a, str) or not DNS_LABEL_RE.fullmatch(a)
            or not isinstance(s, str) or not DNS_LABEL_RE.fullmatch(s) for a, s in legacy.items()):
        raise ValueError(f'{path}: invalid frozen legacy TLS bindings')
    for app_id, secret in dedicated.items():
        if (not isinstance(app_id, str) or not DNS_LABEL_RE.fullmatch(app_id)
                or not isinstance(secret, str) or not DNS_LABEL_RE.fullmatch(secret)
                or not secret.startswith(app_id + '-')):
            raise ValueError(f"{path}: dedicated TLS entries require a DNS app_id and app-owned Secret name")
    allowed = set()  # type: Set[Tuple[str, str, str, str, str]]
    for index, item in enumerate(data.get("grandfathered_routes") or [], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: grandfathered_routes item #{index} must be a mapping")
        keys = ("app_id", "file", "host", "path", "secret_name")
        if item.get("path_type") not in {"Exact", "Prefix", "ImplementationSpecific"}:
            raise ValueError(f"{path}: grandfathered route #{index} requires reviewed path_type")
        if set(item) != set(keys) | {"path_type"} or not all(isinstance(item.get(key), str) for key in keys):
            raise ValueError(f"{path}: grandfathered route #{index} must contain string fields {keys}")
        route = tuple(item[key] for key in keys)
        if route in allowed:
            raise ValueError(f"{path}: duplicate grandfathered route #{index}: {route}")
        allowed.add(route)
    legacy_hosts = data.get('legacy_host_tls_secrets', {})
    frozen_hosts = {item[2] for item in allowed}
    app_secret_names = {item[0] + '-tls' for item in allowed}
    if (not isinstance(legacy_hosts, dict)
            or any(not isinstance(host, str) or host not in frozen_hosts or '*' in host
                   or not isinstance(secret, str) or not DNS_LABEL_RE.fullmatch(secret)
                   or secret in app_secret_names
                   for host, secret in legacy_hosts.items())):
        raise ValueError(f'{path}: exact-host TLS transitions must name frozen legacy hosts and valid Secrets')
    return data, allowed


# Reviewed route transformations are frozen by application and manifest identity.
LEGACY_TRANSFORMS = {
    ("aippt", "z-ingress.yaml"): {"rewrite-target": "/$2"},
    ("ldap-oauth", "z-ingress.yaml"): {"rewrite-target": "/$2"},
    ("dcgpu-hub", "z-ingress.yaml"): {"permanent-redirect": "https://dcgpu-hub.amd.com/"},
    ("gce-hub", "z-ingress.yaml"): {"permanent-redirect": "https://gce-hub.amd.com/"},
    ("rocm-ai", "z-ingress-apex-redirect.yaml"): {"permanent-redirect": "https://rocm-ai.slai-app.amd.com/"},
}


def ingress_document_errors(document, app_id, filename):
    errors = []
    metadata = document.get("metadata") or {}
    spec = document.get("spec") or {}
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        return [f"{filename}: Ingress metadata and spec must be mappings"]
    annotations = metadata.get("annotations") or {}
    if not isinstance(annotations, dict):
        return [f"{filename}: annotations must be a mapping"]
    if spec.get("ingressClassName", "nginx") != "nginx":
        errors.append(f"{filename}: Ingress must use nginx")
    if "defaultBackend" in spec:
        errors.append(f"{filename}: defaultBackend is forbidden")
    transforms = LEGACY_TRANSFORMS.get((app_id, filename), {})
    tls_tuple = {"backend-protocol": "HTTPS", "proxy-ssl-verify": "on", "proxy-ssl-server-name": "on", "proxy-ssl-name": app_id + ".slai-app.amd.com", "proxy-ssl-secret": "slai-app-prod/" + app_id + "-ingress-trust"}
    tls_prefix = "nginx.ingress.kubernetes.io/"
    has_upstream_tls = any(tls_prefix + key in annotations for key in tls_tuple)
    valid_upstream_tls = all(annotations.get(tls_prefix + key) == value for key, value in tls_tuple.items())
    if has_upstream_tls and not valid_upstream_tls:
        errors.append(f"{filename}: upstream TLS requires the complete verified app-owned HTTPS tuple")
    prefix = "nginx.ingress.kubernetes.io/"
    for key, value in annotations.items():
        suffix = key[len(prefix):] if isinstance(key, str) and key.startswith(prefix) else None
        allowed = False
        if key == "kubernetes.io/ingress.class":
            allowed = value == "nginx"
        elif isinstance(value, str):
            if suffix in {"proxy-read-timeout", "proxy-send-timeout"}:
                allowed = bool(re.fullmatch(r"[1-9][0-9]{0,3}", value)) and int(value) <= 3600
            elif suffix == "proxy-body-size":
                allowed = bool(re.fullmatch(r"[1-9][0-9]{0,2}[mM]", value)) and int(value[:-1]) <= 128
            elif suffix == "enable-access-log":
                allowed = value in {"true", "false"}
            elif suffix == "proxy-buffering":
                allowed = value in {"on", "off"}
            elif suffix in {"ssl-redirect", "force-ssl-redirect"}:
                allowed = value == "true"
            elif suffix in tls_tuple:
                allowed = valid_upstream_tls
            elif suffix in transforms:
                allowed = value == transforms[suffix]
        if not allowed:
            errors.append(f"{filename}: unsupported or unsafe Ingress annotation {key!r}")
    return errors


def collect_routes(manifest_dir: Path, supplied_documents=None) -> Tuple[List[Route], List[str]]:
    errors = []  # type: List[str]
    routes = []  # type: List[Route]
    app_id = manifest_dir.name
    files = sorted((*manifest_dir.glob("*.yaml"), *manifest_dir.glob("*.yml"))) if supplied_documents is None else [manifest_dir / name for name in supplied_documents]
    if not files:
        return [], [f"{manifest_dir}: missing Ingress manifests"]
    for path in files:
        try:
            documents = bounded_documents(path) if supplied_documents is None else supplied_documents[path.name]
        except Exception as exc:
            errors.append(f"{path}: invalid YAML: {exc}")
            continue
        for doc_index, document in enumerate(documents, start=1):
            if document is None:
                continue
            if not isinstance(document, dict):
                errors.append(f"{path} document #{doc_index}: expected a mapping")
                continue
            if document.get("kind") != "Ingress":
                continue
            errors.extend(ingress_document_errors(document, app_id, path.name))
            metadata = document.get("metadata") or {}
            annotations = (metadata.get("annotations") or {}) if isinstance(metadata, dict) else {}
            regex_or_rewrite = isinstance(annotations, dict) and any(
                key in annotations for key in (
                    "nginx.ingress.kubernetes.io/use-regex",
                    "nginx.ingress.kubernetes.io/rewrite-target",
                )
            )
            spec = _mapping(document.get("spec"), f"{path} document #{doc_index} spec", errors)
            rules = spec.get("rules")
            tls_entries = spec.get("tls")
            if not isinstance(rules, list) or not rules:
                errors.append(f"{path} document #{doc_index}: spec.rules must be a non-empty list")
                continue
            if not isinstance(tls_entries, list) or not tls_entries:
                errors.append(f"{path} document #{doc_index}: spec.tls must be a non-empty list")
                continue
            tls_by_host = {}  # type: Dict[str, List[str]]
            for tls_index, tls_item in enumerate(tls_entries, start=1):
                tls_item = _mapping(tls_item, f"{path} spec.tls item #{tls_index}", errors)
                hosts = tls_item.get("hosts")
                secret = tls_item.get("secretName")
                if not isinstance(hosts, list) or not hosts or not isinstance(secret, str) or not secret:
                    errors.append(f"{path} spec.tls item #{tls_index}: hosts and secretName are required")
                    continue
                for host in hosts:
                    if not isinstance(host, str) or not host:
                        errors.append(f"{path} spec.tls item #{tls_index}: hosts must contain strings")
                        continue
                    tls_by_host.setdefault(host, []).append(secret)
            rule_hosts = set()  # type: Set[str]
            for rule_index, rule in enumerate(rules, start=1):
                rule = _mapping(rule, f"{path} spec.rules item #{rule_index}", errors)
                host = rule.get("host")
                if not isinstance(host, str) or not host:
                    errors.append(f"{path} spec.rules item #{rule_index}: host is required")
                    continue
                rule_hosts.add(host)
                secrets = tls_by_host.get(host, [])
                if len(secrets) != 1:
                    errors.append(f"{path}: host {host!r} must map to exactly one TLS secret (got {secrets})")
                    continue
                http = _mapping(rule.get("http"), f"{path} rule {host!r} http", errors)
                paths = http.get("paths")
                if not isinstance(paths, list) or not paths:
                    errors.append(f"{path}: host {host!r} must have at least one HTTP path")
                    continue
                for path_index, path_item in enumerate(paths, start=1):
                    path_item = _mapping(path_item, f"{path} host {host!r} path #{path_index}", errors)
                    route_path = path_item.get("path")
                    path_type = path_item.get("pathType")
                    if not isinstance(route_path, str) or not isinstance(path_type, str):
                        errors.append(f"{path}: host {host!r} paths require string path and pathType")
                        continue
                    routes.append(Route(app_id, path.name, host, route_path, secrets[0], path_type,
                                        path_item.get("backend"), regex_or_rewrite))
            extra_tls_hosts = set(tls_by_host) - rule_hosts
            if extra_tls_hosts:
                errors.append(f"{path}: TLS hosts without matching rules: {sorted(extra_tls_hosts)}")
    if not routes and not errors:
        errors.append(f"{manifest_dir}: no Ingress resources found in manifest bundle")
    return routes, errors


def managed_tls_target(directory, supplied_documents=None, supplied_tls_policy=None):
    """A validated descriptor opts an existing canonical app into dedicated TLS."""
    raw = supplied_tls_policy
    if supplied_documents is None and (directory / 'tls-policy.json').exists():
        raw = read_file_bytes(directory / 'tls-policy.json')
    if raw is None:
        return None
    if not isinstance(raw, (str, bytes)) or len(raw) > 4096:
        raise ValueError('invalid TLS enrollment size')
    try:
        from .per_app_tls_inventory import target_from_policy, ingress_filename
    except ImportError:
        from per_app_tls_inventory import target_from_policy, ingress_filename
    target = target_from_policy(directory.name, json.loads(raw))
    filename = ingress_filename(target)
    documents = (bounded_documents(directory / filename) if supplied_documents is None
                 else supplied_documents.get(filename, []))
    matches = [doc for doc in documents if isinstance(doc, dict) and doc.get('kind') == 'Ingress'
               and doc.get('metadata', {}).get('name') == target['ingress']
               and doc.get('metadata', {}).get('namespace') == target['namespace']]
    if len(matches) != 1 or not any(t.get('hosts') == [target['hostname']] and t.get('secretName') == target['secret_name']
                                   for t in matches[0].get('spec', {}).get('tls', [])):
        raise ValueError('TLS enrollment must bind the canonical app Ingress and dedicated Secret')
    return target


def validate_tree(root: Path, policy_path: Path, only_dir: Optional[Path] = None, supplied_documents=None, allocated_app_ids=None, supplied_tls_policy=None) -> List[str]:
    policy, grandfathered = load_policy(policy_path)
    if allocated_app_ids is None:
        allocation_root = root / 'deploy' / str(policy.get('namespace'))
        allocated_app_ids = {path.name for path in allocation_root.iterdir() if path.is_dir()}
    else:
        allocated_app_ids = set(allocated_app_ids)
    reviewed_path_types = {tuple(item[k] for k in ("app_id", "file", "host", "path", "secret_name")): item["path_type"] for item in policy.get("grandfathered_routes", [])}
    namespace = policy.get("namespace")
    standard = policy["standard"]
    namespace_dir = root / "deploy" / str(namespace)
    dirs = [only_dir.resolve()] if only_dir else sorted(path for path in namespace_dir.iterdir() if path.is_dir())
    errors = []  # type: List[str]
    observed = set()  # type: Set[Tuple[str, str, str, str, str]]
    for manifest_dir in dirs:
        try:
            managed = managed_tls_target(manifest_dir, supplied_documents, supplied_tls_policy)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            errors.append(f'{manifest_dir.name}: invalid platform-managed TLS enrollment')
            managed = None
        routes, route_errors = collect_routes(manifest_dir, supplied_documents)
        errors.extend(route_errors)
        standard_routes = []
        seen_routes = set()
        for route in routes:
            key = route.policy_key()
            if managed and route.host == managed['hostname'] and route.secret_name != managed['secret_name']:
                errors.append(f'{route.label()}: managed app routes must use TLS Secret {managed["secret_name"]!r}')
            identity = (route.host, route.path)
            if identity in seen_routes:
                errors.append(f"{route.label()}: duplicate application route")
            seen_routes.add(identity)
            # Permit only a TLS-reference transition for an already reviewed
            # apex route; preserve its original identity for stale detection.
            if route.host == 'slai-app.amd.com' and route.secret_name == 'slai-app-wildcard-tls':
                legacy_key = (*key[:4], 'slai-app-amd-com-tls')
                if legacy_key in grandfathered:
                    key = legacy_key
            # Preserve reviewed extra canonical routes (for example CIMD) while
            # changing only their TLS binding. Host/path/pathType/backend rules
            # remain reviewed, and a shared apex is never implicitly migrated.
            if managed and route.host == managed['hostname'] and route.secret_name == managed['secret_name']:
                prior = [item for item in grandfathered if item[:4] == key[:4]]
                if len(prior) == 1:
                    key = prior[0]
            # An exact-host platform certificate may replace the shared legacy
            # certificate only on an already frozen route. It grants no ability
            # to add apex paths, change URLs, or select another app's backend.
            if route.secret_name == policy.get('legacy_host_tls_secrets', {}).get(route.host):
                prior = [item for item in grandfathered if item[:4] == key[:4]]
                if len(prior) == 1:
                    key = prior[0]

            backend = route.backend
            valid = isinstance(backend, dict) and set(backend) == {'service'}
            service = backend.get('service') if valid else None
            valid = valid and isinstance(service, dict) and set(service) == {'name', 'port'}
            name = service.get('name') if valid else None
            valid = valid and isinstance(name, str) and bool(DNS_LABEL_RE.fullmatch(name))
            valid = valid and (name == route.app_id or name.startswith(route.app_id + '-') or name == 'hosted-slai-' + route.app_id or key in grandfathered and name == route.app_id.replace('_', '-'))
            valid = valid and not any(other != route.app_id and other.startswith(route.app_id + '-') and (name == other or name.startswith(other + '-')) for other in allocated_app_ids)
            port = service.get('port') if isinstance(service, dict) else None
            valid_port = isinstance(port, dict) and len(port) == 1 and (
                set(port) == {'number'} and type(port['number']) is int and 1 <= port['number'] <= 65535
                or set(port) == {'name'} and isinstance(port['name'], str) and 1 <= len(port['name']) <= 15
                and bool(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?', port['name'])) and bool(re.search('[a-z]', port['name'])))
            if not valid or not valid_port:
                errors.append(f'{route.label()}: backend must use an application-owned Service and valid named or numeric port')
            if key in grandfathered:
                if route.path_type != reviewed_path_types[key]:
                    errors.append(f"{route.label()}: grandfathered route requires reviewed pathType {reviewed_path_types[key]!r}")
                observed.add(key)
                continue
            if route.app_id == "platform-sso-keycloak":
                errors.append(f"{route.label()}: Keycloak Ingress requires an explicitly reviewed route")
                continue
            expected_host = f"{route.app_id}.{standard['host_suffix']}"
            if not DNS_LABEL_RE.fullmatch(route.app_id):
                errors.append(f"{route.label()}: new app_id must be a DNS-1123 label")
            if route.host != expected_host:
                errors.append(f"{route.label()}: new routes must use host {expected_host!r}")
            if "*" in route.host:
                errors.append(f"{route.label()}: Ingress rules must use a concrete host, never a wildcard")
            standard_routes.append(route)
            if not route.path.startswith("/"):
                errors.append(f"{route.label()}: Ingress path must start with '/'")
            if route.path_type not in {"Exact", "Prefix", "ImplementationSpecific"}:
                errors.append(f"{route.label()}: invalid Ingress pathType {route.path_type!r}")
            expected_secret = policy.get("dedicated_tls_secrets", {}).get(route.app_id,
                policy.get('legacy_tls_secrets', {}).get(route.app_id, standard['tls_secret_name'].replace('{app_id}', route.app_id)))
            if managed:
                expected_secret = managed['secret_name']
            if route.secret_name != expected_secret:
                ownership = 'platform-managed per-app' if '{app_id}' in standard['tls_secret_name'] and route.app_id not in policy.get('legacy_tls_secrets', {}) else 'reviewed'
                errors.append(f"{route.label()}: new routes must use {ownership} TLS Secret {expected_secret!r}")
        if standard_routes and not any(
            route.host == f"{route.app_id}.{standard['host_suffix']}"
            and route.path == standard["path"]
            and route.path_type == standard["path_type"]
            for route in routes
        ):
            errors.append(
                f"{manifest_dir.name}: new apps require a root route with path "
                f"{standard['path']!r} and pathType {standard['path_type']!r}"
            )
    relevant_grandfathered = grandfathered
    if only_dir:
        relevant_grandfathered = {item for item in grandfathered if item[0] == only_dir.name}
    stale = relevant_grandfathered - observed
    for item in sorted(stale):
        errors.append(f"grandfathered route is missing or changed; update requires platform-infra review: {item}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument("--policy", type=Path, default=Path("config/ingress-policy.yaml"))
    parser.add_argument("--manifest-dir", type=Path, help="Validate one app directory")
    args = parser.parse_args()
    root = args.root.resolve()
    policy_path = args.policy if args.policy.is_absolute() else root / args.policy
    manifest_dir = args.manifest_dir.resolve() if args.manifest_dir else None
    try:
        errors = validate_tree(root, policy_path, manifest_dir)
    except (OSError, ValueError) as exc:
        print(f"ingress policy configuration error: {exc}", file=sys.stderr)
        return 2
    if errors:
        print("ingress policy validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"ok: ingress policy ({manifest_dir or root / 'deploy' / 'slai-app-prod'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(yaml_worker() if sys.argv[1:] == ["--yaml-worker"] else main())
