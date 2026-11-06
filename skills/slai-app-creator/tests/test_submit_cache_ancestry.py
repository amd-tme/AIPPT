"""Session credentials must stay inside descriptor-verified private cache dirs."""
import json
import os
from pathlib import Path
import stat

import pytest

import submit_app as submit


pytestmark = pytest.mark.skipif(os.name == 'nt', reason='POSIX descriptor and permission tests')


@pytest.fixture
def cached_session(tmp_path):
    path = tmp_path / 'trusted' / 'cache' / 'session.json'
    submit.save_session(path, 'old.access', 3600, 'old.refresh', 86400)
    return path


def test_cache_rejects_symlink_in_any_ancestor(cached_session, tmp_path):
    link = tmp_path / 'linked'
    link.symlink_to(cached_session.parent.parent, target_is_directory=True)
    aliased = link / 'cache' / cached_session.name
    assert submit.load_session(aliased) is None
    with pytest.raises((submit.ClientError, OSError)):
        submit.save_session(aliased, 'replacement.access', 3600)
    assert submit.load_session(cached_session) == 'old.access'


@pytest.mark.parametrize('mode', [0o775, 0o777, 0o1777])
def test_cache_rejects_writable_ancestors_without_changing_their_modes(cached_session, mode):
    if mode == 0o1777 and os.geteuid() == 0:
        pytest.skip('root-owned sticky ancestry is deliberately trusted')
    ancestor = cached_session.parent.parent
    ancestor.chmod(mode)
    assert submit.load_session(cached_session) is None
    with pytest.raises(submit.ClientError, match='ancestors'):
        submit.save_session(cached_session, 'replacement.access', 3600)
    assert stat.S_IMODE(ancestor.stat().st_mode) == mode


def test_cache_rejects_untrusted_owner_even_when_ancestor_is_not_writable(cached_session, monkeypatch):
    ancestor = cached_session.parent.parent.stat()
    real_fstat = os.fstat
    def foreign_owner(fd):
        info = real_fstat(fd)
        if (info.st_dev, info.st_ino) == (ancestor.st_dev, ancestor.st_ino):
            values = list(info)
            values[4] = os.geteuid() + 12345
            return os.stat_result(values)
        return info
    monkeypatch.setattr(submit.os, 'fstat', foreign_owner)
    assert submit.load_session(cached_session) is None
    with pytest.raises(submit.ClientError, match='ownership'):
        submit.save_session(cached_session, 'replacement.access', 3600)


def test_cache_accepts_root_owned_sticky_tmp_ancestry(tmp_path):
    shared = Path('/tmp')
    info = shared.stat()
    if info.st_uid != 0 or not info.st_mode & stat.S_ISVTX or shared not in tmp_path.parents:
        pytest.skip('requires pytest temp under root-owned sticky /tmp')
    path = tmp_path / 'private' / 'session.json'
    submit.save_session(path, 'access.value', 3600, 'refresh.value', 86400)
    assert submit.load_session(path) == 'access.value'
    assert submit.load_session(path, refresh=True) == 'refresh.value'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


@pytest.mark.parametrize('kind', ['symlink', 'hardlink'])
def test_cache_rejects_linked_leaf_without_changing_the_target(cached_session, kind):
    original = cached_session.with_name('original.json')
    cached_session.rename(original)
    if kind == 'symlink':
        cached_session.symlink_to(original)
    else:
        os.link(original, cached_session)
    before = original.read_bytes()
    assert submit.load_session(cached_session) is None
    with pytest.raises(submit.ClientError):
        submit.save_session(cached_session, 'replacement.access', 3600)
    assert original.read_bytes() == before


