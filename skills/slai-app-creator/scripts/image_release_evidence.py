"""File-set preflight only; signed authorization remains a hosted check."""
from pathlib import PurePosixPath

EVIDENCE_FILES = {'image-policy.yaml', 'image-release.json', 'image-release.bundle.jsonl'}
STANDARD_FILES = {'deployment.yaml', 'service.yaml', 'z-ingress.yaml', 'networkpolicy.yaml',
                  'secrets.enc.yaml', 'tls-secret.enc.yaml', 'service-cimd.yaml',
                  'z-ingress-cimd.yaml', 'auth-policy.json', 'cli-auth-policy.yaml',
                  'tls-policy.json'} | EVIDENCE_FILES


def evidence_errors(paths, approved_images=False, production=True, require_for_additional=True):
    names = {PurePosixPath(path).name for path in paths}
    supplied = names & EVIDENCE_FILES
    additional = sorted(name for name in names if name not in STANDARD_FILES
                        and name.endswith(('.yaml', '.yml'))
                        and not name.endswith(('.enc.yaml', '.enc.yml')))
    if supplied and supplied != EVIDENCE_FILES:
        return ['Image release evidence is incomplete; missing ' + ', '.join(sorted(EVIDENCE_FILES - supplied))
                + '. Obtain the complete handoff through the hosted authorize_image.py helper.']
    if production and require_for_additional and additional and not supplied and not approved_images:
        return ['Production bundle includes additional resources (' + ', '.join(additional)
                + '), including storage/configuration resources even with a single image. '
                'Include image-policy.yaml, image-release.json, and image-release.bundle.jsonl '
                'from hosted platform image authorization. Hosted validation verifies signed evidence '
                'or an exact platform-reviewed image baseline.']
    return []
