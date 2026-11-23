#!/usr/bin/env python3
"""Extract only bounded, validated fields for the local image probe."""
import json
from pathlib import Path
import sys
from main import _bounded_yaml_document
from yaml_limits import read_file_bytes


def fields(path):
    document = _bounded_yaml_document(read_file_bytes(path).decode('utf-8'))
    container = document['spec']['template']['spec']['containers'][0]
    port = container['ports'][0]['containerPort']
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('invalid port')
    base = ''
    for item in container.get('env', []):
        if item.get('name') == 'BASE_PATH':
            base = item.get('value', '')
    if not isinstance(base, str) or len(base) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in base):
        raise ValueError('invalid BASE_PATH')
    paths = [(container.get(name) or {}).get('httpGet', {}).get('path') for name in ('livenessProbe', 'readinessProbe')]
    encoded = json.dumps(paths)
    if len(encoded) > 16384:
        raise ValueError('probe paths exceed limit')
    return str(port) + '\n' + base + '\n' + encoded


if __name__ == '__main__':
    try:
        print(fields(Path(sys.argv[1])))
    except Exception:
        sys.exit('probe-smoke: manifest is invalid or exceeds parsing limits')
