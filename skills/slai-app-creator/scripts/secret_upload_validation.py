#!/usr/bin/env python3
"""Bounded pre-upload Secret validation; never emit manifest contents."""
import json
import sys
import yaml
from ciphertext_validation import check_document, platform_recipients
from yaml_limits import apply_resource_limits, bounded_loader, MAX_DOCUMENTS
from keycloak_egress import validate_files


def validate(files):
    validate_files(files)
    recipients = platform_recipients()
    for item in files:
        name = item['path']
        if not name.endswith(('.yaml', '.yml')):
            continue
        loader = bounded_loader(item['content'].encode())
        count = 0
        try:
            while loader.check_data():
                count += 1
                if count > MAX_DOCUMENTS:
                    return False
                doc = loader.get_data()
                encrypted_file = name.endswith(('.enc.yaml', '.enc.yml'))
                # Hosted bundles support ordinary resource mappings only; reject
                # wrapper Lists/sequences that could conceal nested Secrets.
                kind = doc.get('kind') if isinstance(doc, dict) else None
                if not isinstance(kind, str) or kind.endswith('List'):
                    return False
                if encrypted_file or doc.get('kind') == 'Secret':
                    if not encrypted_file or check_document(doc, recipients):
                        return False
        finally:
            loader.dispose()
    return True


if __name__ == '__main__':
    apply_resource_limits()
    try:
        raw = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
        valid = len(raw) <= 8 * 1024 * 1024 and validate(json.loads(raw))
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError, MemoryError, RecursionError):
        valid = False
    print(json.dumps({'valid': valid}))
