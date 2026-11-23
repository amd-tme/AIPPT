#!/usr/bin/env python3
"""Install and check LSF executables through a trusted directory descriptor."""
import os
from pathlib import Path
import secrets
import stat
import sys

NAMES = ('image-build-lsf', 'image-build-lsf-worker', 'image-push-lsf')



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


def open_cache(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('cache path must be absolute with no parent traversal')
    start, fd = open_ancestry_boundary(path)
    try:
        for part in path.relative_to(start).parts:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(part, 0o700, dir_fd=fd)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            if info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022:
                raise ValueError('cache ancestors must have trusted ownership and no group/world writes')
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('cache bin directory must be user-owned with mode 0700')
        return fd
    except BaseException:
        os.close(fd)
        raise


def check_binary(fd, name):
    binary = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    try:
        info = os.fstat(binary)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError('cached executable must be a private, user-owned regular file')
    finally:
        os.close(binary)


def install(fd, source):
    for name in NAMES:
        temporary = '.install-' + secrets.token_hex(16)
        output = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700, dir_fd=fd)
        try:
            with os.fdopen(output, 'wb') as destination, open(Path(source) / name, 'rb') as origin:
                while chunk := origin.read(1024 * 1024):
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=fd)
            except FileNotFoundError:
                pass
        check_binary(fd, name)
    os.fsync(fd)


def main():
    action, path, *arguments = sys.argv[1:]
    fd = open_cache(path)
    try:
        if action == 'install':
            install(fd, arguments[0])
        elif action == 'init':
            pass
        elif action == 'check':
            for name in NAMES:
                check_binary(fd, name)
        else:
            raise ValueError('expected init, install or check')
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f'image-build-lsf cache validation failed: {error}')
