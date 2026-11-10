from pathlib import Path

import main
import pytest


@pytest.mark.parametrize('api', ['slai.amd.com/v1alpha2', 'slai.amd.com/v1alpha3'])
def test_supported_image_policy_versions_pass_canonical_filename_fence(api):
    assert main._bundle_resource_errors({'apiVersion': api, 'kind': 'AppImagePolicy'},
                                       Path('image-policy.yaml'), 'example') == []


@pytest.mark.parametrize('api,kind', [
    ('slai.amd.com/v1alpha1', 'AppImagePolicy'),
    ('slai.amd.com/v1alpha4', 'AppImagePolicy'),
    ('slai.amd.com/v1alpha3', 'Deployment'),
    ('apps/v1', 'AppImagePolicy'),
])
def test_policy_version_support_does_not_allow_unknown_versions_or_resource_kinds(api, kind):
    assert main._bundle_resource_errors({'apiVersion': api, 'kind': kind},
                                       Path('image-policy.yaml'), 'example')


def test_policy_cannot_replace_a_workload_or_hide_under_an_extra_filename():
    doc = {'apiVersion': 'slai.amd.com/v1alpha3', 'kind': 'AppImagePolicy'}
    for filename in ['deployment.yaml', 'service.yaml', 'extra-policy.yaml']:
        assert main._bundle_resource_errors(doc, Path(filename), 'example')
