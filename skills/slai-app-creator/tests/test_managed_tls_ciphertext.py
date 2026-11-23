"""Managed ingress checks accept bounded Secret streams and sanitize failures."""
import json
from pathlib import Path
import subprocess

import pytest
import yaml

import ingress_policy
import main
from per_app_tls_inventory import profile_target
from yaml_limits import MAX_DOCUMENTS, MAX_INPUT_BYTES


ENC = 'ENC[AES256_GCM,data:dGVzdA==,iv:aXY=,tag:dGFn,type:str]'


def encrypted_secret(name):
    root = Path(__file__).resolve().parents[1]
    recipient = yaml.safe_load((root / 'assets/platform.sops.yaml').read_text())['creation_rules'][0]['age']
    return {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': name, 'namespace': 'slai-app-prod'},
            'stringData': {'password': ENC}, 'sops': {'mac': ENC, 'age': [{'recipient': recipient, 'enc': 'fixture'}],
                'encrypted_regex': '^(data|stringData)$', 'version': '3.9.4', 'lastmodified': '2026-11-02T00:00:00Z'}}


@pytest.fixture
def managed_bundle(tmp_path):
    directory = tmp_path / 'new-app'
    directory.mkdir()
    (directory / 'tls-policy.json').write_text(json.dumps({'version': 1, 'mode': 'platform-managed', 'ingress': 'new-app'}))
    ingress = {'kind': 'Ingress', 'metadata': {'name': 'new-app', 'namespace': 'slai-app-prod'},
               'spec': {'tls': [{'hosts': ['new-app.slai-app.amd.com'], 'secretName': 'new-app-tls'}]}}
    (directory / 'z-ingress.yaml').write_text(yaml.safe_dump(ingress))
    return directory


def test_managed_tls_accepts_supported_multidocument_encrypted_secret_bundle(managed_bundle):
    path = managed_bundle / 'secrets.enc.yaml'
    path.write_text(yaml.safe_dump_all([encrypted_secret('new-app-first'), encrypted_secret('new-app-second')]))
    assert main.ciphertext_errors(path) == []
    assert main._managed_tls_errors(managed_bundle) == []


@pytest.mark.parametrize('position', [0, 1, 2])
def test_each_encrypted_document_is_checked_for_competing_managed_secret(managed_bundle, position):
    documents = [encrypted_secret('new-app-first'), encrypted_secret('new-app-second')]
    documents.insert(position, encrypted_secret('new-app-tls'))
    (managed_bundle / 'secrets.enc.yaml').write_text(yaml.safe_dump_all(documents))
    assert main._managed_tls_errors(managed_bundle) == ['App bundles cannot supply or overwrite the platform-managed TLS Secret']


@pytest.mark.parametrize('filename', ['secrets.enc.yaml', 'z-ingress.yaml'])
def test_invalid_yaml_is_a_sanitized_validation_error_not_a_crash(managed_bundle, filename):
    marker = 'private-fixture-value-must-not-appear'
    (managed_bundle / filename).write_text('password: ' + marker + '\n  invalid: [\n')
    errors = main._managed_tls_errors(managed_bundle)
    assert errors
    assert marker not in ' '.join(errors)


@pytest.mark.parametrize('limit', ['documents', 'bytes'])
def test_managed_tls_ciphertext_retains_worker_limits(managed_bundle, limit):
    path = managed_bundle / 'secrets.enc.yaml'
    if limit == 'documents':
        path.write_text(yaml.safe_dump_all([encrypted_secret('new-app-data')] * (MAX_DOCUMENTS + 1)))
    else:
        with path.open('wb') as stream:
            stream.truncate(MAX_INPUT_BYTES + 1)
    assert main._managed_tls_errors(managed_bundle)


def test_managed_tls_ciphertext_worker_timeout_is_sanitized(managed_bundle, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('sensitive worker diagnostics suppressed', 10)
    monkeypatch.setattr(ingress_policy, 'bounded_documents', timeout)
    (managed_bundle / 'secrets.enc.yaml').write_text(yaml.safe_dump(encrypted_secret('new-app-data')))
    errors = main._managed_tls_errors(managed_bundle)
    assert errors
    assert 'sensitive worker diagnostics' not in ' '.join(errors)


def test_managed_tls_uses_reviewed_legacy_profile_ingress_file(tmp_path):
    directory = tmp_path / 'gce-hub'
    directory.mkdir()
    target = profile_target('gce-hub')
    (directory / 'tls-policy.json').write_text(json.dumps({'version': 1, 'mode': 'platform-managed',
        'ingress': target['ingress'], 'legacy_profile': 'gce-hub'}))
    ingress = {'kind': 'Ingress', 'metadata': {'name': target['ingress'], 'namespace': target['namespace']},
               'spec': {'tls': [{'hosts': [target['hostname']], 'secretName': target['secret_name']}]}}
    (directory / 'z-ingress-vanity.yaml').write_text(yaml.safe_dump(ingress))
    (directory / 'z-ingress.yaml').write_text(yaml.safe_dump({'kind': 'Ingress', 'metadata': {'name': 'gce-hub'},
        'spec': {'tls': [{'hosts': ['slai-app.amd.com'], 'secretName': 'slai-app-amd-com-tls'}]}}))
    assert main._managed_tls_errors(directory) == []
    ingress['spec']['tls'][0]['secretName'] = 'gce-hub-amd-com-tls'
    (directory / 'z-ingress-vanity.yaml').write_text(yaml.safe_dump(ingress))
    assert main._managed_tls_errors(directory)
