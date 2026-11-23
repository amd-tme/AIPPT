import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('hosted_authorize_helper', ROOT / 'scripts/authorize_image.py')
helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)


def files():
    return [{'path': name, 'content': 'signed-original-' + name} for name in sorted(helper.FILES)]


def test_handoff_is_complete_preserves_bytes_and_can_resume(tmp_path):
    tmp_path.chmod(0o700)
    helper.write_handoff(tmp_path, files())
    helper.write_handoff(tmp_path, files())
    for item in files():
        assert (tmp_path / item['path']).read_text() == item['content']


def test_handoff_rejects_conflicts_partial_response_and_symlinks(tmp_path):
    tmp_path.chmod(0o700)
    with pytest.raises(helper.ClientError):
        helper.write_handoff(tmp_path, files()[:2])
    (tmp_path / 'image-policy.yaml').write_text('different')
    with pytest.raises(helper.ClientError):
        helper.write_handoff(tmp_path, files())
    assert not (tmp_path / 'image-release.json').exists()
    (tmp_path / 'image-policy.yaml').unlink()
    victim = tmp_path / 'victim'; victim.write_text('keep')
    (tmp_path / 'image-policy.yaml').symlink_to(victim)
    with pytest.raises(OSError):
        helper.write_handoff(tmp_path, files())
    assert victim.read_text() == 'keep'


def test_pending_authorization_never_dispatches_again():
    class Client:
        calls = []
        def request(self, method, path):
            self.calls.append((method, path))
            return {'status': 'dispatch_pending'}
    client = Client()
    with pytest.raises(helper.ClientError, match='pending'):
        helper.wait(client, 'a' * 32, 0, 1)
    assert client.calls == [('GET', '/api/image-authorizations/' + 'a' * 32)]


def test_default_flow_has_no_app_repository_authorization_job():
    text = (ROOT / 'SKILL.md').read_text()
    assert 'scripts/authorize_image.py' in text
    assert "Run the app's existing-image authorization workflow" not in text
    template = (ROOT / 'assets/templates/authorize-existing-image.yml.example').read_text()
    assert 'jobs:' not in template
    assert 'Do not copy or dispatch' in template


@pytest.mark.parametrize('repository', [None, 'mkmhub.amd.com/hw-slaiapp-dev/localai'])
def test_authorization_helper_sends_explicit_consumer_repository_and_preserves_default_intent(tmp_path, monkeypatch, repository):
    tmp_path.chmod(0o700)
    seen = []
    class Client:
        def request(self, method, path, payload=None, **kwargs):
            if method == 'POST':
                seen.append(payload)
                return {'id': 'a' * 32}
            return {'status': 'authorized', 'files': files()}
    monkeypatch.setattr(helper, 'Client', Client)
    monkeypatch.setattr(helper, 'authenticate', lambda *args: None)
    args = [str(tmp_path), '--app-id', 'localai-router', '--source-repository', 'AMD-AABEL/hierax-horns-eval',
            '--source-repository-id', '1412234699', '--source-commit', 'b' * 40,
            '--image-tag', 'published', '--image-digest', 'sha256:' + 'c' * 64, '--no-browser']
    if repository: args += ['--image-repository', repository]
    assert helper.main(args) == 0
    assert seen[0]['app_id'] == 'localai-router'
    if repository: assert seen[0]['image_repository'] == repository
    else: assert 'image_repository' not in seen[0]
