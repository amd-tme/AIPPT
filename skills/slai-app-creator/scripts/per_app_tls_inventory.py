"""Credential-free, shared enrollment policy for deployment and rotation."""
import json
from pathlib import Path
import re

PROTOCOL = 'per-app-tls-v1'
LABEL = re.compile(r'^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')
LEGACY_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$')
RESOURCE = re.compile(r'^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$')

# Reviewed exceptions preserve existing URLs. These are not hostname choices
# offered to new deployments. Shared-host profiles are platform-only and can
# never be selected by an application's tls-policy.json.
LEGACY_PROFILES = {
    'platform-apex': {'hostname': 'slai-app.amd.com', 'ingress': 'competes-am-regen',
                      'file': None, 'shared': True},
    'platform-dcgpu-hub': {'hostname': 'dcgpu-hub.amd.com', 'ingress': 'dcgpu-hub-vanity',
                           'file': None, 'shared': True},
    'gce-hub': {'hostname': 'gce-hub.amd.com', 'ingress': 'gce-hub-vanity',
                'file': 'z-ingress-vanity.yaml', 'shared': False},
    'platform-sso-keycloak': {'hostname': 'sso.slai-app.amd.com', 'ingress': 'platform-sso-keycloak',
                              'file': 'z-ingress.yaml', 'shared': False},
    'slai-registry': {'hostname': 'slai-registry.amd.com', 'ingress': 'hosted-slai-slai-registry',
                      'file': 'z-ingress.yaml', 'shared': False},
}
SHARED_INGRESSES = {
    'platform-apex': (
        'competes-am-regen', 'gce-hub', 'hosted-slai-aippt',
        'hosted-slai-coresperf-ai-telemetry', 'hosted-slai-dcgpu-hub',
        'hosted-slai-harbor-cli-proxy', 'hosted-slai-hello-devops', 'hosted-slai-hello-world',
        'hosted-slai-hima', 'hosted-slai-instinct-signals', 'hosted-slai-ldap-oauth',
        'hosted-slai-llm-sizer', 'hosted-slai-pcie-dv-ai-tools-tutorial',
        'hosted-slai-pr-coverage-dashboard', 'hosted-slai-rocm-ai-apex-redirect',
        'hosted-slai-rocm-cli', 'hosted-slai-rocm-cli-feedback', 'slai-asset-submission'),
    'platform-dcgpu-hub': ('dcgpu-hub-vanity', 'umami-vanity'),
}


def profile_target(name, enabled=True):
    profile = LEGACY_PROFILES.get(name)
    if profile is None:
        raise ValueError('Unknown reviewed legacy TLS profile')
    return dict(app_id=name, enabled=enabled, deployment_enabled=not profile['shared'],
                namespace='slai-app-prod', hostname=profile['hostname'], ingress=profile['ingress'],
                secret_name=name + '-tls', legacy_profile=name)


def ingress_filename(target):
    profile = LEGACY_PROFILES.get(target.get('legacy_profile'))
    return profile['file'] if profile else 'z-ingress.yaml'


def shared_profile(target):
    return LEGACY_PROFILES.get(target.get('legacy_profile'), {}).get('shared', False)


