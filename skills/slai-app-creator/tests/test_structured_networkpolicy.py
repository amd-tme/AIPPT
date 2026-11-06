import importlib.util
from pathlib import Path
import pytest
import yaml

root = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('netpol_validator', root / 'scripts/main.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixtures():
    policy = yaml.safe_load((root / 'assets/templates/networkpolicy.yaml.example').read_text().replace('YOUR_APP_NAME', 'example').replace('REPLACE_WITH_CURRENT_COLLECTOR_IPV4', '10.20.30.40'))
    deployment = {'spec': {'template': {'metadata': {'labels': {'app.kubernetes.io/name': 'example'}}, 'spec': {'containers': [{'ports': [{'containerPort': 8080}], 'env': [{'name': 'OTEL_EXPORTER_OTLP_ENDPOINT', 'value': 'http://collector:4317'}]}]}}}}
    return policy, deployment


def check(policy, deployment):
    return module._networkpolicy_errors(yaml.safe_dump(policy), yaml.safe_dump(deployment), Path('/deploy/slai-app-prod/example/networkpolicy.yaml'))


def test_valid_restricted_policy():
    assert check(*fixtures()) == []


@pytest.mark.parametrize('mutation', ['selector', 'all_ingress', 'split_ingress', 'all_egress', 'protocol', 'empty_pods'])
def test_rejects_weakened_policy(mutation):
    policy, deployment = fixtures()
    if mutation == 'selector': policy['spec']['podSelector'] = {'matchLabels': {'other': 'app'}}
    if mutation == 'all_ingress': policy['spec']['ingress'][0].pop('from')
    if mutation == 'split_ingress':
        peer = policy['spec']['ingress'][0]['from'][0]
        policy['spec']['ingress'][0]['from'] = [{k: v} for k, v in peer.items()]
    if mutation == 'all_egress': policy['spec']['egress'][1].pop('to')
    if mutation == 'broad_ip': policy['spec']['egress'][1]['to'][0]['ipBlock']['cidr'] = '0.0.0.0/0'
    if mutation == 'protocol': policy['spec']['ingress'][0]['ports'][0]['protocol'] = 'UDP'
    if mutation == 'empty_pods': policy['spec']['egress'][0]['to'][0]['podSelector'] = {}
    assert check(policy, deployment)


@pytest.mark.parametrize("malformed_input", ["policy", "deployment"])
def test_yaml_parser_diagnostic_never_quotes_manifest_contents(malformed_input):
    import secrets

    canary = "synthetic-" + secrets.token_hex(16)
    malformed = "password: [" + canary + "\n"
    policy, deployment = fixtures()
    policy_text = malformed if malformed_input == "policy" else yaml.safe_dump(policy)
    deployment_text = malformed if malformed_input == "deployment" else yaml.safe_dump(deployment)
    errors = module._networkpolicy_errors(
        policy_text, deployment_text, Path("/deploy/slai-app-prod/example/networkpolicy.yaml")
    )
    diagnostic = " ".join(errors)
    assert "invalid YAML" in diagnostic
    assert "line" in diagnostic and "column" in diagnostic
    assert canary not in diagnostic
    assert "password" not in diagnostic


def test_explicit_broad_egress_preserves_required_ports():
    policy, deployment = fixtures()
    rule = policy["spec"]["egress"][1]
    rule["to"][0]["ipBlock"]["cidr"] = "0.0.0.0/0"
    assert not check(policy, deployment)
    rule.pop("ports")
    assert check(policy, deployment)
