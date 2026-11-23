from pathlib import Path
from types import SimpleNamespace
import pytest
import yaml
from bundle_resources import resource_errors


def workload(kind):
    container={'name':'app','image':'mkmhub.amd.com/hw-slaiapp-dev/example@sha256:'+'1'*64,
               'securityContext':{'allowPrivilegeEscalation':False,'runAsNonRoot':True,'capabilities':{'drop':['ALL']},'seccompProfile':{'type':'RuntimeDefault'}}}
    pod={'automountServiceAccountToken':False,'containers':[container],'imagePullSecrets':[{'name':'example-harbor-pull'}]}
    spec={'selector':{'matchLabels':{'app.kubernetes.io/name':'example'}},'template':{'metadata':{'labels':{'app.kubernetes.io/name':'example'}},'spec':pod}}
    if kind=='CronJob':spec={'schedule':'0 * * * *','jobTemplate':{'spec':spec}}
    api='batch/v1' if kind in ('Job','CronJob') else 'apps/v1'
    return {'apiVersion':api,'kind':kind,'metadata':{'name':'example-worker','namespace':'slai-app-prod'},'spec':spec},pod,container


@pytest.mark.parametrize('kind',['Deployment','StatefulSet','DaemonSet','Job','CronJob'])
@pytest.mark.parametrize('location',['env','envFrom','volume','projected'])
def test_pull_secret_cannot_be_application_data(kind,location):
    doc,pod,container=workload(kind)
    file=lambda:SimpleNamespace(path='/example/worker.yaml',content=yaml.safe_dump(doc))
    assert not resource_errors([file()],'example')
    if location=='env':container['env']=[{'name':'TOKEN','valueFrom':{'secretKeyRef':{'name':'example-harbor-pull','key':'token'}}}]
    elif location=='envFrom':container['envFrom']=[{'secretRef':{'name':'example-harbor-pull'}}]
    elif location=='volume':pod['volumes']=[{'name':'data','secret':{'secretName':'example-harbor-pull'}}]
    else:pod['volumes']=[{'name':'data','projected':{'sources':[{'secret':{'name':'example-harbor-pull'}}]}}]
    assert any('restricted to imagePullSecrets' in error for error in resource_errors([file()],'example'))
