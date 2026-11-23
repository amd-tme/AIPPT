#!/usr/bin/env python3
"""Resource-limited SOPS shape validation; never decrypt or quote source values."""
import json
import os
from pathlib import Path
import re
import stat
import sys

from yaml_limits import (MAX_DOCUMENTS, YamlLimitError, apply_resource_limits,
                         bounded_loader, read_file_bytes)

SOPS_VALUE = re.compile(r'^ENC\[AES256_GCM,data:[A-Za-z0-9+/=]*,iv:[A-Za-z0-9+/=]+,tag:[A-Za-z0-9+/=]+,type:str\]$')


def application_owns(name, app_id, allocated_app_ids=()):
    return (isinstance(name, str) and (name == app_id or name.startswith(app_id + '-'))
            and not any(other != app_id and other.startswith(app_id + '-')
                        and (name == other or name.startswith(other + '-'))
                        for other in allocated_app_ids))


def check_document(document, authorized_recipients, namespace=None, app_id=None, allocated_app_ids=()):
    if not isinstance(document, dict) or document.get('kind') != 'Secret':
        return ['every document must be a Kubernetes Secret']
    object_metadata = document.get('metadata', {})
    if not isinstance(object_metadata, dict):
        return ['Secret metadata must be a mapping']
    annotations = object_metadata.get('annotations', {})
    if not isinstance(annotations, dict):
        return ['Secret annotations must be a mapping']
    if (document.get('type') == 'kubernetes.io/service-account-token'
            or any(key in annotations for key in (
                'kubernetes.io/service-account.name', 'kubernetes.io/service-account.uid'))):
        return ['application Secrets must not request Kubernetes service-account credentials']
    declared = object_metadata.get('namespace')
    if namespace is not None and declared != namespace:
        return ['Secret namespace must match bundle namespace']
    name = object_metadata.get('name')
    if app_id is not None and not application_owns(name, app_id, allocated_app_ids):
        return ['Secret name must belong to the bundle application; shared platform Secrets are not app-owned']
    metadata = document.get('sops')
    if not isinstance(metadata, dict) or not SOPS_VALUE.fullmatch(str(metadata.get('mac', ''))):
        return ['missing valid SOPS metadata/MAC']
    recipients = metadata.get('age')
    if not isinstance(recipients, list) or not recipients or any(
            not isinstance(recipient, dict)
            or not isinstance(recipient.get('recipient'), str) or not recipient['recipient'].strip()
            or not isinstance(recipient.get('enc'), str) or not recipient['enc'].strip()
            for recipient in recipients):
        return ['missing SOPS age recipient metadata']
    actual = [recipient['recipient'] for recipient in recipients]
    if len(set(actual)) != len(actual) or set(actual) != authorized_recipients:
        return ['SOPS age recipients must match the trusted platform configuration']
    if metadata.get('encrypted_regex') != '^(data|stringData)$' or not metadata.get('version') or not metadata.get('lastmodified'):
        return ['invalid SOPS encryption metadata']
    for field in ('data', 'stringData'):
        values = document.get(field, {})
        if not isinstance(values, dict):
            return [f'{field} must be a mapping of encrypted values']
        if any(not isinstance(value, str) or not SOPS_VALUE.fullmatch(value) for value in values.values()):
            return [f'plaintext or malformed encrypted Secret value in {field}']
    return []


def platform_recipients():
    config = Path(__file__).resolve().parents[1] / 'assets/platform.sops.yaml'
    loader = bounded_loader(read_file_bytes(config))
    try:
        document = loader.get_single_data()
    finally:
        loader.dispose()
    rules = document.get('creation_rules') if isinstance(document, dict) else None
    if not isinstance(rules, list) or not rules:
        raise ValueError('invalid platform recipient configuration')
    recipients = set()
    for rule in rules:
        age = rule.get('age') if isinstance(rule, dict) else None
        if not isinstance(age, str):
            raise ValueError('invalid platform recipient configuration')
        for value in age.split(','):
            value = value.strip()
            if not value.startswith('age1') or not value:
                raise ValueError('invalid platform recipient configuration')
            recipients.add(value)
    return recipients


def validate(path, namespace=None, app_id=None, allocated_app_ids=None):
    import yaml

    try:
        data = read_file_bytes(path)
    except YamlLimitError:
        return ['ciphertext exceeds file-size limit or is not a regular file']
    authorized_recipients = platform_recipients()
    if namespace == 'slai-app-prod':
        if (not isinstance(allocated_app_ids, list) or len(allocated_app_ids) > 4096
                or any(not isinstance(app, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', app)
                       for app in allocated_app_ids) or len(set(allocated_app_ids)) != len(allocated_app_ids)):
            return ['trusted platform application allocations are required']
        allocated = allocated_app_ids
    else:
        allocated = []
    loader = bounded_loader(data)
    count = 0
    try:
        while loader.check_data():
            count += 1
            if count > MAX_DOCUMENTS:
                return ['ciphertext exceeds YAML document-count limit']
            document = loader.get_data()
            errors = check_document(document, authorized_recipients, namespace, app_id, allocated)
            if errors:
                return errors
        if count == 0:
            return ['expected SOPS Secret documents']
        return []
    except YamlLimitError:
        return ['ciphertext exceeds YAML complexity limits or contains aliases']
    except yaml.YAMLError:
        return ['cannot parse SOPS Secret YAML']
    finally:
        loader.dispose()


def main():
    apply_resource_limits()
    try:
        arguments = sys.argv[1:]
        allocated = None
        if arguments and arguments[-1] == '--allocated-app-ids-stdin':
            arguments = arguments[:-1]
            raw = sys.stdin.buffer.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('allocation evidence exceeds limit')
            allocated = json.loads(raw)
        if not 1 <= len(arguments) <= 3:
            raise ValueError('invalid validation arguments')
        result = validate(Path(arguments[0]), arguments[1] if len(arguments) >= 2 else None,
                          arguments[2] if len(arguments) == 3 else None, allocated)
    except (OSError, ValueError, MemoryError, RecursionError):
        result = ['ciphertext cannot be parsed within validation limits']
    print(json.dumps(result))


if __name__ == '__main__':
    main()
