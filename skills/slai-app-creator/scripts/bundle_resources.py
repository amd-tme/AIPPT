"""App-scoped manifest discovery and validation for additional workloads."""
import ipaddress
import os
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

try:
    from .image_release_evidence import EVIDENCE_FILES, evidence_errors
    from .yaml_limits import bounded_loader, YamlLimitError, MAX_DOCUMENTS, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, WALL_SECONDS, apply_resource_limits, read_file_bytes
except ImportError:
    from image_release_evidence import EVIDENCE_FILES, evidence_errors
    from yaml_limits import bounded_loader, YamlLimitError, MAX_DOCUMENTS, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, WALL_SECONDS, apply_resource_limits, read_file_bytes
import yaml

MANIFEST_NAME = re.compile(r'^[a-z0-9][a-z0-9-]*\.ya?ml$')
KINDS = {'Deployment', 'StatefulSet', 'DaemonSet', 'Job', 'CronJob', 'Service', 'Ingress', 'NetworkPolicy', 'ConfigMap', 'PersistentVolumeClaim', 'ServiceAccount', 'Role', 'RoleBinding'}


def service_spec_errors(spec):
    """Support app Services through ClusterIP or platform-managed LoadBalancer."""
    if not isinstance(spec, dict):
        return ['Service spec must be a mapping']
    errors = []
    if spec.get('loadBalancerIP') and spec.get('type') != 'LoadBalancer':
        errors.append('Service loadBalancerIP requires type LoadBalancer')
    if spec.get('type', 'ClusterIP') not in ('ClusterIP', 'LoadBalancer'):
        errors.append('Service type must be ClusterIP or LoadBalancer')
    if spec.get('externalIPs') or spec.get('externalName'):
        errors.append('Service externalIPs and externalName are forbidden')
    if spec.get('loadBalancerIP'):
        try:
            ipaddress.ip_address(spec['loadBalancerIP'])
        except (ValueError, TypeError):
            errors.append('Service loadBalancerIP must be an IP address')
    ports = spec.get('ports')
    if not isinstance(ports, list) or not ports:
        return errors + ['Service ports must be a nonempty list of mappings']
    names, sockets = set(), set()
    for port in ports:
        if not isinstance(port, dict):
            errors.append('Service ports must be mappings')
            continue
        number = port.get('port')
        target = port.get('targetPort', number)
        protocol = port.get('protocol', 'TCP')
        name = port.get('name')
        valid_name = lambda value: isinstance(value, str) and 1 <= len(value) <= 15 and bool(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?', value)) and bool(re.search('[a-z]', value))
        if type(number) is not int or not 1 <= number <= 65535 or protocol not in ('TCP', 'UDP', 'SCTP'):
            errors.append('Service port must be 1-65535 with TCP, UDP or SCTP protocol')
        if not (type(target) is int and 1 <= target <= 65535 or valid_name(target)):
            errors.append('Service targetPort must be a valid port number or name')
        if (name is not None and not valid_name(name)) or len(ports) > 1 and name is None:
            errors.append('Service ports require valid names when multiple ports are declared')
        if name is not None:
            if str(name) in names: errors.append('Service port names must be unique')
            names.add(str(name))
        socket = (str(number), str(protocol))
        if socket in sockets: errors.append('Service ports must be unique')
        sockets.add(socket)
        if 'nodePort' in port:
            errors.append('Service nodePort must be allocated by the platform, not explicitly assigned')
    return errors


def accepted_file(name, fixed):
    return name in fixed or bool(MANIFEST_NAME.fullmatch(name)) or bool(re.fullmatch(r'[a-z0-9][a-z0-9-]*\.enc\.yaml', name))


def network_policy_errors(spec):
    """Apply the canonical explicit-peer and individual-port network contract."""
    errors = []
    controller = {
        'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
        'podSelector': {'matchLabels': {
            'app.kubernetes.io/component': 'controller',
            'app.kubernetes.io/instance': 'rke2-ingress-nginx',
            'app.kubernetes.io/name': 'rke2-ingress-nginx'}},
    }
    try:
        if set(spec.get('policyTypes', [])) != {'Ingress', 'Egress'}:
            raise ValueError('policyTypes must include Ingress and Egress')
        selector = spec['podSelector']
        if selector.get('matchExpressions'):
            raise ValueError('podSelector matchExpressions are forbidden')
        for direction, peer_key in (('ingress', 'from'), ('egress', 'to')):
            rules = spec.get(direction, [])
            if not isinstance(rules, list):
                raise ValueError(f'{direction} must be a list')
            for rule in rules:
                if not isinstance(rule, dict) or set(rule) - {peer_key, 'ports'}:
                    raise ValueError(f'invalid {direction} rule')
                peers, ports = rule.get(peer_key), rule.get('ports')
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
                            raise ValueError('same-namespace traffic requires an explicit application pod selector')
                    elif isinstance(peer, dict) and set(peer) == {'ipBlock'}:
                        block = peer['ipBlock']
                        network = ipaddress.ip_network(block['cidr'], strict=True)
                        if set(block) != {'cidr'} or (direction != 'egress' and (network.prefixlen != network.max_prefixlen or network.is_unspecified or network.is_multicast or network.is_loopback)):
                            raise ValueError('egress requires an individual destination (/32 or /128)')
                    elif isinstance(peer, dict) and set(peer) == {'namespaceSelector', 'podSelector'}:
                        for key in ('namespaceSelector', 'podSelector'):
                            value = peer[key]
                            if not isinstance(value, dict) or set(value) != {'matchLabels'} or not isinstance(value['matchLabels'], dict) or not value['matchLabels']:
                                raise ValueError('egress selectors require nonempty matchLabels')
                    else:
                        raise ValueError('egress requires an explicit CIDR ipBlock or namespace-and-pod selectors together')
                for port in ports:
                    if not isinstance(port, dict) or set(port) - {'port', 'protocol'} or type(port.get('port')) is not int or not 1 <= port['port'] <= 65535 or port.get('protocol', 'TCP') not in ('TCP', 'UDP', 'SCTP'):
                        raise ValueError('ports require individual numeric ports and protocols')
    except (ValueError, TypeError, KeyError, AttributeError):
        errors.append('NetworkPolicy must use canonical explicit peers and individual ports')
    return errors


def pvc_spec_errors(spec):
    """Require newly provisioned storage for standalone and embedded claims."""
    if not isinstance(spec, dict):
        return ['PVC spec must be a mapping']
    if spec.get('storageClassName') != 'nfs-network' or any(k in spec for k in ('volumeName', 'selector', 'dataSource', 'dataSourceRef')):
        return ['PVC must provision new nfs-network storage without volume selection or data sources']
    return []


def reviewed_baseline_files():
    """Load bounded service-owned baseline context, never submission files."""
    path = os.environ.get('SLAI_REVIEWED_BASELINE_PATH')
    if not path:
        return {}
    raw = read_file_bytes(Path(path))
    result = json.loads(raw)
    if not isinstance(result, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in result.items()):
        raise ValueError('invalid reviewed baseline context')
    return result


def local_bundle_errors(directory):
    """Read the complete bounded local bundle, retaining its image receipt."""
    fixed = {'service-cimd.yaml', 'z-ingress-cimd.yaml', 'deployment.yaml', 'service.yaml', 'z-ingress.yaml', 'networkpolicy.yaml',
             'secrets.enc.yaml', 'tls-secret.enc.yaml', 'image-policy.yaml',
             'cli-auth-policy.yaml', 'auth-policy.json', 'image-release.json',
             'image-release.bundle.jsonl', 'tls-policy.json'}
    try:
        paths = []
        for path in directory.iterdir():
            if len(paths) >= 100:
                return ['bundle exceeds 100 entries']
            paths.append(path)
        if directory.name == 'charter':
            fixed.add('tls-secret-consumer-platforms.enc.yaml')
        additional = any(p.name not in fixed and p.suffix in ('.yaml', '.yml') and not p.name.endswith('.enc.yaml') for p in paths)
        approved = json.loads(os.environ.get('SLAI_BASELINE_APPROVED_IMAGES', '[]'))
        errors = evidence_errors([p.name for p in paths], approved, directory.parent.name == 'slai-app-prod')
        if errors:
            if not any(p.name in EVIDENCE_FILES for p in paths):
                inventory = Path(__file__).resolve().parents[1] / 'assets/tls-cutover.json'
                if not inventory.is_file():
                    inventory = Path(__file__).with_name('tls-cutover.json')
                if directory.name in json.loads(inventory.read_text())['legacy_apps']:
                    errors.append('Submit this legacy bundle for hosted validation of every workload image against its reviewed baseline.')
            return errors
        if not additional:
            return []
        files, total = [], 0
        for path in paths:
            if path.name not in fixed and path.suffix not in ('.yaml', '.yml'):
                continue
            raw = read_file_bytes(path)
            total += len(raw)
            if total > 5 * 1024 * 1024:
                return ['bundle exceeds 5 MiB']
            files.append(SimpleNamespace(path=str(path), content=raw.decode('utf-8')))
        allocations = [p.name for p in directory.parent.iterdir() if p.is_dir()]
        return resource_errors(files, directory.name, allocations, approved, baseline_files=reviewed_baseline_files())
    except (OSError, ValueError, TypeError):
        return ['cannot securely read complete multi-workload bundle']


def resource_errors(files, app_id, allocated_app_ids=None, approved_images=None, ingress_files=None, baseline_files=None):
    """Validate in a separate process with bounded input, memory, CPU, and wall time."""
    payload = json.dumps({'baseline_files': baseline_files or {}, 'app_id': app_id, 'allocated_app_ids': list(allocated_app_ids or []), 'approved_images': list(approved_images or []), 'ingress_files': [{'path': f.path, 'content': f.content} for f in ingress_files] if ingress_files is not None else None, 'files': [{'path': f.path, 'content': f.content} for f in files]}).encode()
    if len(payload) > MAX_OUTPUT_BYTES:
        return ['multi-resource bundle exceeds validation input limit']
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker'],
                                input=payload, capture_output=True, timeout=WALL_SECONDS)
        if result.returncode or len(result.stdout) > MAX_OUTPUT_BYTES:
            return ['multi-resource validation worker failed']
        errors = json.loads(result.stdout)
        if not isinstance(errors, list) or any(not isinstance(e, str) for e in errors):
            return ['invalid multi-resource validation result']
        return errors
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return ['multi-resource validation failed or exceeded time limit']


