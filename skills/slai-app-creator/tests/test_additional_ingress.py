import importlib.util
from pathlib import Path
import sys
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('all_ingress_policy', ROOT / 'scripts/ingress_policy.py')
policy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = policy
spec.loader.exec_module(policy)


def ingress():
    return {'apiVersion': 'networking.k8s.io/v1', 'kind': 'Ingress', 'metadata': {'name': 'demo-api', 'namespace': 'slai-app-prod'}, 'spec': {'rules': [{'host': 'demo.slai-app.amd.com', 'http': {'paths': [{'path': '/', 'pathType': 'Prefix', 'backend': {'service': {'name': 'demo', 'port': {'number': 80}}}}]}}], 'tls': [{'hosts': ['demo.slai-app.amd.com'], 'secretName': 'demo-tls'}]}}


def validate(tmp_path, doc):
    d = tmp_path / 'demo'; d.mkdir()
    # An embedded Ingress in a filename with no ingress prefix must be checked.
    (d / 'api-deployment.yaml').write_text(yaml.safe_dump({'kind': 'ConfigMap'}) + '---\n' + yaml.safe_dump(doc))
    return policy.validate_tree(ROOT, ROOT / 'scripts/ingress-policy.yaml', d, allocated_app_ids={'demo'})


def test_arbitrary_filename_multidoc_ingress(tmp_path):
    assert validate(tmp_path, ingress()) == []


@pytest.mark.parametrize('mutation', ['host', 'tls', 'class', 'default', 'snippet', 'auth', 'redirect', 'ssl'])
def test_reject_unsafe_embedded_ingress(tmp_path, mutation):
    doc = ingress()
    if mutation == 'host': doc['spec']['rules'][0]['host'] = 'victim.slai-app.amd.com'
    elif mutation == 'tls': doc['spec']['tls'][0]['secretName'] = 'victim-tls'
    elif mutation == 'class': doc['spec']['ingressClassName'] = 'other'
    elif mutation == 'default': doc['spec']['defaultBackend'] = {'service': {'name': 'victim', 'port': {'number': 80}}}
    else:
        key, value = {'snippet': ('configuration-snippet', 'proxy_pass http://victim;'), 'auth': ('auth-url', 'http://victim'), 'redirect': ('permanent-redirect', 'https://victim/'), 'ssl': ('ssl-redirect', 'false')}[mutation]
        doc['metadata']['annotations'] = {'nginx.ingress.kubernetes.io/' + key: value}
    assert validate(tmp_path, doc)



def test_bounded_worker_checks_additional_ingress():
    import json, subprocess
    doc = ingress()
    helper = ROOT / 'scripts/bundle_resources.py'
    payload = {'app_id': 'demo', 'files': [{'path': 'deploy/slai-app-prod/demo/api-ingress.yaml', 'content': yaml.safe_dump(doc)}]}
    def run():
        r = subprocess.run([sys.executable, str(helper), '--worker'], input=json.dumps(payload), text=True, capture_output=True, check=True)
        return json.loads(r.stdout)
    assert run() == []
    doc['spec']['rules'][0]['host'] = 'victim.slai-app.amd.com'
    payload['files'][0]['content'] = yaml.safe_dump(doc)
    assert any('host' in e for e in run())

@pytest.mark.parametrize('entry', yaml.safe_load((ROOT / 'scripts/ingress-policy.yaml').read_text())['grandfathered_routes'])
def test_each_grandfathered_route_preserves_reviewed_path_type(tmp_path, monkeypatch, entry):
    key = tuple(entry[k] for k in ('app_id','file','host','path','secret_name'))
    snapshot = {'version':1,'namespace':'slai-app-prod','standard':{'host_suffix':'slai-app.amd.com','path':'/','path_type':'Prefix','tls_secret_name':'slai-app-wildcard-tls'},'grandfathered_routes':[entry]}
    policy_file=tmp_path/'policy.yaml'; policy_file.write_text(yaml.safe_dump(snapshot))
    directory=tmp_path/entry['app_id']; directory.mkdir()
    name=entry['app_id'].replace('_','-')
    backend={'service':{'name':name,'port':{'name':'http'}}}
    for path_type in ('Exact','Prefix','ImplementationSpecific'):
        route=policy.Route(*key,path_type,backend,False)
        monkeypatch.setattr(policy,'collect_routes',lambda *a:([route],[]))
        errors=policy.validate_tree(tmp_path,policy_file,directory,allocated_app_ids={entry['app_id']})
        assert any('requires reviewed pathType' in e for e in errors)==(path_type != entry['path_type'])


def test_keycloak_retains_reviewed_routes_but_rejects_added_root(tmp_path, monkeypatch):
    snapshot, keys=policy.load_policy(ROOT/'scripts/ingress-policy.yaml')
    entries=[e for e in snapshot['grandfathered_routes'] if e['app_id']=='platform-sso-keycloak']
    backend={'service':{'name':'platform-sso-keycloak','port':{'number':80}}}
    routes=[policy.Route(*(e[k] for k in ('app_id','file','host','path','secret_name')),e['path_type'],backend,False) for e in entries]
    # Exercise path restrictions on the migrated exact-host binding.
    routes=[route._replace(secret_name='platform-sso-keycloak-tls') for route in routes]
    directory=tmp_path/'platform-sso-keycloak'; directory.mkdir()
    monkeypatch.setattr(policy,'collect_routes',lambda *a:(routes,[]))
    monkeypatch.setattr(policy,'managed_tls_target',lambda *a: {
        'hostname': 'sso.slai-app.amd.com', 'secret_name': 'platform-sso-keycloak-tls'})
    assert policy.validate_tree(tmp_path,ROOT/'scripts/ingress-policy.yaml',directory,allocated_app_ids={'platform-sso-keycloak'})==[]
    routes.append(policy.Route('platform-sso-keycloak','z-ingress.yaml','platform-sso-keycloak.slai-app.amd.com','/','slai-app-wildcard-tls','Prefix',backend,False))
    assert any('explicitly reviewed route' in e for e in policy.validate_tree(tmp_path,ROOT/'scripts/ingress-policy.yaml',directory,allocated_app_ids={'platform-sso-keycloak'}))
