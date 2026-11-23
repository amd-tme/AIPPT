import os
from pathlib import Path
import shutil
import subprocess

SKILL = Path(__file__).resolve().parents[1]


def test_go_configuration_isolated_for_every_invocation(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copyfile(SKILL / 'scripts/lsf-build/scripts/build.sh', scripts / 'build.sh')
    (scripts / 'host-preflight.sh').write_text('#!/bin/sh\nexit 0\n')
    (scripts / 'private-build-cache.py').write_text('')
    (tmp_path / 'src').mkdir()
    tools = tmp_path / 'tools'
    tools.mkdir()
    go = tools / 'go'
    go.write_text('''#!/usr/bin/env python3
import os, sys, pathlib
assert os.environ.get('GOFLAGS', '') == ''
assert os.environ.get('GOENV') == 'off'
assert os.environ.get('GOTOOLCHAIN') == 'local'
with open(os.environ['TEST_GO_LOG'], 'a') as f: f.write(sys.argv[1] + '\\n')
if sys.argv[1] == 'env': print('go9.0.0')
if sys.argv[1] == 'build': pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text('test binary')
''')
    # Resolve the synthetic compiler ahead of any newer installed toolchain.
    go.chmod(0o700)
    log = tmp_path / 'go.log'
    env = dict(os.environ, PATH=str(tools)+os.pathsep+os.environ['PATH'],
               XDG_CACHE_HOME=str(tmp_path/'cache'), TEST_GO_LOG=str(log),
               GOFLAGS='-toolexec=/synthetic/hostile-wrapper', GOENV='/synthetic/go-env',
               GOTOOLCHAIN='synthetic-toolchain')
    r = subprocess.run(['sh', str(scripts/'build.sh')], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    calls = log.read_text().splitlines()
    assert 'mod' in calls and 'test' in calls and calls.count('build') == 3
