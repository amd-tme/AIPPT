from pathlib import Path
import yaml


def test_default_ingress_requires_controller_namespace_and_pods():
    path = Path(__file__).parents[1] / 'assets/templates/networkpolicy.yaml.example'
    policy = yaml.safe_load(path.read_text())
    for rule in policy['spec']['ingress']:
        assert rule['from']
        for source in rule['from']:
            assert source['namespaceSelector']['matchLabels']['kubernetes.io/metadata.name'] == 'kube-system'
            assert source['podSelector']['matchLabels']['app.kubernetes.io/component'] == 'controller'
