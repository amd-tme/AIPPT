import json
from pathlib import Path
import yaml
import main


def test_legacy_deployment_requires_exact_app_baseline(tmp_path, monkeypatch):
    path=tmp_path/'ucode'/'deployment.yaml'
    doc={'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':'hosted-slai-ucode','namespace':'slai-app-prod'}}
    baseline=tmp_path/'baseline.json'
    monkeypatch.setenv('SLAI_REVIEWED_BASELINE_PATH',str(baseline))
    key='deploy/slai-app-prod/ucode/deployment.yaml'
    for files, accepted in [({},False),({key:yaml.safe_dump(doc)},True),({'deploy/slai-app-prod/other/deployment.yaml':yaml.safe_dump(doc)},False)]:
        baseline.write_text(json.dumps(files))
        assert (not main._bundle_resource_errors(doc,path,'ucode')) == accepted
    doc['metadata']['name']='hosted-slai-victim'
    assert main._bundle_resource_errors(doc,path,'ucode')
