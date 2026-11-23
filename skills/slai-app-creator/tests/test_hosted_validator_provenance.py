"""Validate offline image provenance without granting clients marker-based trust."""
import json
import os
from pathlib import Path
import stat

import pytest

import hosted_validator_provenance as provenance


@pytest.fixture
def image_tree(tmp_path, monkeypatch):
    root = tmp_path / 'image'
    root.mkdir(mode=0o755)
    for name in provenance.REQUIRED:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('reviewed source fixture: ' + name)
    # Model root-owned image metadata while exercising real descriptor I/O as
    # an unprivileged test user; outer /tmp is modeled as protected /opt.
    outer = {(p.stat().st_dev, p.stat().st_ino) for p in root.parents}
    original_stat, original_fstat = os.stat, os.fstat
    state = {'foreign': set(), 'unsafe_outer': set()}
    def image_metadata(info):
        identity = (info.st_dev, info.st_ino)
        values = list(info)
        values[4] = 23456 if identity in state['foreign'] else 0
        if identity in outer and identity not in state['unsafe_outer']:
            values[0] &= ~0o022
        return os.stat_result(values)
    monkeypatch.setattr(provenance.os, 'stat', lambda *a, **kw: image_metadata(original_stat(*a, **kw)))
    monkeypatch.setattr(provenance.os, 'fstat', lambda *a: image_metadata(original_fstat(*a)))
    monkeypatch.setattr(provenance, 'HOSTED_ROOT', root)
    provenance.write_manifest(root)
    return root, state


def test_offline_hosted_tree_matches_exact_source_manifest(image_tree):
    root, _ = image_tree
    assert provenance.verify_hosted_root(root) == root
    manifest = json.loads((root / provenance.MANIFEST).read_text())
    assert provenance.REQUIRED <= manifest['files'].keys()
    assert stat.S_IMODE((root / provenance.MANIFEST).stat().st_mode) == 0o444


def test_manifest_remains_readable_by_nonroot_runtime_under_restrictive_build_umask(image_tree):
    root, _ = image_tree
    (root / provenance.MANIFEST).unlink()
    previous = os.umask(0o077)
    try:
        provenance.write_manifest(root)
    finally:
        os.umask(previous)
    assert stat.S_IMODE((root / provenance.MANIFEST).stat().st_mode) == 0o444
    assert provenance.verify_hosted_root(root) == root


@pytest.mark.parametrize('mutation', ['changed', 'added', 'removed', 'symlink', 'writable', 'foreign', 'linked'])
def test_hosted_executable_sources_cannot_drift_or_lose_protection(image_tree, mutation):
    root, state = image_tree
    source = root / 'scripts/validate-ingress-policy.py'
    if mutation == 'changed':
        source.write_text('modified validator')
    elif mutation == 'added':
        (source.parent / 'unexpected_module.py').write_text('unexpected import source')
    elif mutation == 'removed':
        source.unlink()
    elif mutation == 'symlink':
        target = source.with_name('redirected.py')
        source.rename(target)
        source.symlink_to(target)
    elif mutation == 'writable':
        source.chmod(0o666)
    elif mutation == 'foreign':
        info = source.stat()
        state['foreign'].add((info.st_dev, info.st_ino))
    else:
        os.link(source, source.with_name('alias.py'))
    with pytest.raises((ValueError, OSError)):
        provenance.verify_hosted_root(root)


@pytest.mark.parametrize('mutation', ['foreign', 'writable', 'invalid_json'])
def test_hosted_manifest_is_not_a_caller_controlled_trust_marker(image_tree, mutation):
    root, state = image_tree
    manifest = root / provenance.MANIFEST
    if mutation == 'foreign':
        info = manifest.stat()
        state['foreign'].add((info.st_dev, info.st_ino))
    elif mutation == 'writable':
        manifest.chmod(0o666)
    else:
        manifest.chmod(0o644)
        manifest.write_text('{invalid')
    with pytest.raises(ValueError):
        provenance.verify_hosted_root(root)


def test_hosted_root_ancestors_must_be_protected(image_tree):
    root, state = image_tree
    parent = root.parent
    parent.chmod(0o777)
    info = parent.stat()
    state['unsafe_outer'].add((info.st_dev, info.st_ino))
    with pytest.raises(ValueError, match='protected'):
        provenance.verify_hosted_root(root)


def test_hosted_inventory_limits_are_enforced(image_tree, monkeypatch):
    root, _ = image_tree
    monkeypatch.setattr(provenance, 'MAX_ENTRIES', 2)
    with pytest.raises(ValueError, match='limit'):
        provenance.verify_hosted_root(root)
