"""All manifest paths use bounded, isolated parsing and bounded file reads."""
import subprocess

import pytest
import main


def test_alias_and_depth_limits_apply_to_manifests():
    main._manifest_yaml_evidence.cache_clear()
    for text in ('a: &values [1, 2]\nb: *values\n', 'a: ' + '[' * 50 + '0' + ']' * 50):
        with pytest.raises(main._ManifestYamlError, match='limits'):
            main._bounded_yaml_document(text)


def test_file_size_limit_before_reading(tmp_path):
    path = tmp_path / 'deployment.yaml'
    with path.open('wb') as stream:
        stream.truncate(main.MAX_INPUT_BYTES + 1)
    errors = []
    assert main._manifest_file_text(path, errors) == ''
    assert 'file-size/type limits' in ' '.join(errors)


def test_parser_timeout_is_cached_and_fail_closed(monkeypatch):
    main._manifest_yaml_evidence.cache_clear()
    calls = []

    def timeout(*args, **kwargs):
        calls.append(kwargs)
        raise subprocess.TimeoutExpired('manifest parser', 10)

    monkeypatch.setattr(main.subprocess, 'run', timeout)
    for _ in range(2):
        with pytest.raises(main._ManifestYamlError, match='limits'):
            main._bounded_yaml_document('a: timeout-case')
    assert len(calls) == 1
    assert calls[0]['timeout'] == 10
    assert 'HARBOR_PASSWORD' not in calls[0]['env']
    main._manifest_yaml_evidence.cache_clear()


def test_regular_manifest_has_unchanged_structure():
    doc = main._bounded_yaml_document('kind: Deployment\nspec:\n  replicas: 2\n')
    assert doc == {'kind': 'Deployment', 'spec': {'replicas': 2}}


@pytest.mark.parametrize('text', [
    'kind: Secret\nkind: Deployment\n',
    'metadata:\n  name: first\n  name: second\n',
    '1: first\n01: second\n',
])
def test_duplicate_mapping_keys_are_rejected(text):
    with pytest.raises(main._ManifestYamlError, match='limits'):
        main._bounded_yaml_document(text)


def test_same_key_in_different_mappings_is_allowed():
    assert main._bounded_yaml_document('a: {name: first}\nb: {name: second}\n') == {
        'a': {'name': 'first'}, 'b': {'name': 'second'}}
