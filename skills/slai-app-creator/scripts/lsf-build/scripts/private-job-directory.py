#!/usr/bin/env python3
"""Create source-staging jobs below a trusted private directory chain."""
import os
from pathlib import Path
import secrets
import stat
import sys



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


def trusted_directory(fd, *, private=False):
    info = os.fstat(fd)
    sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
    if info.st_uid not in (0, os.geteuid()) or (info.st_mode & 0o022 and not sticky_root):
        raise ValueError('job ancestors must have trusted ownership and no group/world writes')
    if private and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError('job staging directories must be user-owned with mode 0700')


def create_job(root):
    root = Path(root)
    if not root.is_absolute() or '..' in root.parts or '\n' in str(root) or '\r' in str(root):
        raise ValueError('worktree path must be absolute without parent traversal or newlines')
    start, fd = open_ancestry_boundary(root)
    try:
        for part in root.relative_to(start).parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            trusted_directory(fd)
        if os.fstat(fd).st_uid != os.geteuid():
            raise ValueError('worktree must be user-owned')
        for part in ('.oci-build', 'jobs'):
            try:
                os.mkdir(part, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            trusted_directory(fd, private=True)
        for _ in range(10):
            name = 'job.' + secrets.token_hex(16)
            try:
                os.mkdir(name, 0o700, dir_fd=fd)
                break
            except FileExistsError:
                continue
        else:
            raise ValueError('cannot allocate a unique source-staging job')
        job = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            trusted_directory(job, private=True)
            os.mkdir('output', 0o700, dir_fd=job)
        finally:
            os.close(job)
        return root / '.oci-build' / 'jobs' / name
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        print(create_job(sys.argv[1]))
    except (OSError, ValueError) as error:
        sys.exit(f'LSF source-staging directory validation failed: {error}')
