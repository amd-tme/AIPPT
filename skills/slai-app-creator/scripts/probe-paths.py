#!/usr/bin/env python3
"""Validate JSON-encoded HTTP probe paths before shell URL construction."""
import json
import sys


def validated_paths(stream):
    data = stream.read(32769)
    if len(data) > 32768:
        raise ValueError('probe path input too large')
    values = json.loads(data)
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError('expected two probe path values')
    paths = []
    for value in values:
        if value is None:
            continue
        if (not isinstance(value, str) or not value.startswith('/')
                or len(value.encode('utf-8')) > 2048
                or '#' in value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError('invalid probe path')
        paths.append(value)
    return paths


if __name__ == '__main__':
    try:
        paths = validated_paths(sys.stdin.buffer)
    except (ValueError, UnicodeError, RecursionError):
        print('probe-smoke: invalid HTTP probe path; use an absolute path without whitespace, controls, or fragments', file=sys.stderr)
        sys.exit(1)
    for path in paths:
        print(path)
