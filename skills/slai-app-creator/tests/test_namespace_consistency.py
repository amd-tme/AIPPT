import copy
from pathlib import Path
import yaml
import main
from test_ciphertext_validation import VALID
from test_manifest_validation import _bundle, _run


def test_deployment_cannot_claim_production_from_nonproduction_bundle():
    text = 'kind: Deployment\nmetadata: {namespace: slai-app-prod}\nspec:\n  template:\n    spec:\n      containers: [{name: app, image: example:mutable}]\n'
    errors, _ = main._deployment_reference_errors(text, Path('/deploy/test-ns/app/deployment.yaml'))
    assert 'namespace must match' in ' '.join(errors)


def test_service_namespace_mismatch_fails_bundle_validation(tmp_path):
    bundle = _bundle(tmp_path)
    (bundle / 'service.yaml').write_text('kind: Service\nmetadata: {namespace: slai-app-prod}\n')
    result = _run(bundle)
    assert result.returncode != 0
    assert 'service.yaml: manifest namespace must match' in result.stderr


def test_list_items_cannot_hide_namespace_mismatch():
    errors = main._namespace_errors({'kind': 'List', 'items': [
        {'kind': 'Service', 'metadata': {'namespace': 'slai-app-prod'}}]}, Path('extra.yaml'), 'test-ns')
    assert errors


def test_ciphertext_all_documents_match_bundle_namespace(tmp_path):
    path = tmp_path / 'secrets.enc.yaml'
    good = copy.deepcopy(VALID)
    good['metadata'] = {'namespace': 'test-ns'}
    bad = copy.deepcopy(VALID)
    bad['metadata'] = {'namespace': 'slai-app-prod'}
    path.write_text(yaml.safe_dump_all([good, bad]))
    assert 'namespace must match' in ' '.join(main.ciphertext_errors(path, 'test-ns'))
    path.write_text(yaml.safe_dump_all([good, good]))
    assert not main.ciphertext_errors(path, 'test-ns')


def test_additional_policy_cannot_override_validated_policy(tmp_path):
    bundle = _bundle(tmp_path)
    (bundle / 'extra-policy.yaml').write_text('apiVersion: networking.k8s.io/v1\nkind: NetworkPolicy\nspec: {ingress: [{}]}\n')
    result = _run(bundle)
    assert result.returncode != 0
    assert 'namespace' in result.stderr or 'NetworkPolicy' in result.stderr


def test_canonical_filename_cannot_hide_other_resource_kind():
    errors = main._bundle_resource_errors({'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy'}, Path('service.yaml'))
    assert errors


def test_list_and_plaintext_secret_are_rejected():
    for document in (
                     {'apiVersion': 'v1', 'kind': 'List', 'items': []},
                     {'apiVersion': 'v1', 'kind': 'Secret'}):
        assert main._bundle_resource_errors(document, Path('extra.yaml'))


def test_additional_nonworkload_resources_are_supported():
    for kind in ('ConfigMap', 'PersistentVolumeClaim'):
        assert not main._bundle_resource_errors({'apiVersion': 'v1', 'kind': kind, 'spec': {'storageClassName': 'nfs-network'}}, Path('extra.yaml'))


def test_missing_namespace_is_rejected_for_manifests_and_secrets(tmp_path):
    assert main._namespace_errors({'kind': 'Service'}, Path('service.yaml'), 'test-ns')
    path = tmp_path / 'secrets.enc.yaml'
    path.write_text(yaml.safe_dump(VALID))
    assert 'namespace must match' in ' '.join(main.ciphertext_errors(path, 'test-ns'))


def test_supported_additional_workload_kinds_reach_shared_policy_validation():
    for api,kind in [('apps/v1','Deployment'),('apps/v1','StatefulSet'),('apps/v1','DaemonSet'),('batch/v1','Job'),('batch/v1','CronJob')]:
        assert main._bundle_resource_errors({'apiVersion':api,'kind':kind},Path('worker.yaml')) == []
    # Admission by kind is followed by the bounded resource policy, not approval.
    from bundle_resources import _resource_errors
    from types import SimpleNamespace
    content = 'apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: demo-worker, namespace: slai-app-prod}\nspec: {}\n'
    assert _resource_errors([SimpleNamespace(path='deploy/slai-app-prod/demo/worker.yaml',content=content)],'demo')
