"""Exercise smoke-test destination validation without a container or network."""
import json
import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).parents[1] / 'scripts/probe-smoke.sh'


def run_smoke(tmp_path, paths, host_port='18080', container_port='8080', timeout='30', base_path='null'):
    tools = tmp_path / 'bin'
    tools.mkdir()
    log = tmp_path / 'calls.jsonl'
    stub = '''#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
if name == 'yq':
    expression = sys.argv[3] if sys.argv[2] == '-r' else sys.argv[2]
    if 'containerPort' in expression:
        print(os.environ['TEST_CONTAINER_PORT'])
    elif '@json' in expression:
        print(os.environ['TEST_PROBE_PATHS'])
    else:
        print(os.environ['TEST_BASE_PATH'])
else:
    with open(os.environ['TEST_COMMAND_LOG'], 'a') as output:
        output.write(json.dumps([name, *sys.argv[1:]]) + '\\n')
    if name == 'curl' and '%{http_code}' in sys.argv:
        print('200')
'''
    for name in ('curl', 'docker'):
        tool = tools / name
        tool.write_text(stub)
        tool.chmod(0o700)
    handoff = tmp_path / 'handoff'
    handoff.mkdir()
    container = {'ports': [{'containerPort': int(container_port) if container_port.isdigit() else container_port}],
                 'env': [{'name': 'BASE_PATH', 'value': '' if base_path == 'null' else base_path}],
                 'livenessProbe': {'httpGet': {'path': paths[0]}},
                 'readinessProbe': {'httpGet': {'path': paths[1]}}}
    (handoff / 'deployment.yaml').write_text(json.dumps({'spec': {'template': {'spec': {'containers': [container]}}}}))
    env = os.environ.copy()
    env.update(PATH=str(tools) + os.pathsep + env['PATH'], IMAGE='test/image:fixture',
               ENGINE='docker', HANDOFF_DIR=str(handoff), HOST_PORT=host_port,
               TEST_CONTAINER_PORT=container_port, TEST_PROBE_PATHS=json.dumps(paths),
               TEST_COMMAND_LOG=str(log), PROBE_TIMEOUT=timeout, TEST_BASE_PATH=base_path)
    result = subprocess.run(['bash', str(SCRIPT)], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=10)
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return result, calls


@pytest.mark.parametrize('path', ['@attacker.example/healthz', 'https://attacker.example/healthz',
                                '', '/health z', '/health\n', '/health\n/other',
                                '/health\r', '/health\t', '/health\x00', '/health#fragment',
                                42, {'path': '/health'}])
def test_bad_path_fails_before_container_or_request(tmp_path, path):
    result, calls = run_smoke(tmp_path, ['/valid', path])
    assert result.returncode != 0
    assert calls == []
    assert 'invalid HTTP probe path' in result.stderr


@pytest.mark.parametrize('port', ['0', '65536', '99999999999999999999', 'x', '80@attacker.example', '-1'])
def test_bad_host_port_fails_before_container_or_request(tmp_path, port):
    result, calls = run_smoke(tmp_path, ['/health', None], host_port=port)
    assert result.returncode != 0
    assert calls == []
    assert 'HOST_PORT must be' in result.stderr


def test_valid_paths_keep_loopback_destination_and_disable_globbing(tmp_path):
    result, calls = run_smoke(tmp_path, ['/health', '/ready?check=[1,2]&account=@service'])
    assert result.returncode == 0, result.stderr
    requests = [call for call in calls if call[0] == 'curl']
    assert [call[-1] for call in requests] == [
        'http://127.0.0.1:18080/', 'http://127.0.0.1:18080/health',
        'http://127.0.0.1:18080/ready?check=[1,2]&account=@service']
    assert all('--globoff' in call for call in requests)
    run = next(call for call in calls if call[:2] == ['docker', 'run'])
    network = next(call for call in calls if call[:3] == ['docker', 'network', 'create'])
    assert '--internal' in network
    assert run[run.index('--network') + 1] == network[-1]
    assert any(call[:3] == ['docker', 'network', 'rm'] for call in calls)
    assert '--cap-drop=ALL' in run
    assert '--security-opt=no-new-privileges' in run
    assert '--user=65534:65534' in run


def test_invalid_default_host_port_fails_before_container(tmp_path):
    result, calls = run_smoke(tmp_path, ['/health', None], host_port='', container_port='60000')
    assert result.returncode != 0
    assert calls == []


@pytest.mark.parametrize('timeout', ['0', '3601', '999999999', 'abc', 'a[$(touch marker)]'])
def test_timeout_cannot_execute_arithmetic_input(tmp_path, timeout):
    result, calls = run_smoke(tmp_path, ['/health', None], timeout=timeout)
    assert result.returncode != 0
    assert calls == []
    assert not (tmp_path / 'marker').exists()
    assert 'PROBE_TIMEOUT must be' in result.stderr


def test_manifest_base_path_remains_one_environment_argument(tmp_path):
    value = '/app --privileged -v /:/host'
    result, calls = run_smoke(tmp_path, ['/health', None], base_path=value)
    assert result.returncode == 0, result.stderr
    arguments = next(call for call in calls if call[:2] == ['docker', 'run'])
    assert 'BASE_PATH=' + value in arguments
    assert '--privileged' not in arguments
    assert '/:/host' not in arguments


def test_probe_manifest_size_limit(tmp_path):
    manifest = tmp_path / 'deployment.yaml'
    with manifest.open('wb') as output:
        output.truncate(4 * 1024 * 1024 + 1)
    helper = SCRIPT.with_name('probe-manifest.py')
    result = subprocess.run(['python3', str(helper), str(manifest)], capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert not result.stdout
