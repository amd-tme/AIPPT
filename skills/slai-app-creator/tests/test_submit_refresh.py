"""Portable hosted submission CLI tests; no live service or credentials."""
import importlib.util
import json
import secrets
import os
from pathlib import Path
import urllib.error

import pytest
import yaml

SPEC = importlib.util.spec_from_file_location("submit_app", Path(__file__).resolve().parents[1] / "scripts/submit_app.py")
submit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(submit)


@pytest.fixture
def manifests(tmp_path):
    root = tmp_path / "my-app"
    root.mkdir()
    for name in submit.REQUIRED:
        (root / name).write_text(yaml.safe_dump(valid_secret()) if name == "secrets.enc.yaml" else "kind: ConfigMap\n")
    (root / 'z-ingress.yaml').write_text(yaml.safe_dump({'kind': 'Ingress', 'metadata': {'name': 'my-app'}}))
    return root


def test_dry_run_without_credentials_or_network(manifests, monkeypatch, capsys):
    monkeypatch.setattr(submit, "authenticate", lambda *a: pytest.fail("auth during dry-run"))
    monkeypatch.setattr(submit, "Client", lambda: pytest.fail("network client during dry-run"))
    assert submit.main([str(manifests), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "SECRET-DO-NOT-SEND" not in output
    assert "secrets.raw.yaml" not in output
    assert set(json.loads(output)["files"]) == submit.REQUIRED | {'tls-policy.json'}


def test_pvc_missing_handoff_rejected_before_auth_or_network(manifests, monkeypatch, capsys):
    (manifests / 'pvc.yaml').write_text('apiVersion: v1\nkind: PersistentVolumeClaim\nmetadata:\n  name: my-app-data\n')
    monkeypatch.setattr(submit, 'authenticate', lambda *a: pytest.fail('auth before evidence rejection'))
    monkeypatch.setattr(submit, 'Client', lambda: pytest.fail('network before evidence rejection'))
    assert submit.main([str(manifests)]) == 1
    error = capsys.readouterr().err
    assert 'pvc.yaml' in error
    assert 'image-release.bundle.jsonl' in error


def test_symlink_manifest_rejected(manifests, tmp_path):
    target = tmp_path / "secret"
    target.write_text("credential")
    (manifests / "service.yaml").unlink()
    (manifests / "service.yaml").symlink_to(target)
    with pytest.raises(submit.ClientError, match="securely open manifest"):
        submit.bundle(manifests, "my-app")


def test_missing_credentials_no_browser(monkeypatch):
    monkeypatch.setattr(submit, "load_session", lambda p, **kwargs: None)
    with pytest.raises(submit.ClientError, match="without --no-browser"):
        submit.authenticate(submit.Client(), True, 1)


def test_http_error_does_not_expose_body():
    class Opener:
        def open(self, request, **kwargs):
            raise urllib.error.HTTPError(request.full_url, 502, "SECRET", {}, None)
    client = submit.Client()
    client.opener = Opener()
    with pytest.raises(submit.HttpError) as exc:
        client.request("GET", "/api/me")
    assert "SECRET" not in str(exc.value)


def test_auth_cookie_fixed_origin_and_redirect_refused():
    fixture_session = secrets.token_urlsafe(24)
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, *args):
            return b'{}'
    class Opener:
        def open(self, request, **kwargs):
            assert request.full_url == submit.SERVICE + "/api/me"
            assert request.headers["Cookie"] == submit.COOKIE + "=" + fixture_session
            return Response()
    client = submit.Client()
    client.token = fixture_session
    client.opener = Opener()
    client.request("GET", "/api/me")
    with pytest.raises(submit.ClientError):
        client.request("GET", "https://evil.example/api/me")
    assert submit.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example") is None


class FakeClient:
    def __init__(self, status="pr_opened", gate=None, conflict=False):
        self.status = status
        self.gate = gate or {"head_sha": "a" * 40, "mergeable": False, "merged": False}
        self.calls = []
        self.conflict = conflict
    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "POST":
            if self.conflict:
                raise submit.HttpError(409)
            return {"merged": True}
        if path.endswith("/merge"):
            return self.gate
        return {"status": self.status}


def test_pending_gate_returns_resumable_error():
    client = FakeClient()
    with pytest.raises(submit.ClientError, match="--submission-id abc"):
        submit.wait_for_merge(client, "abc", 0, 1)
    assert all(call[0] == "GET" for call in client.calls)


@pytest.mark.parametrize("status", ["failed", "validation_failed", "errored", "closed", "changes_requested"])
def test_failed_status_never_merges(status):
    client = FakeClient(status=status)
    with pytest.raises(submit.ClientError, match=status):
        submit.wait_for_merge(client, "abc", 0, 1)
    assert all(call[0] == "GET" for call in client.calls)


def test_merge_uses_observed_head():
    client = FakeClient(gate={"head_sha": "b" * 40, "mergeable": True})
    submit.wait_for_merge(client, "abc", 0, 1)
    assert client.calls[-1] == ("POST", "/api/submissions/abc/merge", {"head_sha": "b" * 40})


def test_stale_head_conflict_can_resume():
    client = FakeClient(gate={"head_sha": "b" * 40, "mergeable": True}, conflict=True)
    with pytest.raises(submit.ClientError, match="pending"):
        submit.wait_for_merge(client, "abc", 0, 1)


def test_resume_does_not_create_submission(monkeypatch):
    client = FakeClient(status="merged")
    monkeypatch.setattr(submit, "Client", lambda: client)
    monkeypatch.setattr(submit, "authenticate", lambda *a: None)
    assert submit.main(["--submission-id", "abc"]) == 0
    assert client.calls == [("GET", "/api/submissions/abc", None)]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission checks")
def test_cache_secure_and_scoped(tmp_path):
    path = tmp_path / "private" / "session.json"
    submit.save_session(path, "session.token", 3600)
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert submit.load_session(path) == "session.token"
    data = json.loads(path.read_text())
    data["service"] = "https://another.example"
    path.write_text(json.dumps(data))
    assert submit.load_session(path) is None
    data["service"] = submit.SERVICE
    path.write_text(json.dumps(data))
    path.chmod(0o644)
    assert submit.load_session(path) is None


def test_logs_read_only_and_bounded(monkeypatch, capsys):
    class Logs:
        token = None
        def request(self, method, path, payload=None):
            assert (method, path, payload) == ("GET", "/api/submissions/abc/logs", None)
            return {"status": "completed", "conclusion": "success", "jobs": [{"name": "deploy", "status": "completed", "log": "\x1b[31m" + "x" * 100000}]}
    monkeypatch.setattr(submit, "Client", Logs)
    monkeypatch.setattr(submit, "authenticate", lambda *a: None)
    assert submit.main(["--submission-id", "abc", "--logs"]) == 0
    output = capsys.readouterr().out
    assert "\x1b" not in output
    assert len(output) < 66000
    assert "Raw workflow logs omitted" in output


def test_hosted_pairing_binds_verifier_and_keeps_credentials_out_of_output(monkeypatch, tmp_path, capsys):
    import base64
    import hashlib
    opened = []
    class LoginClient:
        token = None
        challenge = None
        def request(self, method, path, payload=None):
            assert method == "POST"
            if path == "/auth/cli/pair":
                self.challenge = payload["challenge"]
                return {"code": "a" * 43, "verification_path": "/auth/cli/authorize?code=" + "a" * 43}
            assert path == "/auth/cli/poll"
            assert payload["code"] == "a" * 43
            calculated = base64.urlsafe_b64encode(hashlib.sha256(payload["verifier"].encode()).digest()).rstrip(b"=").decode()
            assert calculated == self.challenge
            self.verifier = payload["verifier"]
            return {"status": "complete", "session_token": "token.session", "expires_in": 3600}
    monkeypatch.setattr(submit.webbrowser, "open", opened.append)
    monkeypatch.setattr(submit, "cache_path", lambda: tmp_path / "cache" / "session.json")
    client = LoginClient()
    submit.browser_login(client, 5)
    assert opened == [submit.SERVICE + "/auth/cli/authorize?code=" + "a" * 43]
    assert client.token == "token.session"
    output = capsys.readouterr().out
    assert client.verifier not in output
    assert client.token not in output


def test_forbidden_error_guides_platform_maintainer():
    error = submit.HttpError(403)
    assert 'platform maintainer' in str(error)
    assert 'App permissions and branch protection' in str(error)


def test_merge_feedback_prints_only_changed_sanitized_reason(monkeypatch, capsys):
    fixture_session = secrets.token_urlsafe(24)
    class Gates(FakeClient):
        token = fixture_session
        reasons = iter(['awaiting review\x1b[31m ' + fixture_session,
                        'awaiting review\x1b[31m ' + fixture_session, 'checks pending', 'checks passed'])
        def request(self, method, path, payload=None):
            if path.endswith('/merge') and method == 'GET':
                reason = next(self.reasons)
                return {'reason': reason, 'merged': reason == 'checks passed'}
            return {'status': 'pr_opened'}
    monkeypatch.setattr(submit.time, 'sleep', lambda seconds: None)
    submit.wait_for_merge(Gates(), 'abc', 5, 1)
    output = capsys.readouterr().out
    assert output.count('awaiting review') == 1
    assert 'checks pending' in output
    assert 'checks passed' in output
    assert fixture_session not in output
    assert '\x1b' not in output


def test_pending_logs_explain_actual_reason(capsys):
    class Logs:
        token = None
        def request(self, *args):
            return {'status': 'pending', 'reason': 'pull request has not merged', 'jobs': []}
    submit.show_logs(Logs(), 'abc')
    output = capsys.readouterr().out
    assert 'Deployment status: pending' in output
    assert 'Deployment has not started' not in output


def test_feedback_is_bounded_and_redacts_token_fields():
    client = submit.Client()
    reason = submit.safe_reason('Bearer confidential token=private ' + 'a' * 1000, client)
    assert 'confidential' not in reason
    assert 'private' not in reason
    assert len(reason) <= 500

@pytest.mark.parametrize('expired', [True,False])
def test_refresh_after_expired_or_rejected_access_token(tmp_path,monkeypatch,expired):
    cache=tmp_path/'private'/'session.json'
    monkeypatch.setattr(submit,'cache_path',lambda:cache)
    submit.save_session(cache,'old-at',-1 if expired else 3600,'old-rt',86400)
    class Client:
        token=None
        calls=[]
        def request(self,method,path,payload=None):
            self.calls.append((method,path))
            if path=='/api/me': raise submit.HttpError(401)
            assert self.token is None
            assert payload=={'refresh_token':'old-rt'}
            return {'session_token':'new-at','expires_in':3600,'refresh_token':'new-rt','refresh_expires_in':86400}
    client=Client()
    submit.authenticate(client,True,1)
    assert client.token=='new-at'
    assert submit.load_session(cache)=='new-at'
    assert submit.load_session(cache,refresh=True)=='new-rt'
    assert client.calls[-1]==('POST','/auth/refresh')


def test_refresh_transport_failure_does_not_start_login(tmp_path,monkeypatch):
    cache=tmp_path/'private'/'session.json'
    monkeypatch.setattr(submit,'cache_path',lambda:cache)
    submit.save_session(cache,'old-at',-1,'old-rt',86400)
    monkeypatch.setattr(submit,'browser_login',lambda *a:pytest.fail('unexpected login'))
    class Client:
        def request(self,*a): raise submit.HttpError(503)
    with pytest.raises(submit.HttpError): submit.authenticate(Client(),False,1)
    assert submit.load_session(cache,refresh=True)=='old-rt'


def valid_secret():
    scripts=Path(__file__).resolve().parents[1]
    recipient=yaml.safe_load((scripts/'assets/platform.sops.yaml').read_text())['creation_rules'][0]['age']
    enc='ENC[AES256_GCM,data:dGVzdA==,iv:aXY=,tag:dGFn,type:str]'
    return {'kind':'Secret','stringData':{'fixture':enc},'sops':{'mac':enc,'age':[{'recipient':recipient,'enc':'synthetic wrapped key'}],'encrypted_regex':'^(data|stringData)$','version':'3.9.4','lastmodified':'2026-10-20T00:00:00Z'}}


@pytest.mark.parametrize('name', ['secrets.yaml','secrets.enc.yaml','api-deployment.yaml'])
def test_plaintext_secret_rejected_before_auth_or_network(manifests,monkeypatch,name,capsys):
    (manifests/name).write_text('kind: Secret\nstringData:\n  fixture: DO-NOT-UPLOAD\n')
    monkeypatch.setattr(submit,'authenticate',lambda *a:pytest.fail('authentication before secret rejection'))
    monkeypatch.setattr(submit,'Client',lambda:pytest.fail('network before secret rejection'))
    assert submit.main([str(manifests)])==1
    assert 'DO-NOT-UPLOAD' not in capsys.readouterr().err


def test_wrong_sops_recipient_rejected_before_upload(manifests):
    doc=valid_secret();doc['sops']['age'][0]['recipient']='age1untrusted'
    (manifests/'secrets.enc.yaml').write_text(yaml.safe_dump(doc))
    with pytest.raises(submit.ClientError,match='before upload'): submit.bundle(manifests,'my-app')


@pytest.mark.parametrize('wrapper', ['list','sequence','typed'])
def test_nested_plaintext_secret_rejected_before_upload(manifests,monkeypatch,wrapper):
    secret={'kind':'Secret','stringData':{'fixture':'DO-NOT-UPLOAD'}}
    doc={'apiVersion':'v1','kind':'SecretList' if wrapper=='typed' else 'List','items':[secret]} if wrapper!='sequence' else [secret]
    (manifests/'api-deployment.yaml').write_text(yaml.safe_dump(doc))
    monkeypatch.setattr(submit,'authenticate',lambda *a:pytest.fail('authentication before rejection'))
    monkeypatch.setattr(submit,'Client',lambda:pytest.fail('network before rejection'))
    assert submit.main([str(manifests)])==1


def test_secret_worker_ignores_hostile_pythonpath(manifests, tmp_path, monkeypatch):
    injection = tmp_path / 'imports'
    injection.mkdir()
    marker = tmp_path / 'payload-exposed'
    (injection / 'sitecustomize.py').write_text(
        'import os, sys\n'
        + f'open({str(marker)!r}, "wb").write(sys.stdin.buffer.read())\n'
        + 'print("{\"valid\": true}")\nos._exit(0)\n'
    )
    monkeypatch.setenv('PYTHONPATH', str(injection))
    (manifests / 'api-secret.yaml').write_text('kind: Secret\nstringData:\n  password: DO-NOT-UPLOAD\n')
    with pytest.raises(submit.ClientError, match='before upload'):
        submit.bundle(manifests, 'my-app')
    assert not marker.exists()
