import json
from pathlib import Path

import pytest

import main
import submit_app
import ingress_policy
import yaml


def test_submit_prepares_enrollment_without_app_ownership_settings():
    files = [{'path': 'z-ingress.yaml', 'content': json.dumps({'kind': 'Ingress', 'metadata': {'name': 'new-app'}})}]
    submit_app.add_managed_tls_policy(files, 'new-app')
    policy = json.loads(files[-1]['content'])
    assert files[-1]['path'] == 'tls-policy.json'
    assert policy == {'version': 1, 'mode': 'platform-managed', 'ingress': 'new-app'}


def test_existing_app_binding_is_left_for_separate_migration():
    legacy = json.loads((Path(submit_app.__file__).parents[1] / 'assets/tls-cutover.json').read_text())['legacy_apps'][0]
    files = [{'path': 'z-ingress.yaml', 'content': 'existing ingress is not rewritten'}]
    submit_app.add_managed_tls_policy(files, legacy)
    assert len(files) == 1


def test_platform_key_cannot_be_injected_into_app_pod(tmp_path):
    app = tmp_path / 'new-app'
    app.mkdir()
    (app / 'tls-policy.json').write_text('{}')
    errors = main._secret_reference_errors({'containers': [{'envFrom': [{'secretRef': {'name': 'new-app-tls'}}]}]}, app / 'deployment.yaml')
    assert any('private keys' in error for error in errors)


@pytest.mark.parametrize('ingress_name', ['other-app', '', None])
def test_auto_enrollment_rejects_foreign_or_missing_ingress_identity(ingress_name):
    files = [{'path': 'z-ingress.yaml', 'content': json.dumps({'kind': 'Ingress', 'metadata': {'name': ingress_name}})}]
    with pytest.raises(submit_app.ClientError):
        submit_app.add_managed_tls_policy(files, 'new-app')


def migration_bundle(tmp_path, *, descriptor=True, secret_name='access-demo-tls'):
    directory = tmp_path / 'access-demo'; directory.mkdir()
    doc = {'apiVersion': 'networking.k8s.io/v1', 'kind': 'Ingress',
           'metadata': {'name': 'access-demo', 'namespace': 'slai-app-prod'},
           'spec': {'rules': [{'host': 'access-demo.slai-app.amd.com', 'http': {'paths': [
               {'path': '/', 'pathType': 'Prefix', 'backend': {'service': {'name': 'access-demo', 'port': {'number': 80}}}}]}}],
               'tls': [{'hosts': ['access-demo.slai-app.amd.com'], 'secretName': secret_name}]}}
    (directory / 'z-ingress.yaml').write_text(yaml.safe_dump(doc))
    if descriptor:
        (directory / 'tls-policy.json').write_text(json.dumps({'version': 1, 'mode': 'platform-managed', 'ingress': 'access-demo'}))
    return directory, doc


def migration_errors(directory, **kwargs):
    skill = Path(__file__).resolve().parents[1]
    return ingress_policy.validate_tree(skill, skill / 'scripts/ingress-policy.yaml', directory,
                                        allocated_app_ids={'access-demo'}, **kwargs)


def test_existing_app_can_migrate_without_changing_its_hostname_or_path(tmp_path):
    directory, _ = migration_bundle(tmp_path)
    assert migration_errors(directory) == []


def test_retired_wildcard_is_rejected_even_without_descriptor(tmp_path):
    directory, _ = migration_bundle(tmp_path, descriptor=False, secret_name='slai-app-wildcard-tls')
    assert any('wildcard TLS is retired' in error for error in migration_errors(directory))


def test_legacy_app_cannot_change_tls_binding_without_enrollment(tmp_path):
    directory, _ = migration_bundle(tmp_path, descriptor=False)
    assert migration_errors(directory)


def test_descriptor_must_match_actual_dedicated_ingress(tmp_path):
    directory, _ = migration_bundle(tmp_path, secret_name='slai-app-wildcard-tls')
    assert any('invalid platform-managed' in error for error in migration_errors(directory))


def test_migration_cannot_add_an_apex_path(tmp_path):
    directory, doc = migration_bundle(tmp_path)
    doc['metadata']['name'] = 'access-demo-apex'
    doc['spec']['rules'][0]['host'] = 'slai-app.amd.com'
    doc['spec']['rules'][0]['http']['paths'][0]['path'] = '/new-access-demo'
    doc['spec']['tls'][0]['hosts'] = ['slai-app.amd.com']
    (directory / 'extra-ingress.yaml').write_text(yaml.safe_dump(doc))
    assert any('new routes must use host' in error for error in migration_errors(directory))


