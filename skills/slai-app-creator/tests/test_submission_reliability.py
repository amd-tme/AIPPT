import importlib.util
import json
import secrets
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('submission_helper', Path(__file__).parents[1]/'scripts/submit_app.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class FakeClient:
    token = secrets.token_urlsafe(24)
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value

@pytest.mark.parametrize('error', [m.TransportError('timeout'), m.HttpError(502), m.HttpError(503), m.HttpError(504)])
def test_uncertain_submission_retries_identical_body_and_key(error):
    c = FakeClient([error, {'id':'existing-record'}]); payload={'files':[]}; key='same-key-12345678'
    assert m.submit_once(c,payload,key)['id']=='existing-record'
    assert c.calls[0] == c.calls[1]
    assert c.calls[0][1]['idempotency_key']==key

@pytest.mark.parametrize('code',[400,401,403,409,429])
def test_rejections_do_not_retry(code):
    c=FakeClient([m.HttpError(code)])
    with pytest.raises(m.HttpError):m.submit_once(c,{},'same-key-12345678')
    assert len(c.calls)==1

def test_transport_retry_is_bounded():
    c=FakeClient([m.TransportError('timeout'),m.TransportError('timeout')])
    with pytest.raises(m.TransportError):m.submit_once(c,{},'same-key-12345678')
    assert len(c.calls)==2

def test_status_is_read_only_and_does_not_print_raw_diagnostics(capsys):
    c=FakeClient([{'schema_version':1,'submission':{'status':'merged'},'rollout':{'status':'in_progress','run_id':123},'diagnostics':{'secret':FakeClient.token},'pr':{'url':'https://untrusted.example/?token='+FakeClient.token}}])
    m.show_status(c,'record',True)
    out=capsys.readouterr().out; data=json.loads(out)
    assert data['rollout']['run_id']==123
    assert c.token not in out
    assert c.calls==[(('GET','/api/submissions/record/status'),{})]

def test_unsupported_status_schema_fails():
    with pytest.raises(m.ClientError):m.show_status(FakeClient([{'schema_version':99}]),'record')

class Response:
    def __init__(self,raw):self.raw=raw
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return self.raw[:n]
class Opener:
    def __init__(self,value):self.value=value;self.request=None
    def open(self,request,timeout):
        self.request=request
        if isinstance(self.value,Exception):raise self.value
        return Response(self.value)

def test_client_sets_idempotency_header_and_uses_canonical_endpoint():
    c=m.Client();c.opener=Opener(b'{"id":"record"}');c.token=secrets.token_urlsafe(24)
    c.request('POST','/api/submissions',{'files':[]},idempotency_key='same-key-12345678')
    assert c.opener.request.get_header('Idempotency-key')=='same-key-12345678'
    assert c.opener.request.full_url==m.SERVICE+'/api/submissions'

def test_client_bounds_response_size():
    c=m.Client();c.opener=Opener(b' '* (2*1024*1024+1))
    with pytest.raises(m.ClientError,match='size'):c.request('GET','/api/me')

def test_timeout_is_distinct_from_invalid_json():
    c=m.Client();c.opener=Opener(TimeoutError())
    with pytest.raises(m.TransportError,match='timed out'):c.request('GET','/api/me')
    c.opener=Opener(b'not json')
    with pytest.raises(m.ClientError,match='valid JSON'):c.request('GET','/api/me')

def test_retryable_processing_error_does_not_create_or_stop_submission(monkeypatch):
    c=FakeClient([{'status':'errored'},{'schema_version':1,'processing':{'retryable':True}},{'status':'merged'}])
    monkeypatch.setattr(m.time,'sleep',lambda _:None)
    m.wait_for_merge(c,'record',10,1)
    assert all(call[0][0]=='GET' for call in c.calls)

def test_terminal_processing_error_stops_without_mutation():
    c=FakeClient([{'status':'errored'},{'schema_version':1,'processing':{'retryable':False}}])
    with pytest.raises(m.ClientError,match='stopped'):m.wait_for_merge(c,'record',10,1)
    assert all(call[0][0]=='GET' for call in c.calls)


def test_malformed_status_values_are_unknown(capsys):
    c=FakeClient([{'schema_version':1,'rollout':{'status':[], 'jobs':[{'status':{},'conclusion':[]} ]}}])
    result=m.show_status(c,'record',True)
    assert result['rollout']['status']=='unknown'
    assert result['rollout']['jobs'][0]['status']=='unknown'


@pytest.mark.parametrize('code', ['authorization_rejected', 'recovery_required', 'attempt_limit', 'unsafe-secret-value'])
def test_status_retains_only_supported_failure_codes(code, capsys):
    c = FakeClient([{'schema_version': 1, 'submission': {'status': 'errored'}, 'processing': {'phase': 'requires_recovery', 'retryable': False, 'error_code': code}}])
    result = m.show_status(c, 'a' * 32)
    assert result['processing']['error_code'] == (code if code != 'unsafe-secret-value' else 'unknown')
    output = capsys.readouterr().out
    assert 'do not repost' in output
    assert 'unsafe-secret-value' not in output
