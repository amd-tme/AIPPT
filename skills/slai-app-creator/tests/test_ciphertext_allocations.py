"""Isolated ciphertext workers consume bounded allocation data, never code paths."""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

import main

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def secret_file(tmp_path, name='app-settings'):
    recipient = yaml.safe_load((SCRIPTS.parent / 'assets/platform.sops.yaml').read_text())['creation_rules'][0]['age']
    enc = 'ENC[AES256_GCM,data:dGVzdA==,iv:aXY=,tag:dGFn,type:str]'
    doc = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': name, 'namespace': 'slai-app-prod'},
           'stringData': {'fixture': enc}, 'sops': {'mac': enc, 'age': [{'recipient': recipient, 'enc': 'fixture'}],
              'encrypted_regex': '^(data|stringData)$', 'version': '3.9.4', 'lastmodified': '2026-11-02T00:00:00Z'}}
    path = tmp_path / 'secret.enc.yaml'
    path.write_text(yaml.safe_dump(doc))
    return path


@pytest.mark.parametrize('name,accepted', [('app-settings', True), ('app-other-settings', False)])
def test_parent_supplies_verified_allocations_and_retains_sibling_collision_guard(tmp_path, monkeypatch, name, accepted):
    path = secret_file(tmp_path, name)
    calls = []
    monkeypatch.setattr(main, '_trusted_allocated_app_ids', lambda: calls.append(True) or frozenset({'app', 'app-other'}))
    assert bool(main.ciphertext_errors(path, 'slai-app-prod', 'app')) is not accepted
    assert calls == [True]


@pytest.mark.parametrize('payload', [None, b'{invalid', b'{}', b'["app", "app"]', b'["../outside"]',
                                   b'[' + b' ' * (1024 * 1024) + b']'])
def test_worker_rejects_missing_malformed_or_oversized_production_allocation_data(tmp_path, payload):
    path = secret_file(tmp_path)
    command = [sys.executable, str(SCRIPTS / 'ciphertext_validation.py'), str(path), 'slai-app-prod', 'app']
    if payload is not None:
        command.append('--allocated-app-ids-stdin')
    result = subprocess.run(command, input=payload, capture_output=True, check=True)
    assert json.loads(result.stdout)
    assert b'Traceback' not in result.stderr


def test_parent_cannot_substitute_unverified_allocations_after_source_failure(tmp_path, monkeypatch):
    def reject():
        raise ValueError('source unavailable')
    monkeypatch.setattr(main, '_trusted_allocated_app_ids', reject)
    assert main.ciphertext_errors(secret_file(tmp_path), 'slai-app-prod', 'app')
