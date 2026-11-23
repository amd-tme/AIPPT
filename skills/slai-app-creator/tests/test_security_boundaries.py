import copy
from pathlib import Path
import main
from test_ciphertext_validation import VALID, RECIPIENT
import ciphertext_validation


def test_secret_ownership_rejects_other_app_and_platform_names():
    document = copy.deepcopy(VALID)
    document['metadata'] = {'namespace': 'slai-app-prod'}
    for name in ('other-secrets', 'slai-app-wildcard-tls', 'slai-app-amd-com-tls', None):
        document['metadata']['name'] = name
        assert ciphertext_validation.check_document(document, {RECIPIENT}, 'slai-app-prod', 'example')
    document['metadata']['name'] = 'example-secrets'
    assert not ciphertext_validation.check_document(document, {RECIPIENT}, 'slai-app-prod', 'example')


def test_pod_security_rejects_host_access_and_privileged_init_containers():
    container = {'securityContext': {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}}
    pod = {'automountServiceAccountToken': False, 'securityContext': {'runAsNonRoot': True, 'seccompProfile': {'type': 'RuntimeDefault'}}, 'containers': [container]}
    assert not main._pod_security_errors(pod, Path('deployment.yaml'))
    for field in ('hostNetwork', 'hostPID', 'hostIPC'):
        bad = copy.deepcopy(pod); bad[field] = True
        assert main._pod_security_errors(bad, Path('deployment.yaml'))
    bad = copy.deepcopy(pod); bad['volumes'] = [{'hostPath': {'path': '/'}}]
    assert main._pod_security_errors(bad, Path('deployment.yaml'))
    bad = copy.deepcopy(pod); bad['initContainers'] = [{'securityContext': {'privileged': True}}]
    assert main._pod_security_errors(bad, Path('deployment.yaml'))


def test_secret_reference_checks_cover_init_projected_and_pull_secrets(monkeypatch):
    monkeypatch.setattr(main, "_trusted_allocated_app_ids", lambda: {"example"})
    dep = Path('/deploy/slai-app-prod/example/deployment.yaml')
    bad_pods = [
        {'volumes': [{'persistentVolumeClaim': {'claimName': 'other-data'}}]},
        {'containers': [{'envFrom': [{'configMapRef': {'name': 'other-config'}}]}]},
        {'volumes': [{'csi': {'nodePublishSecretRef': {'name': 'shared-secret'}}}]},
        {'initContainers': [{'envFrom': [{'secretRef': {'name': 'other-secrets'}}]}]},
        {'ephemeralContainers': [{'env': [{'valueFrom': {'secretKeyRef': {'name': 'platform-secret'}}}]}]},
        {'volumes': [{'projected': {'sources': [{'secret': {'name': 'other-secrets'}}]}}]},
        {'imagePullSecrets': [{'name': 'shared-robot'}]},
    ]
    for pod in bad_pods:
        assert main._secret_reference_errors(pod, dep)
    assert not main._secret_reference_errors({'imagePullSecrets': [{'name': 'example-harbor-pull'}], 'containers': [{'envFrom': [{'secretRef': {'name': 'example-secrets'}}]}]}, dep)


def test_extra_resources_cannot_replace_other_app_config():
    document = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'other-config'}}
    assert main._bundle_resource_errors(document, Path('extra.yaml'), 'example')
    document['metadata']['name'] = 'example-config'
    assert not main._bundle_resource_errors(document, Path('extra.yaml'), 'example')