def read_json(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise ValueError('Invalid TLS policy file')
    return json.loads(path.read_text())


def validate_target(t):
    if isinstance(t, dict) and 'legacy_profile' in t:
        if (type(t.get('enabled')) is not bool or t != profile_target(t['legacy_profile'], t['enabled'])):
            raise ValueError('Legacy TLS target differs from its reviewed profile')
        return t
    if isinstance(t, dict) and t.get('app_id') in LEGACY_PROFILES:
        raise ValueError('Reserved legacy identity requires its reviewed TLS profile')
    if (set(t) != {'app_id', 'enabled', 'deployment_enabled', 'namespace', 'hostname', 'ingress', 'secret_name'}
            or type(t['enabled']) is not bool or type(t['deployment_enabled']) is not bool
            or not isinstance(t['app_id'], str) or not LABEL.fullmatch(t['app_id']) or len(t['app_id']) > 63
            or any(not isinstance(t[k], str) or len(t[k]) > 253 or not RESOURCE.fullmatch(t[k]) for k in ('ingress', 'secret_name'))
            or t['namespace'] != 'slai-app-prod'
            or t['hostname'] != t['app_id'] + '.slai-app.amd.com'
            or not t['secret_name'].startswith(t['app_id'] + '-')
            or not (t['ingress'] == t['app_id'] or t['ingress'].startswith(t['app_id'] + '-')
                    or t['ingress'] == 'hosted-slai-' + t['app_id'])):
        raise ValueError('Invalid TLS target')
    return t


def target_from_policy(app_id, policy):
    if (not isinstance(policy, dict) or set(policy) not in ({'version', 'mode', 'ingress'}, {'version', 'mode', 'ingress', 'legacy_profile'})
            or type(policy['version']) is not int or policy['version'] != 1
            or policy['mode'] != 'platform-managed'):
        raise ValueError('Update your slai-app-creator: a platform-managed tls-policy.json is required')
    if app_id in LEGACY_PROFILES:
        if LEGACY_PROFILES[app_id]['shared']:
            raise ValueError('Shared-host certificate identities are reserved to the platform')
        if 'legacy_profile' not in policy:
            raise ValueError('Existing legacy hostname requires its reviewed TLS profile')
    if 'legacy_profile' in policy:
        target = profile_target(policy['legacy_profile'])
        if app_id != target['app_id'] or shared_profile(target) or policy['ingress'] != target['ingress']:
            raise ValueError('An app may select only its own reviewed non-shared legacy TLS profile')
        return target
    return validate_target(dict(app_id=app_id, namespace='slai-app-prod', hostname=app_id + '.slai-app.amd.com',
                                secret_name=app_id + '-tls', ingress=policy['ingress'], enabled=True,
                                deployment_enabled=True))


def load_inventory(root, policy_root=None):
    root = Path(root)
    data = read_json(Path(policy_root or root) / 'config/per-app-tls.json')
    if (data.get('version') != 1 or type(data.get('renew_before_days')) is not int
            or not 1 <= data['renew_before_days'] <= 90 or not isinstance(data.get('targets'), list)):
        raise ValueError('Invalid TLS inventory version or renewal threshold')
    targets = {}
    for target in data['targets']:
        validate_target(target)
        if target['app_id'] in targets:
            raise ValueError('Duplicate TLS target')
        targets[target['app_id']] = target
    cutover = data.get('cutover', {})
    if cutover:
        if (cutover.get('protocol') != PROTOCOL or type(cutover.get('enabled')) is not bool
                or not isinstance(cutover.get('legacy_apps'), list)
                or any(not isinstance(a, str) or not LEGACY_ID.fullmatch(a) for a in cutover['legacy_apps'])
                or len(set(cutover['legacy_apps'])) != len(cutover['legacy_apps'])):
            raise ValueError('Invalid TLS cutover policy')
        if cutover['enabled']:
            for app in sorted((root / 'deploy/slai-app-prod').iterdir()):
                if not app.is_dir():
                    continue
                if app.is_symlink():
                    raise ValueError('App directories cannot be symbolic links')
                policy = app / 'tls-policy.json'
                if (policy_root and app.name not in targets and not policy.exists()
                        and (Path(policy_root) / 'deploy/slai-app-prod' / app.name / 'tls-policy.json').is_file()):
                    raise ValueError('Managed app must retain tls-policy.json: ' + app.name)
                if policy.exists():
                    derived = target_from_policy(app.name, read_json(policy))
                    if app.name in targets and targets[app.name] != derived:
                        raise ValueError('TLS policy conflicts with explicit enrollment')
                    targets[app.name] = derived
                elif app.name not in targets and app.name not in cutover['legacy_apps']:
                    raise ValueError('New app requires tls-policy.json: ' + app.name)
    ownership = data.get('ownership')
    automation = data.get('automation')
    if automation is not None and (not isinstance(automation, dict) or set(automation) != {'merge_after_checks'}
                                   or type(automation['merge_after_checks']) is not bool):
        raise ValueError('Invalid certificate merge automation policy')
    if ownership is not None and (not isinstance(ownership, dict) or set(ownership) != {'group', 'org_unit'}
                                  or any(not isinstance(v, str) or not v.strip() or len(v) > 128 for v in ownership.values())):
        raise ValueError('Invalid platform certificate ownership')
    return dict(data, targets=list(targets.values()))


def rotation_targets(data, app_id='', changed_paths=None):
    selected = [t for t in data['targets'] if t['enabled'] and (not app_id or t['app_id'] == app_id)]
    if changed_paths is not None:
        changed = set(changed_paths)
        selected = [t for t in selected
                    if changed.intersection({'tls/apps/' + t['app_id'] + '/secret.enc.yaml',
                                             'tls/apps/' + t['app_id'] + '/certificate.json'})
                    and 'tls/requests/' + t['app_id'] + '.json' not in changed]
    return selected


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--policy-root', type=Path)
    args = parser.parse_args()
    try:
        data = load_inventory(args.root, args.policy_root)
        print('TLS enrollment valid: ' + str(len(data['targets'])) + ' managed apps')
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        parser.exit(1, str(error) + '\n')
