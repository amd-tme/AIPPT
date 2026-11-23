"""Catch missing release handoffs without treating file presence as authorization."""
import importlib.util
import itertools
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_evidence', ROOT / 'scripts/image_release_evidence.py')
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


@pytest.mark.parametrize('extra', ['pvc.yaml', 'configmap.yaml', 'worker.yaml'])
def test_single_image_with_additional_resources_needs_handoff(extra):
    errors = evidence.evidence_errors(['deployment.yaml', extra])
    assert len(errors) == 1
    assert extra in errors[0]
    assert 'single image' in errors[0]
    assert all(name in errors[0] for name in evidence.EVIDENCE_FILES)


@pytest.mark.parametrize('files', [set(combo) for n in (1, 2)
    for combo in itertools.combinations(sorted(evidence.EVIDENCE_FILES), n)])
def test_partial_handoff_fails_even_with_reviewed_image(files):
    errors = evidence.evidence_errors(files, approved_images=True)
    assert all(name in errors[0] for name in evidence.EVIDENCE_FILES - files)


def test_complete_handoff_passes_file_check_without_claiming_signature_validity():
    assert evidence.evidence_errors(['pvc.yaml', *evidence.EVIDENCE_FILES]) == []


def test_existing_reviewed_image_retains_hosted_compatibility():
    assert evidence.evidence_errors(['pvc.yaml'], approved_images=True) == []


def test_legacy_client_defers_missing_evidence_but_never_partial_records():
    assert evidence.evidence_errors(['configmap.yaml'], require_for_additional=False) == []
    assert evidence.evidence_errors(['configmap.yaml', 'image-release.json'], require_for_additional=False)


def test_standard_bundle_and_extra_ciphertext_do_not_acquire_new_requirement():
    assert evidence.evidence_errors(['deployment.yaml', 'auth-policy.json', 'provider.enc.yaml']) == []
    assert evidence.evidence_errors(['pvc.yaml'], production=False) == []


def test_packaged_and_hosted_evidence_contract_match():
    service = ROOT.parents[1] / 'tools/slai-app-submission/src/slai_app_submission/image_release_evidence.py'
    assert (ROOT / 'scripts/image_release_evidence.py').read_bytes() == service.read_bytes()


def test_legacy_strict_preflight_distinguishes_missing_and_partial(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    from bundle_resources import local_bundle_errors
    directory = tmp_path / 'slai-app-prod' / 'flowdeck'
    directory.mkdir(parents=True)
    (directory / 'pvc.yaml').write_text('')
    assert 'hosted validation of every' in ' '.join(local_bundle_errors(directory))
    (directory / 'image-policy.yaml').write_text('{}')
    errors = ' '.join(local_bundle_errors(directory))
    assert 'image-release.bundle.jsonl' in errors
    assert 'Submit this legacy bundle' not in errors
