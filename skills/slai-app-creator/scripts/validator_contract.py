#!/usr/bin/env python3
"""Verify that client and hosted validator bundles use the same source files."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

FILES = (
    'scripts/main.py', 'scripts/bundle_resources.py', 'scripts/image_release_evidence.py',
    'scripts/ciphertext_validation.py', 'scripts/ingress_policy.py',
    'scripts/ingress-policy.yaml', 'scripts/prepare_platform_checkout.py', 'scripts/manifest_yaml.py',
    'scripts/yaml_limits.py', 'scripts/secret_upload_validation.py',
    'scripts/keycloak_egress.py', 'assets/platform-keycloak-egress.json',
    'assets/platform.sops.yaml',
    'scripts/per_app_tls_inventory.py', 'assets/tls-cutover.json',
    'scripts/hosted_validator_provenance.py',
)


def contract(root: Path) -> dict:
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in FILES}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'schema_version': 1, 'sha256': digest, 'files': hashes}


def verify(root: Path) -> dict:
    expected = json.loads((root / 'assets/validator-contract.json').read_text())
    actual = contract(root)
    if actual != expected:
        changed = [name for name in FILES if actual['files'][name] != expected.get('files', {}).get(name)]
        raise ValueError('Validator contract differs: ' + ', '.join(changed or ['contract metadata']))
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--compare-skill-root', type=Path)
    parser.add_argument('--write', action='store_true', help='Record hashes after reviewing validator changes')
    args = parser.parse_args()
    try:
        if args.write:
            (args.skill_root / 'assets/validator-contract.json').write_text(json.dumps(contract(args.skill_root), indent=2) + '\n')
        actual = verify(args.skill_root)
        if args.compare_skill_root and verify(args.compare_skill_root) != actual:
            raise ValueError('Client and hosted validator contracts differ')
        print(actual['sha256'])
        return 0
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