def test_cache_temporary_creation_uses_the_retained_directory_after_ancestor_redirect(
        cached_session, tmp_path, monkeypatch):
    outside = tmp_path / 'outside' / 'session.json'
    submit.save_session(outside, 'outside.access', 3600)
    outside_before = outside.read_bytes()
    moved = cached_session.parent.with_name('retained-cache')
    real_open = os.open
    redirected = False
    def redirect_before_create(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal redirected
        if flags & os.O_CREAT and not redirected:
            redirected = True
            cached_session.parent.rename(moved)
            cached_session.parent.symlink_to(outside.parent, target_is_directory=True)
        return real_open(path, flags, mode, dir_fd=dir_fd)
    monkeypatch.setattr(submit.os, 'open', redirect_before_create)
    monkeypatch.setattr(submit.os, 'supports_dir_fd', os.supports_dir_fd | {redirect_before_create})
    submit.save_session(cached_session, 'replacement.access', 3600)
    assert redirected
    assert outside.read_bytes() == outside_before
    assert json.loads((moved / 'session.json').read_text())['token'] == 'replacement.access'
    assert stat.S_IMODE((moved / 'session.json').stat().st_mode) == 0o600
    assert list(moved.iterdir()) == [moved / 'session.json']


@pytest.mark.parametrize('fail_replace', [False, True])
def test_cache_replace_and_cleanup_stay_pinned_after_ancestor_redirect(
        cached_session, tmp_path, monkeypatch, fail_replace):
    outside = tmp_path / 'outside' / 'session.json'
    submit.save_session(outside, 'outside.access', 3600)
    outside_before = outside.read_bytes()
    moved = cached_session.parent.with_name('retained-cache')
    real_replace = os.replace
    outside_temporary = None
    def redirect_at_replace(source, destination, **kwargs):
        nonlocal outside_temporary
        cached_session.parent.rename(moved)
        cached_session.parent.symlink_to(outside.parent, target_is_directory=True)
        outside_temporary = outside.parent / Path(source).name
        outside_temporary.write_text('outside file must not be replaced or removed')
        if fail_replace:
            raise OSError('synthetic replacement failure')
        return real_replace(source, destination, **kwargs)
    monkeypatch.setattr(submit.os, 'replace', redirect_at_replace)
    if fail_replace:
        with pytest.raises(OSError):
            submit.save_session(cached_session, 'replacement.access', 3600)
    else:
        submit.save_session(cached_session, 'replacement.access', 3600)
    assert outside.read_bytes() == outside_before
    assert outside_temporary.read_text() == 'outside file must not be replaced or removed'
    expected = 'old.access' if fail_replace else 'replacement.access'
    assert json.loads((moved / 'session.json').read_text())['token'] == expected
    assert list(moved.iterdir()) == [moved / 'session.json']


def test_cache_unavailable_posix_operations_fail_closed(cached_session, monkeypatch):
    monkeypatch.setattr(submit.os, 'supports_dir_fd', set())
    assert submit.load_session(cached_session) is None
    with pytest.raises(submit.ClientError, match='POSIX'):
        submit.save_session(cached_session, 'replacement.access', 3600)


def test_cache_temporary_name_collision_does_not_overwrite_or_remove_existing_file(cached_session, monkeypatch):
    collision = cached_session.parent / 'session-collision.tmp'
    collision.write_text('existing sibling must remain unchanged')
    monkeypatch.setattr(submit.secrets, 'token_hex', lambda count: 'collision')
    with pytest.raises(submit.ClientError, match='Cannot create'):
        submit.save_session(cached_session, 'replacement.access', 3600)
    assert collision.read_text() == 'existing sibling must remain unchanged'
    assert submit.load_session(cached_session) == 'old.access'


def test_cache_non_object_json_is_rejected_without_a_traceback(cached_session):
    cached_session.write_text('["invalid", "cache"]')
    assert submit.load_session(cached_session) is None


def test_windows_retains_in_memory_only_session_behavior(cached_session, monkeypatch):
    before = cached_session.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(submit.os, 'name', 'nt')
        assert submit.load_session(cached_session) is None
        assert submit.save_session(cached_session, 'replacement.access', 3600) is None
    assert cached_session.read_bytes() == before
