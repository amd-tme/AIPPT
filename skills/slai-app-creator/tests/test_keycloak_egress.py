"""SSO preparation and pre-upload regression for Sahil's rejected bundles."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml
from keycloak_egress import missing_addresses, required_addresses, validate_files
import keycloak_egress
from secret_upload_validation import validate

ROOT = Path(__file__).resolve().parents[1]


def policy():
    return {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
            'metadata': {'name': 'example-net'},
            'spec': {'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'example'}},
                     'policyTypes': ['Ingress', 'Egress'], 'egress': []}}


def files(document, enabled=True, mode='forward-auth'):
    return [{'path': 'auth-policy.json', 'content': json.dumps({'enabled': enabled, 'mode': mode})},
            {'path': 'networkpolicy.yaml', 'content': yaml.safe_dump(document)}]


@pytest.mark.parametrize('mode', ['forward-auth', 'oauth2-proxy'])
def test_rejects_missing_https_before_upload(mode):
    with pytest.raises(ValueError, match='Keycloak SSO requires TCP 443'):
        validate(files(policy(), mode=mode))


def test_disabled_or_absent_sso_needs_no_grant():
    validate_files([])
    validate_files(files(policy(), enabled=False))


@pytest.mark.skipif(os.name != 'posix', reason='Secure preparation requires POSIX descriptor operations')
def test_apply_preserves_existing_rules_and_is_idempotent(tmp_path):
    document = policy()
    document['spec']['egress'] = [{'to': [{'ipBlock': {'cidr': '192.0.2.1/32'}}],
                                 'ports': [{'port': 4317, 'protocol': 'TCP'}]}]
    original = copy.deepcopy(document)
    (tmp_path / 'auth-policy.json').write_text(json.dumps({'enabled': True}))
    path = tmp_path / 'networkpolicy.yaml'
    path.write_text(yaml.safe_dump(document))
    command = [sys.executable, str(ROOT / 'scripts/keycloak_egress.py'), str(tmp_path)]
    assert subprocess.run(command, capture_output=True).returncode == 1
    subprocess.run(command + ['--apply'], check=True)
    prepared = yaml.safe_load(path.read_text())
    assert prepared['spec']['egress'][:-1] == original['spec']['egress']
    assert prepared['spec']['podSelector'] == original['spec']['podSelector']
    assert not missing_addresses(prepared)
    grant = prepared['spec']['egress'][-1]
    assert grant['ports'] == [{'protocol': 'TCP', 'port': 443}]
    assert {x['ipBlock']['cidr'] for x in grant['to']} == {x + '/32' for x in required_addresses()}
    first = path.read_bytes()
    subprocess.run(command + ['--apply'], check=True)
    assert first == path.read_bytes()
    assert validate(files(prepared))


def test_udp_wrong_destination_and_excluded_hosts_do_not_count():
    document = policy()
    document['spec']['egress'] = [{'to': [{'ipBlock': {'cidr': '10.0.0.0/8',
                                   'except': [required_addresses()[0] + '/32']}}],
                                 'ports': [{'protocol': 'TCP', 'port': 443}]}]
    assert missing_addresses(document) == [required_addresses()[0]]
    document['spec']['egress'][0]['ports'][0]['protocol'] = 'UDP'
    assert missing_addresses(document) == required_addresses()


def test_packaged_destinations_match_platform_when_available():
    platform = ROOT.parents[1] / 'config/platform-keycloak-egress.json'
    if not platform.exists():
        pytest.skip('standalone plugin')
    assert json.loads(platform.read_text()) == json.loads((ROOT / 'assets/platform-keycloak-egress.json').read_text())


@pytest.fixture
def secure_bundle(tmp_path):
    if os.name != 'posix':
        pytest.skip('Secure preparation requires POSIX descriptor operations')
    directory = tmp_path / 'bundle'
    directory.mkdir(mode=0o700)
    (directory / 'auth-policy.json').write_text(json.dumps({'enabled': True}))
    (directory / 'networkpolicy.yaml').write_text(yaml.safe_dump(policy()))
    return directory


@pytest.mark.parametrize('name', ['auth-policy.json', 'networkpolicy.yaml'])
def test_preparation_rejects_symlink_inputs(secure_bundle, tmp_path, name):
    target = tmp_path / 'outside'
    target.write_text('outside sentinel')
    (secure_bundle / name).unlink()
    (secure_bundle / name).symlink_to(target)
    with pytest.raises((OSError, ValueError)):
        keycloak_egress.prepare_bundle(secure_bundle, apply=True)
    assert target.read_text() == 'outside sentinel'


def test_preparation_rejects_symlink_ancestor(secure_bundle, tmp_path):
    alias = tmp_path / 'alias'
    alias.symlink_to(secure_bundle, target_is_directory=True)
    original = (secure_bundle / 'networkpolicy.yaml').read_bytes()
    with pytest.raises((OSError, ValueError)):
        keycloak_egress.prepare_bundle(alias, apply=True)
    assert (secure_bundle / 'networkpolicy.yaml').read_bytes() == original


def test_preparation_rejects_untrusted_writable_ancestor(secure_bundle):
    secure_bundle.parent.chmod(0o777)
    try:
        with pytest.raises(ValueError, match='ancestors'):
            keycloak_egress.prepare_bundle(secure_bundle, apply=True)
    finally:
        secure_bundle.parent.chmod(0o700)


def test_replaced_policy_cannot_redirect_update(secure_bundle, tmp_path, monkeypatch):
    target = tmp_path / 'outside'
    target.write_text('outside sentinel')
    update = keycloak_egress.atomic_update
    def replace_leaf(directory_fd, name, original, content):
        (secure_bundle / name).unlink()
        (secure_bundle / name).symlink_to(target)
        return update(directory_fd, name, original, content)
    monkeypatch.setattr(keycloak_egress, 'atomic_update', replace_leaf)
    with pytest.raises(ValueError, match='changed before update'):
        keycloak_egress.prepare_bundle(secure_bundle, apply=True)
    assert target.read_text() == 'outside sentinel'
    assert not list(secure_bundle.glob('.keycloak-egress-*'))


def test_replaced_bundle_path_keeps_update_in_opened_directory(secure_bundle, tmp_path, monkeypatch):
    pinned = tmp_path / 'pinned'
    outside = tmp_path / 'outside'
    outside.mkdir(mode=0o700)
    sentinel = outside / 'networkpolicy.yaml'
    sentinel.write_text('outside sentinel')
    update = keycloak_egress.atomic_update
    def replace_directory(directory_fd, name, original, content):
        secure_bundle.rename(pinned)
        secure_bundle.symlink_to(outside, target_is_directory=True)
        return update(directory_fd, name, original, content)
    monkeypatch.setattr(keycloak_egress, 'atomic_update', replace_directory)
    keycloak_egress.prepare_bundle(secure_bundle, apply=True)
    assert sentinel.read_text() == 'outside sentinel'
    assert not missing_addresses(yaml.safe_load((pinned / 'networkpolicy.yaml').read_text()))


def test_failed_atomic_replace_preserves_original_and_cleans_temp(secure_bundle, monkeypatch):
    original = (secure_bundle / 'networkpolicy.yaml').read_bytes()
    def fail(*args, **kwargs):
        raise OSError('synthetic replace failure')
    monkeypatch.setattr(keycloak_egress.os, 'replace', fail)
    with pytest.raises(OSError):
        keycloak_egress.prepare_bundle(secure_bundle, apply=True)
    assert (secure_bundle / 'networkpolicy.yaml').read_bytes() == original
    assert not list(secure_bundle.glob('.keycloak-egress-*'))


def test_atomic_update_preserves_policy_permissions(secure_bundle):
    path = secure_bundle / 'networkpolicy.yaml'
    path.chmod(0o640)
    keycloak_egress.prepare_bundle(secure_bundle, apply=True)
    assert path.stat().st_mode & 0o777 == 0o640
