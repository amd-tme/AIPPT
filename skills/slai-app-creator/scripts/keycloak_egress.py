#!/usr/bin/env python3
"""Check or add the platform Keycloak HTTPS grant for an SSO bundle."""
import argparse
from contextlib import contextmanager
import ipaddress
import json
import os
from pathlib import Path
import secrets
import stat

import yaml
from yaml_limits import bounded_loader


def required_addresses():
    path = Path(__file__).resolve().parents[1] / 'assets/platform-keycloak-egress.json'
    return json.loads(path.read_text())['addresses']


def load_policy(text):
    loader = bounded_loader(text.encode())
    try:
        document = loader.get_single_data()
    finally:
        loader.dispose()
    if not isinstance(document, dict) or document.get('kind') != 'NetworkPolicy':
        raise ValueError('expected one NetworkPolicy')
    if 'Egress' not in document.get('spec', {}).get('policyTypes', []):
        raise ValueError('NetworkPolicy must declare Egress policyTypes')
    return document


def missing_addresses(document):
    missing = []
    for address in required_addresses():
        destination = ipaddress.ip_address(address)
        covered = False
        for rule in document['spec'].get('egress', []):
            # Require an explicit destination and TCP port, like creator validation.
            if not any(p.get('protocol', 'TCP') == 'TCP' and p.get('port') == 443
                       for p in rule.get('ports', [])):
                continue
            for peer in rule.get('to', []):
                block = peer.get('ipBlock', {})
                if 'cidr' in block and destination in ipaddress.ip_network(block['cidr']):
                    if not any(destination in ipaddress.ip_network(x) for x in block.get('except', [])):
                        covered = True
        if not covered:
            missing.append(address)
    return missing


def validate_files(files):
    contents = {Path(item['path']).name: item['content'] for item in files}
    if 'auth-policy.json' not in contents:
        return
    auth = json.loads(contents['auth-policy.json'])
    if auth.get('enabled') is not True:
        return
    document = load_policy(contents.get('networkpolicy.yaml', ''))
    missing = missing_addresses(document)
    if missing:
        raise ValueError('Keycloak SSO requires TCP 443 egress; missing destinations: ' + ', '.join(missing))


@contextmanager
def open_bundle(directory):
    """Pin a trusted, non-symlink directory chain for the whole operation."""
    if os.name != 'posix' or not all(hasattr(os, flag) for flag in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK')):
        raise ValueError('Secure bundle preparation requires Linux, WSL, or macOS')
    path = Path(os.path.abspath(directory))
    uid = os.getuid()
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            info = os.fstat(fd)
            sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            if info.st_uid not in (0, uid) or (info.st_mode & 0o022 and not sticky_root):
                raise ValueError('Bundle ancestors must be trusted and not writable by others')
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if info.st_uid != uid or info.st_mode & 0o022:
            raise ValueError('Bundle directory must be owned and not writable by others')
        yield fd
    finally:
        os.close(fd)


def file_stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_at(directory_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid() or info.st_mode & 0o022 or info.st_size > 1024 * 1024):
            raise ValueError('Bundle inputs must be owned regular files within size limits')
        data = source.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024 or file_stamp(info) != file_stamp(os.fstat(source.fileno())):
            raise ValueError('Bundle input changed during read or exceeds size limit')
    return data.decode('utf-8'), info


def atomic_update(directory_fd, name, original, content):
    temporary = '.keycloak-egress-' + secrets.token_hex(16)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory_fd)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(content.encode('utf-8'))
            output.flush()
            os.fchmod(output.fileno(), stat.S_IMODE(original.st_mode) & 0o777)
            os.fsync(output.fileno())
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if file_stamp(current) != file_stamp(original):
            raise ValueError('NetworkPolicy changed before update')
        # Replacing an entry never follows a newly substituted destination link.
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        temporary = None
        os.fsync(directory_fd)
    finally:
        if temporary is not None:
            os.unlink(temporary, dir_fd=directory_fd)


def prepare_bundle(directory, apply=False):
    with open_bundle(directory) as directory_fd:
        try:
            auth, _ = read_at(directory_fd, 'auth-policy.json')
        except FileNotFoundError:
            return 'Keycloak SSO disabled; no egress changes'
        if json.loads(auth).get('enabled') is not True:
            return 'Keycloak SSO disabled; no egress changes'
        text, original = read_at(directory_fd, 'networkpolicy.yaml')
        document = load_policy(text)
        missing = missing_addresses(document)
        if missing and not apply:
            raise ValueError('Keycloak SSO requires TCP 443 egress; missing destinations: ' + ', '.join(missing))
        if missing:
            document['spec'].setdefault('egress', []).append({
                'to': [{'ipBlock': {'cidr': str(ipaddress.ip_network(address))}} for address in missing],
                'ports': [{'protocol': 'TCP', 'port': 443}],
            })
            atomic_update(directory_fd, 'networkpolicy.yaml', original, yaml.safe_dump(document, sort_keys=False))
        return 'Keycloak TCP 443 egress verified'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--apply', action='store_true', help='Add only missing SSO destinations on TCP 443')
    args = parser.parse_args()
    try:
        print(prepare_bundle(args.bundle, args.apply))
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError):
        parser.exit(1, 'Keycloak SSO egress check failed. Use an owned, non-symlink bundle on Linux, WSL, or macOS with trusted ancestors and regular input files. Prepare explicit TCP 443 to every address in assets/platform-keycloak-egress.json, or run this helper with --apply.\n')


if __name__ == '__main__':
    main()
