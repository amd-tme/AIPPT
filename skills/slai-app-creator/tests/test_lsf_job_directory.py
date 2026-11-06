"""Source-staging jobs must remain under trusted, private parents."""
import importlib.util
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / 'scripts/lsf-build/scripts/private-job-directory.py'
spec = importlib.util.spec_from_file_location('private_lsf_job', HELPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_job_has_private_staging_and_output(tmp_path):
    root = tmp_path / 'app'
    root.mkdir(mode=0o700)
    job = module.create_job(str(root))
    assert job.parent == root / '.oci-build/jobs'
    for path in (root / '.oci-build', job.parent, job, job / 'output'):
        assert path.stat().st_mode & 0o777 == 0o700
    assert module.create_job(str(root)) != job


@pytest.mark.parametrize('level', ['.oci-build', 'jobs'])
def test_symlinked_staging_parent_is_rejected(tmp_path, level):
    root = tmp_path / 'app'
    root.mkdir(mode=0o700)
    target = tmp_path / 'outside'
    target.mkdir(mode=0o700)
    if level == '.oci-build':
        (root / level).symlink_to(target, target_is_directory=True)
    else:
        (root / '.oci-build').mkdir(mode=0o700)
        (root / '.oci-build/jobs').symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError):
        module.create_job(str(root))
    assert not list(target.iterdir())


@pytest.mark.parametrize('level', ['app', '.oci-build', 'jobs'])
def test_writable_staging_parent_is_rejected(tmp_path, level):
    root = tmp_path / 'app'
    root.mkdir(mode=0o700)
    (root / '.oci-build').mkdir(mode=0o700)
    (root / '.oci-build/jobs').mkdir(mode=0o700)
    paths = {'app': root, '.oci-build': root / '.oci-build', 'jobs': root / '.oci-build/jobs'}
    paths[level].chmod(0o770)
    with pytest.raises(ValueError):
        module.create_job(str(root))
    assert not list((root / '.oci-build/jobs').iterdir())
