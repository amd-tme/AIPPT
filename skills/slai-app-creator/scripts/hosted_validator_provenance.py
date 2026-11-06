"""Verify the protected, immutable validator tree built into the hosted image."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

HOSTED_ROOT = Path('/opt/slai-app-platform')
MANIFEST = '.hosted-validator-manifest.json'
MODE = 'immutable-image'
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 8192
REQUIRED = {
    'scripts/validate-ingress-policy.py', 'scripts/validate-platform-auth-policy.py',
    'scripts/yaml_limits.py', 'scripts/platform_network_policy.py',
    'config/ingress-policy.yaml', 'config/platform-sso-auth-proxy.json',
    'config/platform-keycloak-egress.json', 'config/schemas/platform-auth-policy.schema.json',
    'skills/slai-app-creator/scripts/main.py',
    'skills/slai-app-creator/scripts/hosted_validator_provenance.py',
    'skills/slai-app-creator/assets/validator-contract.json',
}


def _protected(info, directory=False):
    if info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('Hosted validator sources must be root-owned and protected from writes')
    if directory:
        valid = stat.S_ISDIR(info.st_mode)
    else:
        valid = stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= MAX_FILE_BYTES
    if not valid:
        raise ValueError('Hosted validator sources must be regular files with one link and real directories')


def _open_root(root):
    if os.name != 'posix' or root != HOSTED_ROOT:
        raise ValueError('Hosted validator mode requires its fixed image root')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open('/', flags)
    try:
        _protected(os.fstat(fd), directory=True)
        for part in root.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
            _protected(os.fstat(fd), directory=True)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _snapshot(root_fd):
    files, directories = {}, []
    def visit(directory_fd, prefix='', depth=0):
        entries = os.listdir(directory_fd)
        if len(entries) > MAX_ENTRIES or depth > 64:
            raise ValueError('Hosted validator source inventory exceeds limit')
        for name in sorted(entries):
            if not prefix and name == MANIFEST:
                continue
            relative = prefix + name
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            directory = stat.S_ISDIR(info.st_mode)
            _protected(info, directory=directory)
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if directory:
                flags |= os.O_DIRECTORY
            child = os.open(name, flags, dir_fd=directory_fd)
            try:
                _protected(os.fstat(child), directory=directory)
                if directory:
                    directories.append(relative)
                    visit(child, relative + '/', depth + 1)
                else:
                    digest, count = hashlib.sha256(), 0
                    while True:
                        data = os.read(child, 65536)
                        if not data:
                            break
                        count += len(data)
                        if count > MAX_FILE_BYTES:
                            raise ValueError('Hosted validator source exceeds size limit')
                        digest.update(data)
                    files[relative] = digest.hexdigest()
                if len(files) + len(directories) > MAX_ENTRIES:
                    raise ValueError('Hosted validator source inventory exceeds limit')
            finally:
                os.close(child)
    visit(root_fd)
    if not REQUIRED <= files.keys():
        raise ValueError('Hosted validator image is missing required canonical sources')
    return {'schema_version': 1, 'files': files, 'directories': sorted(directories)}


def write_manifest(root=HOSTED_ROOT):
    """Image-build operation; runtime cannot write this root-owned artifact."""
    fd = _open_root(Path(root))
    try:
        encoded = (json.dumps(_snapshot(fd), sort_keys=True, indent=2) + '\n').encode()
        output = os.open(MANIFEST, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o444, dir_fd=fd)
        with os.fdopen(output, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fchmod(stream.fileno(), 0o444)
    finally:
        os.close(fd)


def verify_hosted_root(root):
    root = Path(root)
    fd = _open_root(root)
    try:
        source = os.open(MANIFEST, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(source, 'rb') as stream:
            _protected(os.fstat(stream.fileno()))
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Hosted validator manifest exceeds size limit')
        expected = json.loads(raw)
        if expected != _snapshot(fd):
            raise ValueError('Hosted validator executable source/config integrity verification failed')
        return root
    finally:
        os.close(fd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    if args.write:
        write_manifest()
    else:
        verify_hosted_root(HOSTED_ROOT)
