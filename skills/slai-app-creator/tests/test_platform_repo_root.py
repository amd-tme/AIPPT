from pathlib import Path
import subprocess
import pytest
import main


def checkout(tmp_path):
    root = tmp_path / 'platform'
    root.mkdir(mode=0o700, parents=True)
    subprocess.run(['git', '-c', 'core.sharedRepository=false', 'init', '-q', str(root)], check=True)
    subprocess.run(['git', '-C', str(root), 'remote', 'add', 'origin', 'https://github.com/AMD-SLAI/slai-app-platform.git'], check=True)
    for path in (root / '.git').rglob('*'):
        path.chmod(0o700 if path.is_dir() else 0o600)
    for name in ('scripts', 'config'):
        (root / name).mkdir(mode=0o700)
    return root


def test_external_helper_delegates_to_fresh_pinned_source(tmp_path, monkeypatch):
    import prepare_platform_checkout
    monkeypatch.setattr(main, '__file__', str(tmp_path / 'external/skills/app/scripts/main.py'))
    expected = checkout(tmp_path)
    monkeypatch.setattr(prepare_platform_checkout, 'trusted_validator_checkout', lambda: expected)
    monkeypatch.setenv('SLAI_PLATFORM_CLONE_DIR', str(tmp_path / 'caller-untrusted'))
    assert main.platform_repo_root() == expected


def test_external_helper_propagates_source_validation_failure(tmp_path, monkeypatch):
    import prepare_platform_checkout
    monkeypatch.setattr(main, '__file__', str(tmp_path / 'external/skills/app/scripts/main.py'))
    def reject():
        raise ValueError('source provenance rejected')
    monkeypatch.setattr(prepare_platform_checkout, 'trusted_validator_checkout', reject)
    monkeypatch.setenv('SLAI_PLATFORM_CLONE_DIR', str(tmp_path / 'caller-untrusted'))
    with pytest.raises(ValueError, match='source provenance'):
        main.platform_repo_root()


def test_shipped_image_requires_explicit_mode_and_integrity_verification(monkeypatch):
    import hosted_validator_provenance
    root = Path('/opt/slai-app-platform')
    monkeypatch.setattr(main, '__file__', str(root / 'skills/slai-app-creator/scripts/main.py'))
    monkeypatch.setenv('SLAI_HOSTED_VALIDATOR_MODE', 'immutable-image')
    verified = []
    monkeypatch.setattr(hosted_validator_provenance, 'verify_hosted_root', lambda path: verified.append(path) or root)
    assert main.platform_repo_root() == root
    assert verified == [root]


def test_nested_repository_platform_root(tmp_path,monkeypatch):
    import prepare_platform_checkout
    root=tmp_path/'platform';(root/'scripts').mkdir(parents=True)
    (root/'scripts/validate-ingress-policy.py').write_text('# reviewed validator')
    path=root/'skills/slai-app-creator/scripts/main.py';path.parent.mkdir(parents=True);path.touch()
    monkeypatch.setattr(main,'__file__',str(path))
    expected = checkout(tmp_path / 'verified')
    selected = []
    monkeypatch.setattr(prepare_platform_checkout, 'trusted_validator_checkout', lambda: selected.append(True) or expected)
    monkeypatch.setenv('SLAI_PLATFORM_CLONE_DIR', str(root))
    assert main.platform_repo_root() == expected
    assert selected == [True]


def test_opt_path_alone_does_not_establish_source_authority(tmp_path, monkeypatch):
    import prepare_platform_checkout
    monkeypatch.setattr(main, '__file__', '/opt/slai-app-platform/skills/slai-app-creator/scripts/main.py')
    monkeypatch.delenv('SLAI_HOSTED_VALIDATOR_MODE', raising=False)
    monkeypatch.setenv('SLAI_PLATFORM_CLONE_DIR', '/untrusted/handoff')
    expected = checkout(tmp_path)
    monkeypatch.setattr(prepare_platform_checkout, 'trusted_validator_checkout', lambda: expected)
    assert main.platform_repo_root() == expected


def test_operator_mode_cannot_enable_a_caller_controlled_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(main, '__file__', str(tmp_path / 'external/skills/app/scripts/main.py'))
    monkeypatch.setenv('SLAI_HOSTED_VALIDATOR_MODE', 'immutable-image')
    with pytest.raises(ValueError, match='fixed protected image root'):
        main.platform_repo_root()


def test_hosted_integrity_error_is_fail_closed(monkeypatch):
    import hosted_validator_provenance
    monkeypatch.setattr(main, '__file__', '/opt/slai-app-platform/skills/slai-app-creator/scripts/main.py')
    monkeypatch.setenv('SLAI_HOSTED_VALIDATOR_MODE', 'immutable-image')
    def reject(root):
        raise ValueError('integrity verification failed')
    monkeypatch.setattr(hosted_validator_provenance, 'verify_hosted_root', reject)
    with pytest.raises(ValueError, match='integrity'):
        main.platform_repo_root()


def test_parser_worker_receives_no_client_checkout_or_authentication_env(monkeypatch):
    monkeypatch.setenv('SLAI_HOSTED_VALIDATOR_MODE', 'immutable-image')
    monkeypatch.setenv('SLAI_PLATFORM_CLONE_DIR', '/caller/untrusted')
    monkeypatch.setenv('GH_TOKEN', 'non-secret-fixture')
    environment = main._parser_environment()
    assert environment['SLAI_HOSTED_VALIDATOR_MODE'] == 'immutable-image'
    assert 'SLAI_PLATFORM_CLONE_DIR' not in environment
    assert 'GH_TOKEN' not in environment
