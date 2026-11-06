#!/usr/bin/env python3
"""Resolve checksum-verified SOPS in an owned private cache."""
import hashlib
import os
from pathlib import Path
import stat
import signal
import time
import sys
import tempfile
import urllib.request

VERSION = '3.9.4'
DIGEST = '5488e32bc471de7982ad895dd054bbab3ab91c417a118426134551e9626e4e85'
MAX_BINARY_BYTES = 128 * 1024 * 1024
MAX_DOWNLOAD_SECONDS = 300
SOCKET_TIMEOUT_SECONDS = 30



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


def validate_cache(cache):
    cache = Path(os.path.abspath(cache))
    uid = os.getuid()
    start = trusted_ancestry_start(cache)
    ancestry = [*reversed(cache.parents), cache]
    for path in ancestry[ancestry.index(start):]:
        if path.is_symlink():
            raise ValueError('SOPS cache path must not contain symlinks')
        if not path.exists():
            path.mkdir(mode=0o700)
        info = path.lstat()
        sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, uid) or (info.st_mode & 0o022 and not sticky_root):
            raise ValueError('SOPS cache ancestors must be trusted and not writable by others')
    info = cache.lstat()
    if info.st_uid != uid or info.st_mode & 0o077:
        raise ValueError('SOPS cache must be private and user-owned')
    return cache


def verify(binary):
    descriptor = os.open(binary, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ValueError('SOPS cache binary must be owned, regular, and not linked or writable by others')
        if info.st_size > MAX_BINARY_BYTES:
            raise ValueError('Cached SOPS exceeds binary size limit')
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(descriptor, min(1024 * 1024, MAX_BINARY_BYTES - total + 1)):
            total += len(chunk)
            if total > MAX_BINARY_BYTES:
                raise ValueError('Cached SOPS exceeds binary size limit')
            digest.update(chunk)
        if digest.hexdigest() != DIGEST:
            raise ValueError('Cached SOPS checksum mismatch')
        if not info.st_mode & 0o111:
            raise ValueError('Cached SOPS is not executable')
    finally:
        os.close(descriptor)


def download_binary(url, staged):
    """Bound total bytes and elapsed time, including blocked or trickled reads."""
    started = time.monotonic()
    previous_handler = signal.getsignal(signal.SIGALRM)

    def expired(_signum, _frame):
        raise TimeoutError('SOPS download exceeded total duration limit')

    signal.signal(signal.SIGALRM, expired)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, MAX_DOWNLOAD_SECONDS)
    try:
        deadline = started + MAX_DOWNLOAD_SECONDS
        total_bytes = 0
        with urllib.request.urlopen(url, timeout=SOCKET_TIMEOUT_SECONDS) as response, staged.open('xb') as output:
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError('SOPS download exceeded total duration limit')
                chunk = response.read(min(1024 * 1024, MAX_BINARY_BYTES - total_bytes + 1))
                if time.monotonic() >= deadline:
                    raise TimeoutError('SOPS download exceeded total duration limit')
                if not chunk:
                    break
                if total_bytes + len(chunk) > MAX_BINARY_BYTES:
                    raise ValueError('SOPS download exceeded binary size limit')
                output.write(chunk)
                total_bytes += len(chunk)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            remaining = max(0.000001, previous_timer[0] - (time.monotonic() - started))
            signal.setitimer(signal.ITIMER_REAL, remaining, previous_timer[1])


def main():
    if os.environ.get('SOPS_VERSION', VERSION) != VERSION:
        raise ValueError('Automatic download supports pinned SOPS 3.9.4; use SOPS_BIN for another version')
    os.umask(0o077)
    cache = validate_cache(os.environ.get('SOPS_CACHE_DIR', str(Path.home() / '.cache/slai-app-creator')))
    binary = cache / ('sops-' + VERSION)
    if binary.exists() or binary.is_symlink():
        verify(binary)
    else:
        with tempfile.TemporaryDirectory(prefix='.download-', dir=cache) as temporary:
            staged = Path(temporary) / 'sops'
            url = f'https://github.com/getsops/sops/releases/download/v{VERSION}/sops-v{VERSION}.linux.amd64'
            download_binary(url, staged)
            staged.chmod(0o700)
            verify(staged)
            validate_cache(cache)
            if binary.exists() or binary.is_symlink():
                verify(binary)
            else:
                os.replace(staged, binary)
        verify(binary)
    print(binary)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
