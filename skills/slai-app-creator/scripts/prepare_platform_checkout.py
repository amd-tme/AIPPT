#!/usr/bin/env python3
"""Create a private platform checkout or validate an existing one before use."""
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from functools import lru_cache

ORIGINS = {'https://github.com/AMD-SLAI/slai-app-platform.git',
           'git@github.com:AMD-SLAI/slai-app-platform',
           'git@github.com:AMD-SLAI/slai-app-platform.git'}



def open_ancestry_boundary(path):
    """Open HOME without following any path component; validate the used fd."""
    home = Path(os.path.abspath(os.path.expanduser('~')))
    start = home if path == home or home in path.parents else Path('/')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in start.parts[1:]:
            info = os.fstat(fd)
            sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            if info.st_mode & 0o022 and not sticky_root:
                raise ValueError('HOME ancestors must not permit untrusted child replacement')
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if start != Path('/') and (info.st_uid != os.geteuid() or info.st_mode & 0o022):
            raise ValueError('HOME must be user-owned without group/world writes')
        return start, fd
    except BaseException:
        os.close(fd)
        raise

def trusted_ancestry_start(path):
    start, fd = open_ancestry_boundary(path)
    os.close(fd)
    return start


def validate(path):
    path = Path(os.path.abspath(path))
    uid = os.getuid()
    start = trusted_ancestry_start(path)
    ancestry = [*reversed(path.parents), path]
    for component in ancestry[ancestry.index(start):]:
        info = component.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('Checkout path must contain only real directories')
        sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if info.st_uid not in (0, uid) or (info.st_mode & 0o022 and not sticky_root):
            raise ValueError('Checkout ancestors must be trusted and not writable by other users')
    if path.stat().st_uid != uid or path.stat().st_mode & 0o077:
        raise ValueError('Checkout must be owned by this user with private permissions')
    gitdir = path / '.git'
    if gitdir.is_symlink() or not gitdir.is_dir():
        raise ValueError('Only a regular .git directory is supported')
    for base, dirs, files in os.walk(gitdir, followlinks=False):
        for name in dirs + files:
            info = (Path(base) / name).lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != uid or info.st_mode & 0o022:
                raise ValueError('Git metadata must be owned, non-symlink, and not writable by others')
    return path


# Reviewed platform source revision; refresh deliberately with plugin releases.
PLATFORM_COMMIT = '3d24d6deca664e4c547c9ab18c0720e6ad62c5fd'
PLATFORM_URL = 'https://github.com/AMD-SLAI/slai-app-platform.git'


def fresh_checkout():
    os.umask(0o077)
    workspace = Path(tempfile.mkdtemp(prefix='slai-platform-'))
    workspace.chmod(0o700)
    path = workspace / 'slai-app-platform'
    environment = dict(os.environ)
    # Do not inherit Git repository/config overrides from caller-selected trees.
    for key in list(environment):
        if key.startswith('GIT_'):
            del environment[key]
    environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    def git(*args):
        return subprocess.check_output(
            ['git', '-c', 'core.hooksPath=/dev/null',
             '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential',
             '-c', 'http.sslVerify=true', *args],
            env=environment, text=True, stderr=sys.stderr,
        ).strip()
    try:
        git('init', str(path))
        git('-C', str(path), 'remote', 'add', 'origin', PLATFORM_URL)
        git('-C', str(path), 'fetch', '--depth', '1', 'origin', PLATFORM_COMMIT)
        if git('-C', str(path), 'rev-parse', 'FETCH_HEAD') != PLATFORM_COMMIT:
            raise ValueError('Fetched platform revision does not match pinned commit')
        git('-C', str(path), 'checkout', '--detach', PLATFORM_COMMIT)
        path.chmod(0o700)
        return validate(path)
    except BaseException:
        import shutil
        shutil.rmtree(workspace)
        raise


@lru_cache(maxsize=1)
def trusted_validator_checkout():
    """Execute validators only from a fresh, pinned remote checkout.

    Existing app handoff trees are never an executable-source authority.
    This snapshot is private and process-local; no on-disk trust marker is reused.
    """
    return fresh_checkout()


def main():
    os.umask(0o077)
    if len(sys.argv) > 2:
        raise ValueError('Supply at most one existing checkout path')
    if len(sys.argv) == 2:
        raise ValueError('Existing checkouts cannot establish source provenance; prepare a fresh pinned checkout')
    path = fresh_checkout()
    print(path)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
