from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
import yaml
import main
from bundle_resources import resource_errors, service_spec_errors


def service(app='example'):
    return {'apiVersion':'v1','kind':'Service','metadata':{'name':app+'-amqps-lb','namespace':'slai-app-prod'}, 'spec':{'type':'LoadBalancer','selector':{'app.kubernetes.io/name':app},'ports':[{'name':'amqps','port':5671,'targetPort':'amqps'}]}}


def test_general_loadbalancer_and_rabbit(monkeypatch):
    monkeypatch.setattr(main, "_trusted_allocated_app_ids", lambda: {"example", "rabbit"})
    for doc, app in [(service(),'example'),(service('rabbit'),'rabbit')]:
        path=Path('/deploy/slai-app-prod')/app/'service-amqps-lb.yaml'
        assert not main._bundle_resource_errors(doc,path,app)
        assert not resource_errors([SimpleNamespace(path=str(path),content=yaml.safe_dump(doc))],app)
        canonical=deepcopy(doc);canonical['metadata']['name']=app
        assert not main._bundle_resource_errors(canonical,path.with_name('service.yaml'),app)


@pytest.mark.parametrize('change',[{'type':'NodePort'},{'type':'ExternalName'},{'externalIPs':['10.1.2.3']},{'ports':[{'port':0}]},{'ports':[{'port':5671,'nodePort':30001}]},{'ports':[{'port':5671,'targetPort':'bad_name'}]}])
def test_unsupported_service_exposure(change):
    doc=service();doc['spec'].update(change)
    assert service_spec_errors(doc['spec'])
    assert resource_errors([SimpleNamespace(path='/example/service-lb.yaml',content=yaml.safe_dump(doc))],'example')


def test_foreign_selector_and_identity_rejected():
    for field in ['selector','name']:
        doc=service()
        if field=='selector':doc['spec']['selector']['app.kubernetes.io/name']='victim'
        else:doc['metadata']['name']='victim-lb'
        assert resource_errors([SimpleNamespace(path='/example/service-lb.yaml',content=yaml.safe_dump(doc))],'example')