def _resource_errors(files, app_id, allocated_app_ids=None, approved_images=None, ingress_files=None, baseline_files=None):
    approved_images = set(approved_images or [])
    other_apps = set(allocated_app_ids or []) - {app_id}
    def owned(value):
        return (isinstance(value, str) and (value == app_id or value.startswith(app_id + '-'))
                and not any(value == other or value.startswith(other + '-') for other in other_apps
                            if other.startswith(app_id + '-')))
    # Only immutable platform-base content can establish reviewed compatibility.
    baseline = {}
    for path, content in (baseline_files or {}).items():
        if path.startswith('deploy/slai-app-prod/' + app_id + '/') and path.endswith(('.yaml', '.yml')) and not path.endswith('.enc.yaml'):
            loader = bounded_loader(content)
            documents = []
            try:
                while loader.check_data(): documents.append(loader.get_data())
            finally:
                loader.dispose()
            for doc in documents:
                if isinstance(doc, dict):
                    baseline[(path.rsplit('/', 1)[-1], doc.get('kind'), doc.get('metadata', {}).get('name'))] = doc
    errors, identities, workloads = [], set(), []
    ingress_documents = {}
    release = next((f for f in files if f.path.endswith('/image-release.json')), None)
    authorized = None
    if release:
        try:
            record = json.loads(release.content)
            authorized = record['repository'] + '@' + record['digest']
        except (ValueError, KeyError, TypeError):
            errors.append('invalid image release record')
    for file in files:
        name = file.path.rsplit('/', 1)[-1]
        if not name.endswith(('.yaml', '.yml')) or name.endswith('.enc.yaml') or name in {'image-policy.yaml', 'cli-auth-policy.yaml'}:
            continue
        try:
            if len(file.content.encode('utf-8')) > MAX_INPUT_BYTES:
                raise YamlLimitError('manifest exceeds input limit')
            loader = bounded_loader(file.content)
            try:
                documents = []
                while loader.check_data():
                    if len(documents) >= MAX_DOCUMENTS:
                        raise YamlLimitError('too many YAML documents')
                    documents.append(loader.get_data())
            finally:
                loader.dispose()
        except (yaml.YAMLError, YamlLimitError, RecursionError):
            errors.append(f'{name}: invalid YAML')
            continue
        for doc in documents:
            if not isinstance(doc, dict) or doc.get('kind') not in KINDS:
                errors.append(f'{name}: unsupported resource kind')
                continue
            metadata = doc.get('metadata', {})
            resource = metadata.get('name', '')
            reviewed_legacy = (doc['kind'] == 'Deployment' and resource == 'hosted-slai-' + app_id
                               and baseline.get((name, doc['kind'], resource), {}).get('metadata', {}).get('namespace') == 'slai-app-prod')
            if metadata.get('namespace') != 'slai-app-prod' or not (reviewed_legacy or owned(resource) or doc['kind'] == 'Ingress' and (resource == 'hosted-slai-' + app_id or app_id == 'charter' and name == 'z-ingress-cimd.yaml' and resource == 'hosted-slai-charter-cimd')):
                errors.append(f'{name}: resource must belong to the app and target namespace')
            reviewed = baseline.get((name, doc['kind'], resource), {})
            identity = (doc['kind'], resource)
            if identity in identities:
                errors.append(f'{name}: duplicate resource identity')
            identities.add(identity)
            def check_references(value, ancestry=()):
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key in {'secretKeyRef', 'secretRef', 'secret', 'nodePublishSecretRef'}:
                            field = 'name' if key != 'secret' or ancestry[-2:] == ('projected', 'sources') else 'secretName'
                            ref = child.get(field) if isinstance(child, dict) else None
                            if isinstance(child, dict) and ('secretName' if field == 'name' else 'name') in child:
                                errors.append(f'{name}: Secret reference contains an unsupported identity field')
                            if ref == app_id + '-tls':
                                errors.append(f'{name}: platform-managed TLS private keys cannot enter application pods')
                            if ref == app_id + '-harbor-pull':
                                errors.append(f'{name}: harbor-pull Secret is restricted to imagePullSecrets')
                            reviewed_pod = reviewed.get('spec', {}).get('template', {}).get('spec', {})
                            reviewed_tls = (key == 'secret' and ref == 'slai-app-wildcard-tls'
                                            and any(v.get('secret') == child for v in reviewed_pod.get('volumes', []) if isinstance(v, dict)))
                            if not reviewed_tls and (not isinstance(ref, str) or not owned(ref)):
                                errors.append(f'{name}: environment and volume Secrets must be application-owned')
                        elif key in {'configMap', 'configMapKeyRef', 'configMapRef', 'persistentVolumeClaim'}:
                            ref = child.get('name', child.get('claimName')) if isinstance(child, dict) else None
                            if not isinstance(ref, str) or not owned(ref):
                                errors.append(f'{name}: ConfigMap and PVC references must be application-owned')
                        elif key == 'imagePullSecrets':
                            if not isinstance(child, list) or any(not isinstance(item, dict) or item.get('name') != app_id + '-harbor-pull' or not owned(item.get('name')) for item in child):
                                errors.append(f'{name}: imagePullSecrets must use the application-owned harbor-pull Secret')
                        check_references(child, ancestry + (key,))
                elif isinstance(value, list):
                    for child in value:
                        check_references(child, ancestry)
            check_references(doc)
            spec = doc.get('spec', {})
            if doc['kind'] in {'Deployment', 'StatefulSet', 'DaemonSet', 'Job', 'CronJob'}:
                if doc['kind'] == 'CronJob':
                    spec = spec.get('jobTemplate', {}).get('spec', {})
                if doc['kind'] in {'Deployment', 'StatefulSet', 'DaemonSet'} and not owned(spec.get('selector', {}).get('matchLabels', {}).get('app.kubernetes.io/name')):
                    errors.append(f'{name}: workload selector must belong to the app')
                if doc['kind'] == 'StatefulSet':
                    claims = spec.get('volumeClaimTemplates', [])
                    if not isinstance(claims, list):
                        errors.append(f'{name}: volumeClaimTemplates must be a list')
                    else:
                        for claim in claims:
                            if not isinstance(claim, dict):
                                errors.append(f'{name}: claim template must be a mapping')
                                continue
                            metadata = claim.get('metadata', {})
                            if not isinstance(metadata, dict) or not owned(metadata.get('name')) or metadata.get('namespace', 'slai-app-prod') != 'slai-app-prod':
                                errors.append(f'{name}: claim template must belong to the app and target namespace')
                            errors.extend(f'{name}: {error}' for error in pvc_spec_errors(claim.get('spec')))
                template = spec.get('template', {})
                pod = template.get('spec', {})
                if not owned(template.get('metadata', {}).get('labels', {}).get('app.kubernetes.io/name')):
                    errors.append(f'{name}: workload labels must belong to the app')
                workloads.append((name, pod))
                for container in pod.get('containers', []) + pod.get('initContainers', []):
                    image = container.get('image', '')
                    if image not in approved_images and not re.fullmatch(r'mkmhub\.amd\.com/hw-slaiapp-dev/[a-z0-9._/-]+@sha256:[0-9a-f]{64}', image):
                        errors.append(f'{name}: every workload image must be digest-pinned in approved Harbor')
                    if authorized and image != authorized and image not in approved_images:
                        errors.append(f'{name}: workload image is not covered by the release receipt or reviewed baseline')
                if not pod.get('containers'):
                    errors.append(f'{name}: workload must contain containers')
                reviewed_spec = reviewed.get('spec', {})
                if doc['kind'] == 'CronJob': reviewed_spec = reviewed_spec.get('jobTemplate', {}).get('spec', {})
                reviewed_pod = reviewed_spec.get('template', {}).get('spec', {})
                access_keys = ('automountServiceAccountToken', 'serviceAccountName', 'serviceAccount')
                reviewed_access = bool(reviewed) and (pod.get('serviceAccountName', 'default') == 'default' or owned(pod.get('serviceAccountName'))) and all(pod.get(k) == reviewed_pod.get(k) for k in access_keys) and pod.get('volumes', []) == reviewed_pod.get('volumes', [])
                if not reviewed_access and (pod.get('automountServiceAccountToken') is not False or pod.get('serviceAccountName', 'default') != 'default' or pod.get('serviceAccount', 'default') != 'default'):
                    errors.append(f'{name}: workload service-account access is forbidden')
                if 'ephemeralContainers' in pod:
                    errors.append(f'{name}: ephemeral containers are forbidden in workload templates')
                pod_context = pod.get('securityContext', {})
                if pod_context.get('sysctls'):
                    errors.append(f'{name}: pod sysctls are forbidden')
                if pod.get('hostNetwork') or pod.get('hostPID') or pod.get('hostIPC'):
                    errors.append(f'{name}: host namespaces are forbidden')
                for container in pod.get('containers', []) + pod.get('initContainers', []):
                    context = container.get('securityContext', {})
                    if context.get('procMount', 'Default') != 'Default':
                        errors.append(f'{name}: containers must use Default procMount')
                    if context.get('privileged') or context.get('allowPrivilegeEscalation') is not False or context.get('runAsNonRoot', pod_context.get('runAsNonRoot')) is not True or context.get('runAsUser', pod_context.get('runAsUser')) == 0 or context.get('capabilities', {}).get('drop') != ['ALL']:
                        errors.append(f'{name}: containers must disable privilege escalation')
                    capabilities = context.get('capabilities', {})
                    if not isinstance(capabilities, dict) or capabilities.get('add', []):
                        errors.append(f'{name}: containers must not add Linux capabilities')
                    seccomp = context.get('seccompProfile', pod_context.get('seccompProfile', {}))
                    if not isinstance(seccomp, dict) or seccomp.get('type') != 'RuntimeDefault':
                        errors.append(f'{name}: containers must use RuntimeDefault seccomp')
                for container in pod.get('containers', []) + pod.get('initContainers', []):
                    if any(port.get('hostPort') for port in container.get('ports', [])):
                        errors.append(f'{name}: hostPort is forbidden')
                for volume in pod.get('volumes', []):
                    if not reviewed_access and set(volume) - {'name', 'secret', 'configMap', 'emptyDir', 'persistentVolumeClaim', 'downwardAPI'}:
                        errors.append(f'{name}: hostPath is forbidden')
            if doc['kind'] in {'Service', 'NetworkPolicy'}:
                selector = spec.get('selector', {}) if doc['kind'] == 'Service' else spec.get('podSelector', {}).get('matchLabels', {})
                if not owned(selector.get('app.kubernetes.io/name')):
                    errors.append(f'{name}: selector must belong to the app')
            if doc['kind'] == 'NetworkPolicy':
                if not reviewed or doc != reviewed:
                    errors.extend(f'{name}: {error}' for error in network_policy_errors(spec))
            if doc['kind'] in {'ServiceAccount', 'Role', 'RoleBinding'} and (not reviewed or doc != reviewed or doc.get('apiVersion') != ('v1' if doc['kind'] == 'ServiceAccount' else 'rbac.authorization.k8s.io/v1')):
                errors.append(f'{name}: controller identity and RBAC require exact reviewed platform baseline')
            if doc['kind'] == 'Ingress':
                ingress_documents.setdefault(name, []).append(doc)
                if app_id == 'charter' and name == 'z-ingress-cimd.yaml':
                    # Host/TLS and app-owned backend routing are checked by the
                    # shared ingress validator; the app owns endpoint selection.
                    if spec.get('ingressClassName', 'nginx') != 'nginx':
                        errors.append(f'{name}: CIMD Ingress must use nginx')
                    annotations = metadata.get('annotations', {})
                    # Public launch/callback queries contain capabilities/codes.
                    # Permit only explicit log suppression; retain legacy empty annotations.
                    if annotations not in ({}, {'nginx.ingress.kubernetes.io/enable-access-log': 'false'}):
                        errors.append(f'{name}: CIMD Ingress annotations require platform review')
                for rule in spec.get('rules', []):
                    for route in rule.get('http', {}).get('paths', []):
                        if not owned(route.get('backend', {}).get('service', {}).get('name', '')):
                            errors.append(f'{name}: ingress backend must belong to the app')
            if doc['kind'] == 'PersistentVolumeClaim':
                errors.extend(f'{name}: {error}' for error in pvc_spec_errors(spec))
            if doc['kind'] == 'Service':
                errors.extend(f'{name}: {error}' for error in service_spec_errors(spec))
    if ingress_files is not None:
        ingress_documents = {}
        for file in ingress_files:
            filename = file.path.rsplit('/', 1)[-1]
            if not filename.endswith(('.yaml', '.yml')) or filename.endswith('.enc.yaml'):
                continue
            loader = None
            try:
                if len(file.content.encode('utf-8')) > MAX_INPUT_BYTES:
                    raise YamlLimitError('manifest exceeds input limit')
                loader = bounded_loader(file.content)
                count = 0
                documents = []
                while loader.check_data():
                    count += 1
                    if count > MAX_DOCUMENTS:
                        raise YamlLimitError('too many Ingress documents')
                    document = loader.get_data()
                    if isinstance(document, dict) and document.get('kind') == 'Ingress':
                        documents.append(document)
                if documents:
                    ingress_documents[filename] = documents
            except (yaml.YAMLError, YamlLimitError, RecursionError):
                # Keep prior resource failures and continue checking independent
                # manifests. Do not expose untrusted YAML content in errors.
                errors.append(f'{filename}: invalid YAML in complete Ingress collection')
            finally:
                if loader is not None:
                    loader.dispose()
    if ingress_documents:
        try:
            try:
                from . import ingress_policy
            except ImportError:
                import ingress_policy
            # Retain original filenames: grandfathered routes bind to that identity.
            tls_policies = [file.content for file in (ingress_files if ingress_files is not None else files)
                            if file.path.rsplit('/', 1)[-1] == 'tls-policy.json']
            if len(tls_policies) > 1:
                raise ValueError('duplicate TLS enrollment')
            errors.extend(ingress_policy.validate_tree(Path('/'), Path(__file__).with_name('ingress-policy.yaml'), Path('/') / app_id,
                          ingress_documents, allocated_app_ids or [], tls_policies[0] if tls_policies else None))
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            errors.append('cannot validate complete Ingress policy')
    return errors


if __name__ == '__main__':
    apply_resource_limits()
    try:
        raw = sys.stdin.buffer.read(MAX_OUTPUT_BYTES + 1)
        if len(raw) > MAX_OUTPUT_BYTES:
            raise ValueError('input limit')
        payload = json.loads(raw)
        files = [SimpleNamespace(**f) for f in payload['files']]
        errors = _resource_errors(files, payload['app_id'], payload.get('allocated_app_ids'), payload.get('approved_images'), [SimpleNamespace(**f) for f in payload['ingress_files']] if payload.get('ingress_files') is not None else None, payload.get('baseline_files'))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, MemoryError):
        errors = ['malformed or overly complex multi-resource bundle']
    sys.stdout.write(json.dumps(errors))
