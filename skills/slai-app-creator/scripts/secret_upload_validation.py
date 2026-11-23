#!/usr/bin/env python3
"""Bounded pre-upload Secret validation; never emit manifest contents."""
import json
import sys
from pathlib import Path
import yaml
from ciphertext_validation import check_document, platform_recipients
from yaml_limits import apply_resource_limits, bounded_loader, MAX_DOCUMENTS
from keycloak_egress import validate_files


def validate(files, app_id=None):
    validate_files(files)
    recipients = platform_recipients()
    ingress_documents = {}
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
                if app_id and kind == 'Ingress':
                    ingress_documents.setdefault(name, []).append(doc)
                    for entry in doc.get('spec', {}).get('tls', []):
                        if (entry.get('secretName') == 'slai-app-wildcard-tls'
                                and app_id not in {'localai', 'llmd-localai', 'localai-router'}):
                            return False
        finally:
            loader.dispose()
    if app_id:
        from ingress_policy import managed_tls_target
        policies = [item['content'] for item in files if item['path'] == 'tls-policy.json']
        if len(policies) > 1:
            return False
        if policies:
            managed_tls_target(Path('/') / app_id, ingress_documents, policies[0])
    return True


if __name__ == '__main__':
    apply_resource_limits()
    try:
        raw = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
        payload = json.loads(raw)
        valid = len(raw) <= 8 * 1024 * 1024 and (
            validate(payload['files'], payload['app_id']) if isinstance(payload, dict) else validate(payload))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, yaml.YAMLError, MemoryError, RecursionError):
        valid = False
    print(json.dumps({'valid': valid}))
