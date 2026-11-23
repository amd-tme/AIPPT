from pathlib import Path
import subprocess
import sys


def test_missing_yaml_stops_before_manifest_validation():
    script = Path(__file__).parents[1] / 'scripts/main.py'
    code = "import sys, runpy; sys.modules['yaml'] = None; runpy.run_path(sys.argv[1], run_name='__main__')"
    result = subprocess.run([sys.executable, '-c', code, str(script)], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'PyYAML is required' in result.stderr
