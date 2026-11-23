"""Exercise batch argument construction without contacting LSF."""
import json
import os
from pathlib import Path
import shutil
import subprocess

SKILL = Path(__file__).resolve().parents[1]


def executable(path, contents):
    path.write_text(contents)
    path.chmod(0o700)


def test_build_job_disables_environment_inheritance(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copyfile(SKILL / 'scripts/lsf-build/scripts/submit.sh', scripts / 'submit.sh')
    executable(scripts / 'host-preflight.sh', '#!/bin/sh\nexit 0\n')
    (scripts / 'private-build-cache.py').write_text('')
    shutil.copyfile(SKILL / 'scripts/lsf-build/scripts/private-job-directory.py', scripts / 'private-job-directory.py')
    tools = tmp_path / 'tools'
    tools.mkdir()
    executable(scripts / 'build.sh', '#!/bin/sh\nprintf "%s\\n" "'+str(tools)+'"\n')
    executable(tools / 'image-build-lsf', '''#!/usr/bin/env python3
import pathlib, sys
output = pathlib.Path(sys.argv[sys.argv.index('--output') + 1])
output.write_bytes(b'synthetic tracked source snapshot')
print('{}')
''')
    command_log = tmp_path / 'bsub-arguments.json'
    (scripts / 'build.sh').chmod(0o600)
    fake_bsub = tmp_path / 'bsub'
    executable(fake_bsub, '''#!/usr/bin/env python3
import json, os, pathlib, sys
pathlib.Path(os.environ['TEST_BSUB_ARGUMENTS']).write_text(json.dumps(sys.argv[1:]))
print('Job <123> is submitted to queue <regr_high>.')
''')
    executable(tools / 'stat', '#!/bin/sh\necho nfs\n')
    app = tmp_path / 'app'
    app.mkdir()
    (app / 'Dockerfile').write_text('FROM scratch\n')
    env = os.environ.copy()
    env.update({'PATH': str(tools)+os.pathsep+env['PATH'],
                'OCI_LSF_BSUB': str(fake_bsub),
                'TEST_BSUB_ARGUMENTS': str(command_log),
                'HARBOR_PASSWORD': 'synthetic-environment-canary'})
    result = subprocess.run(['sh', str(scripts / 'submit.sh'), '--root', str(app),
                             '--lsf-project', 'authorized-test-project'],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    arguments = json.loads(command_log.read_text())
    assert arguments[arguments.index('-env')+1] == 'none'
    assert arguments[arguments.index('-P')+1] == 'authorized-test-project'
    assert arguments[arguments.index('-E')+1].startswith('sh ')
    assert 'synthetic-environment-canary' not in command_log.read_text()+result.stdout+result.stderr
    assert 'IMAGE_BUILD_LSF_JOB_DIR=' in result.stdout
