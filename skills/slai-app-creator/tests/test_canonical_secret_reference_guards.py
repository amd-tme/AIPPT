"""Exercise canonical reference validation without the hosted bundle guard."""
import pytest

import main


def secret_reference(context, name):
    if context == 'env':
        return {'containers': [{'env': [{'name': 'VALUE', 'valueFrom': {'secretKeyRef': {'name': name, 'key': 'value'}}}]}]}
    if context == 'envFrom':
        return {'initContainers': [{'envFrom': [{'secretRef': {'name': name}}]}]}
    if context == 'volume':
        return {'volumes': [{'name': 'credentials', 'secret': {'secretName': name}}]}
    if context == 'projected':
        return {'volumes': [{'name': 'credentials', 'projected': {'sources': [{'secret': {'name': name}}]}}]}
    if context == 'csi':
        return {'volumes': [{'name': 'credentials', 'csi': {'driver': 'fixture.example', 'nodePublishSecretRef': {'name': name}}}]}
    raise AssertionError('unknown test context')


@pytest.fixture
def deployment(tmp_path):
    app = tmp_path / 'new-app'
    app.mkdir()
    return app / 'deployment.yaml'


@pytest.mark.parametrize('context', ['env', 'envFrom', 'volume', 'projected', 'csi'])
def test_canonical_guard_blocks_harbor_pull_credentials_outside_image_pull(deployment, context):
    errors = main._secret_reference_errors(secret_reference(context, 'new-app-harbor-pull'), deployment)
    assert any('harbor-pull Secret is restricted to imagePullSecrets' in error for error in errors)


def test_canonical_guard_accepts_the_app_image_pull_secret(deployment):
    assert main._secret_reference_errors({'imagePullSecrets': [{'name': 'new-app-harbor-pull'}]}, deployment) == []


@pytest.mark.parametrize('context', ['env', 'envFrom', 'volume', 'projected', 'csi'])
@pytest.mark.parametrize('has_policy', [False, True])
def test_platform_tls_secret_never_enters_app_pods(deployment, context, has_policy):
    if has_policy:
        (deployment.parent / 'tls-policy.json').write_text('{}')
    errors = main._secret_reference_errors(secret_reference(context, 'new-app-tls'), deployment)
    assert any('platform-managed TLS private keys' in error for error in errors)


@pytest.mark.parametrize('context', ['env', 'envFrom', 'volume', 'projected', 'csi'])
@pytest.mark.parametrize('has_policy', [False, True])
def test_bounded_guard_blocks_tls_secret_even_with_exact_baseline(context, has_policy):
    from types import SimpleNamespace
    import bundle_resources
    import yaml
    path = 'deploy/slai-app-prod/new-app/deployment.yaml'
    document = {'apiVersion': 'apps/v1', 'kind': 'Deployment',
                'metadata': {'name': 'new-app', 'namespace': 'slai-app-prod'},
                'spec': {'template': {'spec': secret_reference(context, 'new-app-tls')}}}
    content = yaml.safe_dump(document)
    files = [SimpleNamespace(path=path, content=content)]
    if has_policy:
        files.append(SimpleNamespace(path='deploy/slai-app-prod/new-app/tls-policy.json', content='{}'))
    errors = bundle_resources.resource_errors(files, 'new-app', baseline_files={path: content})
    assert any('platform-managed TLS private keys' in error for error in errors)


@pytest.mark.parametrize('context', ['env', 'envFrom', 'volume', 'projected'])
def test_canonical_guard_retains_normal_app_secret_references(deployment, context):
    assert main._secret_reference_errors(secret_reference(context, 'new-app-settings'), deployment) == []


@pytest.mark.parametrize('name', ['other-app-harbor-pull', 'new-app-settings'])
def test_canonical_guard_keeps_image_pull_secret_identity_restricted(deployment, name):
    assert main._secret_reference_errors({'imagePullSecrets': [{'name': name}]}, deployment)


@pytest.mark.parametrize('target,message', [('new-app-harbor-pull', 'harbor-pull Secret is restricted'),
    ('new-app-tls', 'platform-managed TLS private keys'), ('another-app-settings', 'must be application-owned')])
def test_volume_decoy_name_cannot_hide_the_actual_secret_name(deployment, target, message):
    (deployment.parent / 'tls-policy.json').write_text('{}')
    pod = secret_reference('volume', target)
    pod['volumes'][0]['secret']['name'] = 'new-app-settings'
    errors = main._secret_reference_errors(pod, deployment)
    assert any(message in error for error in errors)
    assert any('unsupported identity field' in error for error in errors)


@pytest.mark.parametrize('context', ['env', 'envFrom', 'projected', 'csi'])
def test_name_based_references_cannot_select_a_secret_name_fallback(deployment, context):
    pod = secret_reference(context, 'new-app-settings')
    def conflict(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {'secretKeyRef', 'secretRef', 'secret', 'nodePublishSecretRef'}:
                    child['secretName'] = child.pop('name')
                else:
                    conflict(child)
        elif isinstance(value, list):
            for child in value:
                conflict(child)
    conflict(pod)
    assert any('unsupported identity field' in error for error in main._secret_reference_errors(pod, deployment))


def test_volume_secret_requires_its_kubernetes_secret_name_field(deployment):
    pod = {'volumes': [{'name': 'credentials', 'secret': {'name': 'new-app-settings'}}]}
    assert any('unsupported identity field' in error for error in main._secret_reference_errors(pod, deployment))


@pytest.mark.parametrize('target', ['new-app-harbor-pull', 'another-app-settings'])
def test_bounded_hosted_guard_also_checks_the_effective_volume_secret_name(target):
    from types import SimpleNamespace
    import bundle_resources
    import yaml
    pod = secret_reference('volume', target)
    pod['volumes'][0]['secret']['name'] = 'new-app-settings'
    document = {'apiVersion': 'apps/v1', 'kind': 'Deployment',
                'metadata': {'name': 'new-app', 'namespace': 'slai-app-prod'},
                'spec': {'template': {'spec': pod}}}
    errors = bundle_resources.resource_errors([SimpleNamespace(path='deployment.yaml', content=yaml.safe_dump(document))], 'new-app')
    message = 'harbor-pull Secret is restricted' if target == 'new-app-harbor-pull' else 'must be application-owned'
    assert any(message in error for error in errors)
