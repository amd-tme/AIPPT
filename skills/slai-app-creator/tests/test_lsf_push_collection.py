import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from test_lsf_push_stamp import EVIDENCE

SKILL = Path(__file__).parents[1]


@pytest.mark.parametrize('verifier_status', [0, 1])
def test_collector_requires_successful_verifier_exit(tmp_path, verifier_status):
    push = tmp_path / 'scripts/lsf-push'
    build = tmp_path / 'scripts/lsf-build/scripts'
    tools = tmp_path / 'tools'
    for path in (push, build, tools):
        path.mkdir(parents=True)
    for name in ('result.sh', 'private-stamp.py'):
        shutil.copyfile(SKILL / 'scripts/lsf-push' / name, push / name)
    (build / 'build.sh').write_text('#!/bin/sh\nprintf "%s\\n" "' + str(tools) + '"\n')
    verifier = tools / 'image-push-lsf'
    log = tmp_path / 'evidence-path'
    verifier.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
# Emit fully parseable evidence even when returning failure.
print(os.environ['TEST_EVIDENCE'])
Path(os.environ['TEST_EVIDENCE_PATH']).write_text(os.readlink('/proc/self/fd/1'))
sys.exit(int(os.environ['TEST_VERIFIER_STATUS']))
''')
    verifier.chmod(0o700)
    job = tmp_path / 'job'
    (job / 'output').mkdir(parents=True)
    (job / 'output/success.json').write_text('{}')
    stamp = tmp_path / 'cache/harbor-last-image.env'
    env = os.environ.copy()
    env.update(TEST_EVIDENCE=json.dumps(EVIDENCE), TEST_VERIFIER_STATUS=str(verifier_status),
               TEST_EVIDENCE_PATH=str(log))
    result = subprocess.run(['sh', str(push / 'result.sh'), '--job-dir', str(job),
                             '--last-image-file', str(stamp)], env=env,
                            capture_output=True, text=True, timeout=10)
    assert (result.returncode == 0) == (verifier_status == 0), result.stderr
    assert stamp.exists() == (verifier_status == 0)
    assert not Path(log.read_text()).exists()
