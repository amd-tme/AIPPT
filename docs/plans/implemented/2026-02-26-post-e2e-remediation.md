## Context

Use an agent team as needed to work through these items. The goal is to integrate the `feature/sections` branch, clean up remaining issues from the code review, and run the full E2E pipeline test suite to confirm everything works together.

We're on the `actually-useful` branch of Outline2PPT. In the previous session we committed 3 fixes and 2 features across 3 commits (`194cf26`, `48783ca`, `7176a3e`). The unit test suite is at 289 tests, all passing. The full E2E pipeline (24 tests, 10 ordered steps) passed in the prior session and needs to be re-run after the merge and cleanups below.

### What was completed in the previous session

1. **`.PNG` case sensitivity** — Added uppercase `.PNG` to extension searches in both `cli.py` and `catalog.py`
2. **SQLite connection contention** — Moved `conn.close()` in `cmd_analyze` to immediately after `fetchall()`, fixing the tag count = 0 anomaly in E2E Step 10
3. **conftest fixture override** — Added local `patch_default_config_path` overrides in both `test_e2e_pipeline.py` and `test_gateway_live.py`
4. **WSL path translation** — Added `_is_wsl()`, `_wsl_to_windows_path()`, `_is_windows_powershell()` helpers to auto-convert Linux paths for PowerShell on WSL
5. **Text-only analysis fallback** — `analyze_slide()` now falls back to text-only LLM prompts when images are unavailable or detected as placeholders (13 new tests)

### Current branch state

```
actually-useful: 7176a3e  (HEAD, 7 commits ahead of main)
feature/sections: b3ff6eb (origin, 2 commits ahead of main — PRD + implementation)
Common ancestor: 26a7886
```

## What Needs To Be Done

### 1. Merge `origin/feature/sections` into `actually-useful` (first, before anything else)

The `feature/sections` branch adds PowerPoint section support — reading/writing sections via XML, database tables (`sections`, `slide_sections`), and integration across catalog, search, create, reverse, export, and remix workflows. It also adds `outline2ppt/sections.py` (new file) and `tests/test_sections.py` (142 tests).

**Expected merge conflicts** in files modified by both branches:
- `outline2ppt/catalog.py` — sections branch adds section-reading to `catalog_deck()`; our branch added `.PNG` extension fix and is the same area
- `outline2ppt/cli.py` — sections branch adds `--section` flags; our branch added WSL helpers, text-only fallback, and moved `conn.close()`
- `outline2ppt/export.py` — sections branch adds section column
- `outline2ppt/parser.py` — sections branch adds H1-as-section detection
- `outline2ppt/ppt2outline.py` — sections branch adds section output
- `outline2ppt/remix.py` — sections branch adds section preservation
- `outline2ppt/schema.sql` — sections branch adds `sections` and `slide_sections` tables
- `tests/test_catalog.py` — sections branch adds 145 lines of catalog tests
- `tests/test_parser.py` — sections branch modifies existing tests

**Merge strategy:**
```bash
git fetch origin
git merge origin/feature/sections --no-edit
# Resolve conflicts, keeping both sets of changes
# Run tests after each conflict resolution
```

After merging, run the full unit test suite to confirm no regressions.

### 2. Remove dead `analyze_deck()` function (quick)

`outline2ppt/analyze.py` contains an `analyze_deck()` function (around line 307) that is never called from anywhere in the codebase. It still uses the old "skip if no image" behavior and was not updated when the text-only fallback was added. Rather than update dead code, remove it. The CLI uses `cmd_analyze` directly.

Key location:
- `outline2ppt/analyze.py` — `analyze_deck()` function (~lines 307-385)

### 3. Fix `claude-sonnet-4` model reference in `test_gateway_live.py`

`test_anthropic_gateway_chat()` at `tests/test_gateway_live.py:76` creates an `LLMClient(model="claude-sonnet-4", ...)` but `models.yaml` registers the model as `claude-sonnet-4-6`. This causes the test to fail with a model-not-found error even when the gateway key is set. Update the model name to match the registry, or add a `claude-sonnet-4` alias to `models.yaml`.

Key location:
- `tests/test_gateway_live.py:76` — model name string

### 4. Add unit tests for `_extract_slide_text` helper

The `_extract_slide_text()` helper in `cli.py` (around line 600) drives which text is sent to the LLM in text-only mode, but has no unit tests. Add tests covering:
- Basic text extraction from a slide with multiple text shapes
- Title shape exclusion (text matching the slide title is skipped)
- Empty slide returns empty string
- Shapes without text frames are skipped

Key location:
- `outline2ppt/cli.py` — `_extract_slide_text()` function
- `tests/test_cli.py` — add test class here

### 5. Update E2E tests for sections support (if needed after merge)

After merging `feature/sections`, the E2E test outlines (`tests/e2e_outlines/*.md`) may need updates to exercise section functionality. The sections branch brings its own `test-sections.md` outline and `tests/test_sections.py` (142 tests), but the E2E pipeline should verify sections work through the full create → catalog → analyze → search → export → remix flow.

Check whether:
- The existing E2E outlines use H1 headers that would trigger the section parser
- The E2E Step 10 summary should report section counts
- The E2E catalog step correctly stores sections in the database

Key locations:
- `tests/test_e2e_pipeline.py` — all 10 steps
- `tests/e2e_outlines/` — markdown test outlines
- `outline2ppt/sections.py` — section reading/writing

### 6. Run the full E2E pipeline test suite (final verification)

After completing items 1-5, run the full E2E pipeline to confirm everything works together, including the tag count fix from the previous session.

```bash
# Unit tests first (should be ~430+ with sections tests merged)
venv/bin/python -m pytest tests/ --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_gateway_live.py -q

# E2E steps 1-3 (fast, no LLM needed)
venv/bin/python -m pytest tests/test_e2e_pipeline.py -k "test_01 or test_02 or test_03" -v -s

# Full E2E pipeline (needs AMD_LLM_KEY, ~5 min)
venv/bin/python -m pytest tests/test_e2e_pipeline.py -v -s

# Gateway live tests (needs AMD_LLM_KEY)
venv/bin/python -m pytest tests/test_gateway_live.py -v -s
```

**Key things to verify in E2E results:**
- Step 10 tag count > 0 (was 0 before the SQLite contention fix)
- Text-only analysis produces meaningful output (not "slide appears blank")
- Section data appears in catalog and export (after sections merge)
- All 24 E2E tests pass

## How to Verify

```bash
# Quick smoke test (unit tests only, ~3 seconds)
venv/bin/python -m pytest tests/ --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_gateway_live.py -q

# E2E steps 1-3 only (no LLM calls, ~10 seconds)
venv/bin/python -m pytest tests/test_e2e_pipeline.py -k "test_01 or test_02 or test_03" -v -s

# Full E2E (needs AMD_LLM_KEY, ~5 min)
venv/bin/python -m pytest tests/test_e2e_pipeline.py -v -s

# Gateway live tests (needs AMD_LLM_KEY, ~30 seconds)
venv/bin/python -m pytest tests/test_gateway_live.py -v -s
```

Work through items in order — the merge (item 1) must come first since everything else depends on having the sections code available.
