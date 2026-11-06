"""Stamp writes must stay on verified directory descriptors."""
import importlib.util
import os
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / 'scripts/lsf-push/private-stamp.py'
spec = importlib.util.spec_from_file_location('private_lsf_stamp', HELPER)
stamp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stamp)
EVIDENCE = {
    'full_image': 'harbor.example.test/project/app:slai-sc-' + 'a' * 40 + '-1-1',
    'image_digest': 'sha256:' + 'b' * 64,
}


def test_private_atomic_stamp_and_existing_owned_file(tmp_path):
    target = tmp_path / 'cache/harbor-last-image.env'
    stamp.write_stamp(target, EVIDENCE)
    assert target.stat().st_mode & 0o777 == 0o600
    assert 'IMAGE_DIGEST=' + EVIDENCE['image_digest'] in target.read_text()
    assert 'FULL_IMAGE=' + EVIDENCE['full_image'].rsplit(':', 1)[0] + '@' + EVIDENCE['image_digest'] in target.read_text()
    stamp.write_stamp(target, EVIDENCE)
    assert not list(target.parent.glob('.harbor-stamp-*'))


def test_symlink_parent_cannot_redirect_stamp(tmp_path):
    actual = tmp_path / 'actual'
    actual.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(OSError):
        stamp.write_stamp(link / 'stamp', EVIDENCE)
    assert not (actual / 'stamp').exists()


def test_group_writable_ancestor_is_rejected(tmp_path):
    hostile = tmp_path / 'hostile'
    hostile.mkdir(mode=0o770)
    hostile.chmod(0o770)
    with pytest.raises(ValueError, match='ancestors'):
        stamp.write_stamp(hostile / 'stamp', EVIDENCE)
    assert not (hostile / 'stamp').exists()


def test_existing_stamp_symlink_cannot_overwrite_target(tmp_path):
    victim = tmp_path / 'victim'
    victim.write_text('keep')
    link = tmp_path / 'stamp'
    link.symlink_to(victim)
    with pytest.raises(ValueError, match='existing stamp'):
        stamp.write_stamp(link, EVIDENCE)
    assert victim.read_text() == 'keep'


def test_existing_hardlinked_stamp_is_rejected(tmp_path):
    victim = tmp_path / 'victim'
    victim.write_text('keep')
    target = tmp_path / 'stamp'
    os.link(victim, target)
    with pytest.raises(ValueError, match='existing stamp'):
        stamp.write_stamp(target, EVIDENCE)
    assert victim.read_text() == 'keep'


def test_parent_replacement_does_not_redirect_open_directory(tmp_path, monkeypatch):
    parent = tmp_path / 'cache'
    parent.mkdir()
    relocated = tmp_path / 'original-cache'
    attacker = tmp_path / 'attacker'
    attacker.mkdir()
    original = stamp.open_parent

    def replaced(path):
        fd, name = original(path)
        parent.rename(relocated)
        parent.symlink_to(attacker, target_is_directory=True)
        return fd, name

    monkeypatch.setattr(stamp, 'open_parent', replaced)
    stamp.write_stamp(parent / 'stamp', EVIDENCE)
    assert (relocated / 'stamp').exists()
    assert not (attacker / 'stamp').exists()
