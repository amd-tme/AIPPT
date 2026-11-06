from pathlib import Path
import main


def test_overlapping_resource_names():
    path = Path('/bundle/slai-app-prod/foo/service.yaml')
    for name in ['foo-bar', 'foo-bar-config', 'foo-bar-data']:
        assert not main._application_owns(name, 'foo', path, {'foo', 'foo-bar'})
    for name in ['foo', 'foo-config', 'foo-barista']:
        assert main._application_owns(name, 'foo', path, {'foo', 'foo-bar'})


def test_resources_and_references_use_trusted_allocations(monkeypatch):
    monkeypatch.setattr(main, '_trusted_allocated_app_ids', lambda: {'foo', 'foo-bar'})
    dep = Path('/bundle/slai-app-prod/foo/deployment.yaml')
    doc = {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': 'foo-bar'}}
    assert main._bundle_resource_errors(doc, dep.with_name('service.yaml'), 'foo')
    doc = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'foo-bar-config'}}
    assert main._bundle_resource_errors(doc, dep.with_name('configmap.yaml'), 'foo')
    for field in ['configMap', 'configMapRef', 'configMapKeyRef', 'persistentVolumeClaim']:
        ref = {'claimName': 'foo-bar-data'} if field == 'persistentVolumeClaim' else {'name': 'foo-bar-config'}
        assert main._secret_reference_errors({field: ref}, dep)
    assert not main._secret_reference_errors({'configMap': {'name': 'foo-config'}}, dep)


def test_allocation_failure_does_not_accept_resource(monkeypatch):
    def unavailable(): raise ValueError('allocations unavailable')
    monkeypatch.setattr(main, '_trusted_allocated_app_ids', unavailable)
    import pytest
    with pytest.raises(ValueError):
        main._application_owns('foo-bar', 'foo', Path('/bundle/slai-app-prod/foo/service.yaml'))


def test_additional_bundle_secret_references_reject_allocated_collisions():
    import json
    from types import SimpleNamespace
    from bundle_resources import resource_errors
    import yaml
    for field, reference, other in [
        ('secretKeyRef', {'name':'foo-secrets','key':'fixture'}, 'foo-secrets'),
        ('secret', {'secretName':'foo-secrets'}, 'foo-secrets'),
        ('imagePullSecrets', [{'name':'foo-harbor-pull'}], 'foo-harbor-pull'),
    ]:
        doc={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'foo-config','namespace':'slai-app-prod'},'data':{},field:reference}
        files=[SimpleNamespace(path='deploy/slai-app-prod/foo/configmap.yaml',content=yaml.safe_dump(doc))]
        assert not resource_errors(files,'foo',{'foo'})
        assert any('application-owned' in e for e in resource_errors(files,'foo',{'foo',other}))


def test_wildcard_tls_secret_rejected_in_pod_references():
    from types import SimpleNamespace
    from bundle_resources import resource_errors
    import yaml
    for reference in [
        {'volumes':[{'name':'tls','secret':{'secretName':'slai-app-wildcard-tls'}}]},
        {'env':[{'name':'FIXTURE','valueFrom':{'secretKeyRef':{'name':'slai-app-wildcard-tls','key':'tls.key'}}}]},
        {'envFrom':[{'secretRef':{'name':'slai-app-wildcard-tls'}}]},
    ]:
        doc={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'foo-config','namespace':'slai-app-prod'},'data':{},'fixture':reference}
        files=[SimpleNamespace(path='deploy/slai-app-prod/foo/configmap.yaml',content=yaml.safe_dump(doc))]
        assert any('application-owned' in e for e in resource_errors(files,'foo',{'foo'}))


def test_wildcard_tls_volume_requires_reviewed_baseline(monkeypatch):
    import yaml
    import bundle_resources
    monkeypatch.setattr(main, '_trusted_allocated_app_ids', lambda: {'foo'})
    dep = Path('/bundle/slai-app-prod/foo/deployment.yaml')
    volume = {'name': 'tls', 'secret': {'secretName': 'slai-app-wildcard-tls'}}
    pod = {'volumes': [volume]}
    monkeypatch.setattr(bundle_resources, 'reviewed_baseline_files', lambda: {})
    assert main._secret_reference_errors(pod, dep)
    baseline = {'kind': 'Deployment', 'spec': {'template': {'spec': pod}}}
    monkeypatch.setattr(bundle_resources, 'reviewed_baseline_files', lambda: {
        'deploy/slai-app-prod/foo/deployment.yaml': yaml.safe_dump(baseline)})
    assert not main._secret_reference_errors(pod, dep)
    assert main._secret_reference_errors({'containers': [{'envFrom': [
        {'secretRef': {'name': 'slai-app-wildcard-tls'}}]}]}, dep)
    assert main._secret_reference_errors({'volumes': [
        {'name': 'other', 'secret': {'secretName': 'slai-app-wildcard-tls'}}]}, dep)
