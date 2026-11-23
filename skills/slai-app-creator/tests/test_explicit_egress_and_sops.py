import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
import main
import bundle_resources

ROOT = Path(__file__).resolve().parents[3]


def validators(spec, tmp_path):
    dep = {'spec': {'template': {'metadata': {'labels': {'app.kubernetes.io/name': 'example'}}, 'spec': {'containers': []}}}}
    policy = {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy', 'spec': spec}
    yield main._networkpolicy_errors(yaml.safe_dump(policy), yaml.safe_dump(dep), tmp_path / 'networkpolicy.yaml')
    yield bundle_resources.network_policy_errors(spec)
    file = ROOT / 'tools/slai-app-submission/src/slai_app_submission/bundle_resources.py'
    if not file.is_file():
        return
    module_spec = importlib.util.spec_from_file_location('hosted_egress_resources', file)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    yield module.network_policy_errors(spec)


def policy():
    return {'policyTypes': ['Ingress', 'Egress'], 'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'example'}}, 'ingress': [], 'egress': []}


@pytest.mark.parametrize('cidr', ['0.0.0.0/0', '::/0', '10.0.0.0/8', '10.67.251.0/24', '2001:db8::/32'])
def test_explicit_egress_ranges(cidr, tmp_path):
    spec = policy()
    spec['egress'] = [{'to': [{'ipBlock': {'cidr': cidr}}], 'ports': [{'port': 6123}, {'port': 23}]}]
    assert all(not errors for errors in validators(spec, tmp_path))


def test_default_deny_and_invalid_rules(tmp_path):
    assert all(not errors for errors in validators(policy(), tmp_path))
    for rule in [{}, {'to': [{'ipBlock': {'cidr': '0.0.0.0/0'}}]}, {'to': [{'ipBlock': {'cidr': '10.1.2.3/8'}}], 'ports': [{'port': 23}]}]:
        spec = policy()
        spec['egress'] = [rule]
        assert all(errors for errors in validators(spec, tmp_path))
    spec = policy()
    spec['ingress'] = [{'from': [{'ipBlock': {'cidr': '0.0.0.0/0'}}], 'ports': [{'port': 23}]}]
    assert all(errors for errors in validators(spec, tmp_path))


def test_bundled_sops_rule_encrypts_only_secret_values(tmp_path):
    config = ROOT / 'skills/slai-app-creator/assets/platform.sops.yaml'
    rules = yaml.safe_load(config.read_text())['creation_rules']
    assert rules[0]['encrypted_regex'] == '^(data|stringData)$'
    if (ROOT / '.sops.yaml').is_file():
        assert rules == yaml.safe_load((ROOT / '.sops.yaml').read_text())['creation_rules']
    sops = shutil.which('sops') or str(Path.home() / '.cache/slai-app-creator/sops-3.9.4')
    if not Path(sops).is_file():
        pytest.skip('SOPS executable required for encryption integration')
    doc = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'example', 'namespace': 'slai-app-prod'}, 'type': 'Opaque', 'stringData': {'password': 'test-only-value'}, 'data': {'key': 'dGVzdA=='}}
    raw = tmp_path / 'secrets.enc.yaml'
    raw.write_text(yaml.safe_dump(doc))
    result = subprocess.run([sops, '--encrypt', '--config', str(config), str(raw)], capture_output=True, text=True, check=True)
    encrypted = yaml.safe_load(result.stdout)
    for key in ['apiVersion', 'kind', 'metadata', 'type']:
        assert encrypted[key] == doc[key]
    assert encrypted['stringData']['password'].startswith('ENC[')
    assert encrypted['data']['key'].startswith('ENC[')
    assert encrypted['sops']['encrypted_regex'] == '^(data|stringData)$'
    raw.write_text(result.stdout)
    assert not main.ciphertext_errors(raw)
