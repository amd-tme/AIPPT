"""Managed NFS ownership must not block private LSF caches or image stamps."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize("helper,function", [
    ("lsf-build/scripts/private-build-cache.py", "open_cache"),
    ("lsf-push/private-stamp.py", "open_parent"),
])
def test_foreign_owned_mount_accepts_private_child(tmp_path, monkeypatch, helper, function):
    spec = importlib.util.spec_from_file_location("nfs_helper", ROOT / "scripts" / helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    mount = tmp_path / "nfs"
    mount.mkdir(mode=0o755)
    home = mount / "home"
    home.mkdir(mode=0o750)
    monkeypatch.setenv("HOME", str(home))
    private = home / "private"
    private.mkdir(mode=0o700)
    real_fstat = os.fstat
    inode = mount.stat().st_ino
    def nfs_fstat(fd):
        info = real_fstat(fd)
        if info.st_ino == inode:
            return SimpleNamespace(st_uid=65534, st_mode=info.st_mode)
        return info
    monkeypatch.setattr(module.os, "fstat", nfs_fstat)
    argument = private if function == "open_cache" else private / "stamp"
    result = getattr(module, function)(argument)
    os.close(result if isinstance(result, int) else result[0])
    home.chmod(0o777)
    with pytest.raises(ValueError):
        getattr(module, function)(argument)

@pytest.mark.parametrize("helper,function", [
    ("lsf-build/scripts/private-build-cache.py", "open_cache"),
    ("lsf-push/private-stamp.py", "open_parent"),
])
def test_foreign_owned_ancestor_outside_home_is_rejected(tmp_path, monkeypatch, helper, function):
    spec = importlib.util.spec_from_file_location("external_helper", ROOT / "scripts" / helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    mount = tmp_path / "foreign"
    mount.mkdir(mode=0o755)
    private = mount / "private"
    private.mkdir(mode=0o700)
    inode = mount.stat().st_ino
    real_fstat = os.fstat
    def foreign_fstat(fd):
        info = real_fstat(fd)
        return SimpleNamespace(st_uid=65534, st_mode=info.st_mode) if info.st_ino == inode else info
    monkeypatch.setattr(module.os, "fstat", foreign_fstat)
    monkeypatch.setenv("HOME", str(tmp_path / "elsewhere"))
    with pytest.raises(ValueError):
        getattr(module, function)(private if function == "open_cache" else private / "stamp")

@pytest.mark.parametrize('helper,function', [
    ('lsf-build/scripts/private-build-cache.py', 'open_cache'),
    ('lsf-push/private-stamp.py', 'open_parent'),
])
def test_home_replacement_cannot_redirect_open_descriptor(tmp_path, monkeypatch, helper, function):
    spec = importlib.util.spec_from_file_location('race_helper', ROOT / 'scripts' / helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    home = tmp_path / 'home'
    home.mkdir(mode=0o700)
    private = home / 'private'
    private.mkdir(mode=0o700)
    home_inode = home.stat().st_ino
    original_inode = private.stat().st_ino
    attacker = tmp_path / 'attacker'
    attacker.mkdir(mode=0o700)
    (attacker / 'private').mkdir(mode=0o700)
    monkeypatch.setenv('HOME', str(home))
    real_open = os.open
    swapped = False
    def replace_after_open(path, flags, *args, **kwargs):
        nonlocal swapped
        fd = real_open(path, flags, *args, **kwargs)
        if os.fstat(fd).st_ino == home_inode and not swapped:
            swapped = True
            home.rename(tmp_path / 'original-home')
            home.symlink_to(attacker, target_is_directory=True)
        return fd
    monkeypatch.setattr(module.os, 'open', replace_after_open)
    result = getattr(module, function)(private if function == 'open_cache' else private / 'stamp')
    fd = result if isinstance(result, int) else result[0]
    try:
        assert os.fstat(fd).st_ino == original_inode
        assert swapped
    finally:
        os.close(fd)
