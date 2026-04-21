## Context

Use an agent team as needed to resolve these issues and prepare for additional testing.

We're on the `actually-useful` branch of Outline2PPT. We just completed running the full E2E pipeline test suite (`tests/test_e2e_pipeline.py` — 24 tests, 10 ordered steps) and all 24 tests pass. During the test run we found and fixed two bugs:

1. **conftest autouse fixture override** — `tests/conftest.py` has an autouse, function-scoped `patch_default_config_path` that redirects `DEFAULT_CONFIG_PATH` to a nonexistent temp path. This was overwriting the E2E test's module-scoped `real_models_yaml` fixture. Fixed by adding a local no-op `patch_default_config_path` override in `test_e2e_pipeline.py` that depends on `real_models_yaml`.

2. **Case-sensitive `.PNG` extension** — `outline2ppt/cli.py:380` only checked lowercase `.png` when searching for slide images, but PowerShell exports and placeholder images use uppercase `.PNG`. On Linux this caused all slides to be skipped during analysis. Fixed by adding `.PNG` to the extension search list.

Neither fix has been committed yet. The full test results with detailed breakdowns are at `docs/plans/2026-02-26-e2e-test-results.md`.

## Uncommitted Changes

- `outline2ppt/cli.py` — Added `.PNG` to image extension search (line 380)
- `tests/test_e2e_pipeline.py` — Added local `patch_default_config_path` fixture override

## What Needs To Be Done

### 1. Commit the two bug fixes (quick)

Stage and commit the changes to `cli.py` and `test_e2e_pipeline.py` on the `actually-useful` branch. Run the full non-E2E test suite first to confirm no regressions (`venv/bin/python -m pytest tests/ --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_gateway_live.py -q`).

### 2. Fix the Step 10 tag count = 0 anomaly

The E2E summary (Step 10) reports `Unique tags applied: 0` from `SELECT COUNT(DISTINCT tag_id) FROM slide_tags`, even though Step 4 successfully generates and verifies tags via `get_slide_tags()`. Investigate whether this is a db_path mismatch, a query against the wrong database file, or a schema issue. The relevant code is in `test_e2e_pipeline.py` around line 621 and `outline2ppt/catalog.py` in the `add_tags`/`get_slide_tags` functions.

### 3. Fix `test_gateway_live.py` (same conftest issue)

`tests/test_gateway_live.py` fails with the same `models.yaml not found` error as the E2E tests had before our fix. Apply the same pattern: add a local `patch_default_config_path` fixture override that points to the real `models.yaml`, or restructure the fixture to not need the override.

### 4. Fix WSL path translation for image export (biggest impact)

This is the highest-impact improvement. `cmd_export_images` in `cli.py` passes Linux paths (e.g., `/tmp/pytest-of-matt/.../deck.pptx`) to PowerShell running on the Windows side. PowerShell can't access these paths. The fix should detect WSL and convert paths to the `\\wsl$\<distro>\...` format using `wslpath -w` before passing them to PowerShell. Key locations:
- `_find_powershell()` at `cli.py:575`
- `cmd_export_images()` at `cli.py:585`
- The PowerShell script at `scripts/Export-SlidesToImages.ps1`

Getting real slide images would dramatically improve LLM analysis quality — currently all feedback is dominated by "the slide appears blank" because the placeholder PNGs are white rectangles.

### 5. Consider text-only analysis fallback (medium priority)

When slide images are unavailable or are detected as placeholders, the analyze modes could skip the vision API and use a text-only prompt with the slide's title + bullet content from the PPTX. This would produce useful feedback even without images. The relevant code is in `outline2ppt/analyze.py` (`analyze_slide` function) and the CLI dispatch in `cli.py` around line 390.

## How to Verify

```bash
# Run unit tests (should be 276 passed)
venv/bin/python -m pytest tests/ --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_gateway_live.py -q

# Run E2E steps 1-3 (fast, no LLM)
venv/bin/python -m pytest tests/test_e2e_pipeline.py -k "test_01 or test_02 or test_03" -v -s

# Run full E2E (needs AMD_LLM_KEY, ~5 min)
venv/bin/python -m pytest tests/test_e2e_pipeline.py -v -s
```

Please start by reviewing the uncommitted diff (`git diff`), then work through the items above in order.
