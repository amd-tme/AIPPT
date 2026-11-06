"""SOPS downloads are bounded and failures leave no cache partials."""
import hashlib
import importlib.util
import io
from pathlib import Path
import time

import pytest

HELPER = Path(__file__).resolve().parents[1] / 'scripts/private-sops-cache.py'
spec = importlib.util.spec_from_file_location('bounded_sops_cache', HELPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_download_aborts_before_writing_over_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'MAX_BINARY_BYTES', 8)
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(b'123456789'))
    target = tmp_path / 'binary'
    with pytest.raises(ValueError, match='size limit'):
        module.download_binary('https://example.invalid/binary', target)
    assert target.stat().st_size <= 8


def test_total_deadline_interrupts_blocked_read(tmp_path, monkeypatch):
    class SlowResponse(io.BytesIO):
        def read(self, count):
            time.sleep(2)
            return super().read(count)

    monkeypatch.setattr(module, 'MAX_DOWNLOAD_SECONDS', 0.05)
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *a, **k: SlowResponse(b'binary'))
    started = time.monotonic()
    with pytest.raises(TimeoutError, match='total duration limit'):
        module.download_binary('https://example.invalid/binary', tmp_path / 'binary')
    assert time.monotonic() - started < 1


def test_oversized_download_cleans_staging_directory(tmp_path, monkeypatch):
    cache = tmp_path / 'private-cache'
    monkeypatch.setenv('SOPS_CACHE_DIR', str(cache))
    monkeypatch.setattr(module, 'MAX_BINARY_BYTES', 8)
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(b'123456789'))
    with pytest.raises(ValueError, match='size limit'):
        module.main()
    assert list(cache.iterdir()) == []


def test_bounded_download_retains_checksum_verification(tmp_path, monkeypatch):
    data = b'synthetic-sops-binary'
    cache = tmp_path / 'private-cache'
    monkeypatch.setenv('SOPS_CACHE_DIR', str(cache))
    monkeypatch.setattr(module, 'DIGEST', hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(data))
    module.main()
    binary = cache / ('sops-' + module.VERSION)
    assert binary.read_bytes() == data
    assert binary.stat().st_mode & 0o777 == 0o700
    assert not list(cache.glob('.download-*'))
    binary.write_bytes(b'tamper')
    with pytest.raises(ValueError, match='checksum mismatch'):
        module.main()


def test_cached_sparse_binary_is_rejected_before_reading(tmp_path, monkeypatch):
    binary = tmp_path / 'binary'
    with binary.open('wb') as output:
        output.truncate(1024 * 1024)
    binary.chmod(0o700)
    monkeypatch.setattr(module, 'MAX_BINARY_BYTES', 8)
    with pytest.raises(ValueError, match='size limit'):
        module.verify(binary)
