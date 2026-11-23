#!/usr/bin/env python3
"""Write verified Harbor evidence through a trusted parent-directory descriptor."""
import json
import os
from pathlib import Path
import re
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


def open_parent(path):
    path = Path(os.path.abspath(path))
    start, fd = open_ancestry_boundary(path.parent)
    try:
        for part in path.parent.relative_to(start).parts:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(part, 0o700, dir_fd=fd)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            if info.st_uid not in (0, os.geteuid()) or (info.st_mode & 0o022 and not sticky_root):
                raise ValueError('stamp ancestors must have trusted ownership and no group/world writes')
        if os.fstat(fd).st_uid != os.geteuid():
            raise ValueError('stamp parent must be user-owned')
        return fd, path.name
    except BaseException:
        os.close(fd)
        raise


def write_stamp(path, evidence):
    image, digest = evidence['full_image'], evidence['image_digest']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*/[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*:slai-sc-[0-9a-f]{40}-[1-9][0-9]*-[1-9][0-9]*', image):
        raise ValueError('invalid image')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise ValueError('invalid digest')
    fd, name = open_parent(path)
    temporary = '.harbor-stamp-' + secrets.token_hex(16)
    created = False
    try:
        try:
            existing = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if (not stat.S_ISREG(existing.st_mode) or existing.st_uid != os.geteuid()
                    or existing.st_mode & 0o022 or existing.st_nlink != 1):
                raise ValueError('existing stamp must be an owned regular file without links or group/world writes')
        output = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        with os.fdopen(output, 'w') as stream:
            stream.write(f'FULL_IMAGE={image.rsplit(":", 1)[0]}@{digest}\nIMAGE_TAG={image.rsplit(":", 1)[1]}\nIMAGE_DIGEST={digest}\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
        created = False
        os.fsync(fd)
    finally:
        if created:
            os.unlink(temporary, dir_fd=fd)
        os.close(fd)


def main():
    write_stamp(sys.argv[1], json.load(sys.stdin))
    print(f'Recorded {os.path.abspath(sys.argv[1])}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.exit(f'LSF push result unavailable or invalid: {error}')
