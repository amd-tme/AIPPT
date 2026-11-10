import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import secret_upload_validation


def files(app, secret=None, descriptor=True, filename='z-ingress.yaml'):
    host = app + '.slai-app.amd.com'
    ingress = {'apiVersion': 'networking.k8s.io/v1', 'kind': 'Ingress',
               'metadata': {'name': 'hosted-slai-' + app, 'namespace': 'slai-app-prod'},
               'spec': {'rules': [{'host': host, 'http': {'paths': [{'path': '/', 'pathType': 'Prefix',
                         'backend': {'service': {'name': app, 'port': {'number': 80}}}}]}}],
                        'tls': [{'hosts': [host], 'secretName': secret or app + '-tls'}]}}
    result = [{'path': filename, 'content': yaml.safe_dump(ingress)}]
    if descriptor:
        result.append({'path': 'tls-policy.json', 'content': json.dumps(
            {'version': 1, 'mode': 'platform-managed', 'ingress': 'hosted-slai-' + app})})
    return result


@pytest.mark.parametrize('descriptor', [True, False])
@pytest.mark.parametrize('filename', ['z-ingress.yaml', 'extra-resources.yaml'])
def test_client_rejects_legacy_wildcard_in_any_ingress(descriptor, filename):
    bundle = files('florence-sp7-dashboard', 'slai-app-wildcard-tls', descriptor, filename)
    assert not secret_upload_validation.validate(bundle, 'florence-sp7-dashboard')


def test_client_accepts_migrated_binding_and_checks_descriptor():
    assert secret_upload_validation.validate(files('florence-sp7-dashboard'), 'florence-sp7-dashboard')
    with pytest.raises(ValueError, match='dedicated Secret'):
        secret_upload_validation.validate(files('florence-sp7-dashboard', 'another-app-tls'), 'florence-sp7-dashboard')


@pytest.mark.parametrize('app', ['localai', 'llmd-localai', 'localai-router'])
def test_client_preserves_explicit_localai_exclusions(app):
    assert secret_upload_validation.validate(files(app, 'slai-app-wildcard-tls', False), app)


def test_upload_worker_checks_app_aware_envelope():
    helper = Path(secret_upload_validation.__file__)
    result = subprocess.run([sys.executable, str(helper)], input=json.dumps({
        'app_id': 'florence-sp7-dashboard', 'files': files('florence-sp7-dashboard', 'slai-app-wildcard-tls')}),
        text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == {'valid': False}
