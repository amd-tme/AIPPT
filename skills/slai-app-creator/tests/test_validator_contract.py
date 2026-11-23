"""Prevent publishing a contract that omits or misidentifies validator code."""
from pathlib import Path
import shutil
import pytest
from validator_contract import verify

ROOT = Path(__file__).resolve().parents[1]


def test_shipped_contract_covers_current_validators():
    assert verify(ROOT)['schema_version'] == 1


def test_changed_validator_cannot_keep_old_contract(tmp_path):
    target = tmp_path / 'skill'
    shutil.copytree(ROOT, target)
    path = target / 'scripts/bundle_resources.py'
    path.write_text(path.read_text() + '\n# changed after contract generation\n')
    with pytest.raises(ValueError, match='scripts/bundle_resources.py'):
        verify(target)