def test_supplied_document_worker_honors_the_same_migration_contract(tmp_path):
    directory, doc = migration_bundle(tmp_path)
    raw = (directory / 'tls-policy.json').read_text()
    assert migration_errors(directory, supplied_documents={'z-ingress.yaml': [doc]}, supplied_tls_policy=raw) == []
    assert migration_errors(directory, supplied_documents={'z-ingress.yaml': [doc]})


def test_bounded_bundle_worker_accepts_migrated_tls_descriptor(tmp_path):
    from types import SimpleNamespace
    import bundle_resources
    directory, _ = migration_bundle(tmp_path)
    files = [SimpleNamespace(path='deploy/slai-app-prod/access-demo/' + path.name,
                             content=path.read_text()) for path in directory.iterdir()]
    assert bundle_resources.resource_errors(files, 'access-demo', {'access-demo'}, ingress_files=files) == []


def test_additional_canonical_routes_migrate_together(tmp_path):
    directory, doc = migration_bundle(tmp_path)
    directory = directory.rename(tmp_path / 'charter')
    doc['metadata']['name'] = 'hosted-slai-charter'
    doc['spec']['rules'][0]['host'] = 'charter.slai-app.amd.com'
    doc['spec']['rules'][0]['http']['paths'][0]['backend']['service']['name'] = 'charter'
    doc['spec']['tls'] = [{'hosts': ['charter.slai-app.amd.com'], 'secretName': 'charter-tls'}]
    (directory / 'z-ingress.yaml').write_text(yaml.safe_dump(doc))
    (directory / 'tls-policy.json').write_text(json.dumps({'version': 1, 'mode': 'platform-managed', 'ingress': 'hosted-slai-charter'}))
    doc['metadata']['name'] = 'hosted-slai-charter-cimd'
    doc['spec']['rules'][0]['http']['paths'] = [
        {'path': '/v1/token', 'pathType': 'Exact', 'backend': {'service': {'name': 'charter-cimd', 'port': {'name': 'http'}}}}]
    (directory / 'z-ingress-cimd.yaml').write_text(yaml.safe_dump(doc))
    assert migration_errors(directory) == []
    doc['spec']['tls'][0]['secretName'] = 'slai-app-wildcard-tls'
    (directory / 'z-ingress-cimd.yaml').write_text(yaml.safe_dump(doc))
    assert any('managed app routes must use' in error for error in migration_errors(directory))


def test_all_canonical_ingresses_in_managed_app_require_dedicated_secret(tmp_path):
    directory, doc = migration_bundle(tmp_path)
    doc['metadata']['name'] = 'access-demo-extra'
    doc['spec']['rules'][0]['http']['paths'][0]['path'] = '/extra'
    doc['spec']['tls'][0]['secretName'] = 'slai-app-wildcard-tls'
    (directory / 'extra-ingress.yaml').write_text(yaml.safe_dump(doc))
    assert any('managed app routes must use' in error for error in migration_errors(directory))


@pytest.mark.parametrize('changed_path', [False, True])
def test_shared_apex_certificate_transition_preserves_exact_legacy_path(tmp_path, changed_path):
    directory = tmp_path / 'competes-am-regen'; directory.mkdir()
    host = 'slai-app.amd.com'
    doc = {'kind': 'Ingress', 'metadata': {'name': 'competes-am-regen', 'namespace': 'slai-app-prod'},
           'spec': {'rules': [{'host': host, 'http': {'paths': [
               {'path': '/new-path' if changed_path else '/competes-am-regen', 'pathType': 'Prefix',
                'backend': {'service': {'name': 'competes-am-regen', 'port': {'number': 80}}}}]}}],
               'tls': [{'hosts': [host], 'secretName': 'platform-apex-tls'}]}}
    (directory / 'z-ingress.yaml').write_text(yaml.safe_dump(doc))
    errors = migration_errors(directory)
    assert bool(errors) is changed_path


def test_legacy_host_certificate_map_cannot_introduce_a_new_shared_host(tmp_path):
    source = Path(__file__).resolve().parents[1] / 'scripts/ingress-policy.yaml'
    data = yaml.safe_load(source.read_text())
    data['legacy_host_tls_secrets']['new-shared.amd.com'] = 'other-tls'
    path = tmp_path / 'policy.yaml'; path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match='frozen legacy hosts'):
        ingress_policy.load_policy(path)


def test_legacy_host_certificate_map_cannot_claim_an_application_default_secret(tmp_path):
    source = Path(__file__).resolve().parents[1] / 'scripts/ingress-policy.yaml'
    data = yaml.safe_load(source.read_text())
    data['legacy_host_tls_secrets']['gce-hub.amd.com'] = 'gce-hub-tls'
    path = tmp_path / 'policy.yaml'; path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        ingress_policy.load_policy(path)
