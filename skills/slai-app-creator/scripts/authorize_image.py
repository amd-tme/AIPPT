#!/usr/bin/env python3
"""Request a signed existing-image handoff without an app-repository runner."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from uuid import uuid4

from submit_app import Client, ClientError, authenticate

FILES = {'image-policy.yaml', 'image-release.json', 'image-release.bundle.jsonl'}


def write_handoff(directory, files):
    if not isinstance(files, list) or len(files) != 3:
        raise ClientError('Hosted authorization did not return the complete signed handoff')
    contents = {}
    for item in files:
        if not isinstance(item, dict) or item.get('path') not in FILES or item['path'] in contents:
            raise ClientError('Hosted authorization returned unexpected evidence files')
        if not isinstance(item.get('content'), str) or len(item['content'].encode()) > 1024 * 1024:
            raise ClientError('Hosted authorization evidence exceeds its size limit')
        contents[item['path']] = item['content'].encode()
    if set(contents) != FILES:
        raise ClientError('Hosted authorization is missing signed evidence')
    # Pin the owned output directory; never replace existing or conflicting files.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(directory, flags)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ClientError('Evidence output directory must be owned and not group/world writable')
        for name, raw in contents.items():
            try:
                existing = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            except FileNotFoundError:
                continue
            with os.fdopen(existing, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or stream.read(1024 * 1024 + 1) != raw:
                    raise ClientError('Existing evidence conflicts with this handoff; preserve it in a separate bundle')
        for name, raw in contents.items():
            temporary = '.authorization-' + uuid4().hex
            try:
                out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                              0o600, dir_fd=fd)
                with os.fdopen(out, 'wb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    # Link a complete file atomically without replacing evidence.
                    os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                except FileExistsError:
                    existing = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                    with os.fdopen(existing, 'rb') as stream:
                        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode) or stream.read(1024 * 1024 + 1) != raw:
                            raise ClientError('Evidence output changed during preparation')
            finally:
                try:
                    os.unlink(temporary, dir_fd=fd)
                except FileNotFoundError:
                    pass
        os.fsync(fd)
    finally:
        os.close(fd)


def wait(client, identifier, timeout, interval):
    if not isinstance(identifier, str) or not re.fullmatch(r'[0-9a-f]{32}', identifier):
        raise ClientError('Hosted service returned an invalid authorization ID')
    deadline = time.monotonic() + timeout
    while True:
        result = client.request('GET', '/api/image-authorizations/' + identifier)
        if result.get('status') == 'authorized':
            return result['files']
        if result.get('status') == 'failed':
            raise ClientError('Platform authorization failed; inspect this request with the platform agent')
        if result.get('status') not in {'dispatch_pending', 'queued', 'in_progress', 'waiting', 'requested', 'pending'}:
            raise ClientError('Unexpected authorization state; preserve this request ID')
        if time.monotonic() >= deadline:
            raise ClientError('Authorization is still pending; resume the same authorization ID')
        time.sleep(min(interval, max(0, deadline - time.monotonic())))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', help='Owned POSIX directory receiving the three-file handoff')
    parser.add_argument('--app-id')
    parser.add_argument('--source-repository')
    parser.add_argument('--source-repository-id')
    parser.add_argument('--source-commit')
    parser.add_argument('--image-tag')
    parser.add_argument('--image-digest')
    parser.add_argument('--image-repository', help='Existing Harbor repository, including its registry; defaults to the app repository')
    parser.add_argument('--authorization-id')
    parser.add_argument('--idempotency-key')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--poll-interval', type=int, default=10)
    args = parser.parse_args(argv)
    identifier = args.authorization_id
    key = args.idempotency_key or uuid4().hex
    if not 1 <= args.timeout <= 3600 or not 1 <= args.poll_interval <= 60:
        parser.error('timeout must be 1-3600 seconds; poll interval must be 1-60 seconds')
    if not identifier and any(not value for value in (args.app_id, args.source_repository, args.source_repository_id, args.source_commit, args.image_tag, args.image_digest)):
        parser.error('New authorization requires app ID, declared source repository and numeric ID, source commit, image tag and digest')
    try:
        client = Client()
        authenticate(client, args.no_browser, 300)
        if not identifier:
            payload = {'app_id': args.app_id, 'source_repository': args.source_repository,
                       'source_repository_id': args.source_repository_id, 'source_commit': args.source_commit,
                       'image_tag': args.image_tag, 'image_digest': args.image_digest}
            if args.image_repository:
                payload['image_repository'] = args.image_repository
            print('Authorization idempotency key: ' + key, flush=True)
            result = client.request('POST', '/api/image-authorizations', payload, idempotency_key=key)
            identifier = result.get('id')
            if not isinstance(identifier, str) or not re.fullmatch(r'[0-9a-f]{32}', identifier):
                raise ClientError('Hosted service returned an invalid authorization ID')
            print('Authorization: ' + identifier, flush=True)
        files = wait(client, identifier, args.timeout, args.poll_interval)
        write_handoff(Path(args.directory), files)
        print('Complete signed handoff saved. Continue hosted submission using this bundle.')
        return 0
    except (ClientError, OSError, ValueError, KeyError):
        print('Authorization did not complete. Preserve the request and existing evidence; do not dispatch an app-repository workflow.', file=sys.stderr)
        if identifier:
            print('Resume authorization ID: ' + str(identifier), file=sys.stderr)
        else:
            print('Retry identical authorization intent with idempotency key: ' + key, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