def test_canonical_service_cannot_target_other_application():
    document = {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': 'other'}, 'spec': {'selector': {'app.kubernetes.io/name': 'other'}, 'ports': [{'port': 80}]}}
    path = Path('service.yaml')
    assert main._bundle_resource_errors(document, path, 'example')
    document['metadata']['name'] = 'example'
    assert main._bundle_resource_errors(document, path, 'example')
    document['spec']['selector']['app.kubernetes.io/name'] = 'example'
    assert not main._bundle_resource_errors(document, path, 'example')


def test_pod_cannot_select_privileged_service_account_or_request_token():
    container = {'securityContext': {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}}
    pod = {'automountServiceAccountToken': False, 'securityContext': {'runAsNonRoot': True, 'seccompProfile': {'type': 'RuntimeDefault'}}, 'containers': [container]}
    assert not main._pod_security_errors(pod, Path('deployment.yaml'))
    for fields in ({'serviceAccountName': 'platform-admin'}, {'automountServiceAccountToken': True}, {'volumes': [{'projected': {'sources': [{'serviceAccountToken': {'path': 'token'}}]}}]}):
        assert main._pod_security_errors(dict(pod, **fields), Path('deployment.yaml'))


def test_pvc_requires_new_application_storage():
    document = {'apiVersion': 'v1', 'kind': 'PersistentVolumeClaim',
                'metadata': {'name': 'example-data'},
                'spec': {'storageClassName': 'nfs-network', 'accessModes': ['ReadWriteMany'],
                         'resources': {'requests': {'storage': '1Gi'}}}}
    path = Path('pvc.yaml')
    assert not main._bundle_resource_errors(document, path, 'example')
    for field, value in [('volumeName', 'other-volume'), ('selector', {}),
                         ('dataSource', {'name': 'other-snapshot'}),
                         ('dataSourceRef', {'name': 'other-data'})]:
        bad = copy.deepcopy(document)
        bad['spec'][field] = value
        assert main._bundle_resource_errors(bad, path, 'example')
    for storage_class in (None, '', 'unapproved'):
        bad = copy.deepcopy(document)
        bad['spec']['storageClassName'] = storage_class
        assert main._bundle_resource_errors(bad, path, 'example')


def test_pod_volumes_cannot_bypass_application_pvc(monkeypatch):
    monkeypatch.setattr(main, "_trusted_allocated_app_ids", lambda: {"example"})
    dep = Path('/deploy/slai-app-prod/example/deployment.yaml')
    container = {'securityContext': {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}}
    pod = {'automountServiceAccountToken': False, 'securityContext': {'runAsNonRoot': True, 'seccompProfile': {'type': 'RuntimeDefault'}}, 'containers': [container]}
    for source in ({'nfs': {'server': 'storage', 'path': '/other'}}, {'csi': {'driver': 'driver'}},
                   {'persistentVolumeClaim': {'claimName': 'other-data'}},
                   {'emptyDir': {}, 'persistentVolumeClaim': {'claimName': 'example-data'}}):
        bad = copy.deepcopy(pod)
        bad['volumes'] = [{'name': 'data', **source}]
        assert main._pod_security_errors(bad, dep)
    for source in ({'emptyDir': {}}, {'persistentVolumeClaim': {'claimName': 'example-data'}},
                   {'secret': {'secretName': 'example-secrets'}}, {'configMap': {'name': 'example-config'}},
                   {'projected': {'sources': [{'configMap': {'name': 'example-config'}}]}}):
        good = copy.deepcopy(pod)
        good['volumes'] = [{'name': 'data', **source}]
        assert not main._pod_security_errors(good, dep)


def test_host_port_exposure_is_rejected_for_all_container_types():
    dep = Path('/deploy/slai-app-prod/example/deployment.yaml')
    context = {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}
    pod = {'automountServiceAccountToken': False, 'securityContext': {'runAsNonRoot': True, 'seccompProfile': {'type': 'RuntimeDefault'}}}
    for group in ('containers', 'initContainers', 'ephemeralContainers'):
        for port, rejected in [({'containerPort': 8080}, False),
                               ({'containerPort': 8080, 'hostPort': 0}, False),
                               ({'containerPort': 8080, 'hostPort': 8080}, True)]:
            candidate = copy.deepcopy(pod)
            candidate[group] = [{'securityContext': context, 'ports': [port]}]
            assert bool(main._pod_security_errors(candidate, dep)) == rejected
