import copy
import yaml
import main
from pathlib import Path

RECIPIENT = yaml.safe_load((Path(__file__).parents[1] / "assets/platform.sops.yaml").read_text())["creation_rules"][0]["age"]

ENC = 'ENC[AES256_GCM,data:dGVzdA==,iv:aXY=,tag:dGFn,type:str]'
VALID = {'apiVersion': 'v1', 'kind': 'Secret', 'stringData': {'password': ENC},
         'sops': {'mac': ENC, 'age': [{'recipient': RECIPIENT, 'enc': 'encrypted key'}],
                  'encrypted_regex': '^(data|stringData)$', 'version': '3.9.4', 'lastmodified': '2026-10-03T00:00:00Z'}}


def test_structured_ciphertext_rejects_plaintext_and_marker_comments(tmp_path):
    path = tmp_path / 'secrets.enc.yaml'
    path.write_text('# sops: ENC[\nkind: Secret\nstringData:\n  password: plaintext\n')
    assert main.ciphertext_errors(path)
    doc = copy.deepcopy(VALID)
    doc['stringData']['password'] = 'plaintext'
    path.write_text(yaml.safe_dump(doc))
    assert main.ciphertext_errors(path)


def test_every_document_must_be_encrypted(tmp_path):
    path = tmp_path / 'tls-secret.enc.yaml'
    path.write_text(yaml.safe_dump_all([VALID, VALID]))
    assert not main.ciphertext_errors(path)
    bad = copy.deepcopy(VALID)
    bad['data'] = {'tls.key': 'plaintext'}
    path.write_text(yaml.safe_dump_all([VALID, bad]))
    assert main.ciphertext_errors(path)


def test_ciphertext_size_limit_rejects_sparse_oversized_file(tmp_path):
    path = tmp_path / 'secrets.enc.yaml'
    with path.open('wb') as stream:
        stream.truncate(4 * 1024 * 1024 + 1)
    assert 'file-size limit' in ' '.join(main.ciphertext_errors(path))


def test_ciphertext_document_limit(tmp_path):
    path = tmp_path / 'secrets.enc.yaml'
    path.write_text(yaml.safe_dump_all([VALID] * 33))
    assert 'document-count limit' in ' '.join(main.ciphertext_errors(path))


def test_ciphertext_aliases_are_rejected(tmp_path):
    path = tmp_path / 'secrets.enc.yaml'
    path.write_text(yaml.safe_dump(VALID) + '\nextra: &values [1, 2]\nmore: *values\n')
    assert 'complexity limits or contains aliases' in ' '.join(main.ciphertext_errors(path))


def test_ciphertext_deep_nesting_is_rejected(tmp_path):
    path = tmp_path / 'secrets.enc.yaml'
    path.write_text(yaml.safe_dump(VALID) + '\nextra: ' + '[' * 50 + '0' + ']' * 50 + '\n')
    assert 'complexity limits' in ' '.join(main.ciphertext_errors(path))


def test_ciphertext_worker_timeout_is_fail_closed(tmp_path, monkeypatch):
    import subprocess

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('ciphertext worker', 10)

    monkeypatch.setattr(main.subprocess, 'run', timeout)
    errors = main.ciphertext_errors(tmp_path / 'secrets.enc.yaml')
    assert 'time/resource limits' in ' '.join(errors)


def test_duplicate_stringdata_cannot_hide_plaintext(tmp_path):
    import secrets
    canary = 'synthetic-' + secrets.token_hex(16)
    path = tmp_path / 'secrets.enc.yaml'
    # The first plaintext mapping would disappear under SafeLoader's last-wins rule.
    path.write_text('stringData:\n  password: ' + canary + '\n' + yaml.safe_dump(VALID))
    errors = main.ciphertext_errors(path)
    assert errors
    assert canary not in ' '.join(errors)


def test_duplicate_nested_secret_key_is_rejected(tmp_path):
    path = tmp_path / 'secrets.enc.yaml'
    document = yaml.safe_dump(VALID)
    document = document.replace('  password: ' + ENC, '  password: placeholder\n  password: ' + ENC)
    path.write_text(document)
    assert main.ciphertext_errors(path)


def test_unauthorized_or_additional_recipients_are_rejected(tmp_path):
    path = tmp_path / 'secrets.enc.yaml'
    for recipients in ([{'recipient': 'age1unauthorized', 'enc': 'fixture'}],
                       VALID['sops']['age'] + [{'recipient': 'age1unauthorized', 'enc': 'fixture'}],
                       [{'recipient': RECIPIENT, 'enc': 42}]):
        document = copy.deepcopy(VALID)
        document['sops']['age'] = recipients
        path.write_text(yaml.safe_dump(document))
        assert main.ciphertext_errors(path)


def test_encrypted_structural_fields_require_canonical_reencryption(tmp_path):
    path = tmp_path / 'secrets.enc.yaml'
    document = copy.deepcopy(VALID)
    document['kind'] = ENC
    document['apiVersion'] = ENC
    path.write_text(yaml.safe_dump(document))
    assert 'every document must be a Kubernetes Secret' in ' '.join(main.ciphertext_errors(path))
    document['kind'] = 'Secret'
    document['apiVersion'] = 'v1'
    path.write_text(yaml.safe_dump(document))
    assert not main.ciphertext_errors(path)


def test_service_account_token_generation_rejected_without_blocking_app_data():
    from ciphertext_validation import check_document
    for secret_type in (None, 'Opaque', 'kubernetes.io/dockerconfigjson', 'kubernetes.io/tls'):
        doc = copy.deepcopy(VALID)
        if secret_type is not None:
            doc['type'] = secret_type
        assert not check_document(doc, {RECIPIENT})
    doc = copy.deepcopy(VALID)
    doc['type'] = 'kubernetes.io/service-account-token'
    assert 'service-account credentials' in ' '.join(check_document(doc, {RECIPIENT}))
    for annotation in ('kubernetes.io/service-account.name', 'kubernetes.io/service-account.uid'):
        doc = copy.deepcopy(VALID)
        doc['metadata'] = {'annotations': {annotation: 'example'}}
        assert 'service-account credentials' in ' '.join(check_document(doc, {RECIPIENT}))
