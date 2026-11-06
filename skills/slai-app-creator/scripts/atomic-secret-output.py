#!/usr/bin/env python3
"""Write successful encryption output atomically without following links."""
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile



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


def validate(output):
    path = Path(os.path.abspath(output))
    uid = os.getuid() if os.name != 'nt' else None
    start = trusted_ancestry_start(path.parent)
    ancestry = [*reversed(path.parent.parents), path.parent]
    for directory in ancestry[ancestry.index(start):]:
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('Output ancestors must be real directories')
        if uid is not None:
            sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
            if info.st_uid not in (0, uid) or (info.st_mode & 0o022 and not sticky_root):
                raise ValueError('Output ancestors must be trusted and not writable by others')
    info = path.parent.lstat()
    if uid is not None and (info.st_uid != uid or info.st_mode & 0o022):
        raise ValueError('Output directory must be owned and not writable by others')
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Existing output must be regular and not linked')
        if uid is not None and (info.st_uid != uid or info.st_mode & 0o022):
            raise ValueError('Existing output must be owned and not writable by others')
    return path


def write(output, command):
    path = validate(output)
    fd, temporary = tempfile.mkstemp(prefix='.sops-output-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            subprocess.run(command, stdout=stream, check=True)
            stream.flush()
            os.fsync(stream.fileno())
        validate(path)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == '__main__':
    try:
        if sys.argv[1] == '--validate':
            print(validate(sys.argv[2]))
        else:
            write(sys.argv[1], sys.argv[2:])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
