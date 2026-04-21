# E2E Pipeline Test Results — 2026-02-26

## Summary

- **Branch:** `actually-useful`
- **Result:** 24/24 tests passed in 5:20
- **Platform:** Linux (WSL2), Python 3.10.16, pytest 9.0.2
- **LLM Gateway:** AMD LLM Gateway via `gateway.yaml`
- **Image Export:** Placeholder PNGs (PowerShell path translation issue)

## Step-by-Step Results

| Step | Test | Decks | Status | Duration | Notes |
|------|------|-------|--------|----------|-------|
| 1 | `test_01_create_deck` | 3 | PASSED | ~1.5s | No LLM. 3+5+4 = 12 slides created |
| 2 | `test_02_export_images` | 3 | PASSED | ~8s | PowerShell found but can't access Linux `/tmp/` paths; fell back to placeholder PNGs |
| 3 | `test_03_catalog_deck` | 3 | PASSED | ~1s | deck_id 1/2/3, all slides cataloged with content hashes |
| 4 | `test_04_analyze_tags` | 3 | PASSED | ~24s | Real LLM calls. 7 tags per slide, topically relevant |
| 5 | `test_05_analyze_feedback` | 3 | PASSED | ~95s | 3.7K–6.2K chars feedback per deck |
| 6 | `test_06_analyze_notes` | 3 | PASSED | ~70s | 12/12 slides got speaker notes written back to PPTX |
| 7 | `test_07_analyze_improvements` | 3 | PASSED | ~120s | 5.7K–8.4K chars improvements per deck |
| 8 | `test_08_export_feedback` | 1 | PASSED | <1s | 3 markdown files exported |
| 9 | `test_09_capability_analysis` | 1 | PASSED | <1s | Actionable items: 67–75% across decks |
| 10 | `test_10_summary` | 1 | PASSED | <1s | Summary printed, tag count anomaly noted |

## Deck Details

### Decks Created (Step 1)

| Deck | Outline File | Slides |
|------|-------------|--------|
| tech_overview | `tech_overview.md` | 3 |
| mini_presentation | `mini_presentation.md` | 5 |
| generic_info | `generic_info.md` | 4 |

### Tags Generated (Step 4)

| Deck | Slide | Tags |
|------|-------|------|
| tech_overview | 1: Cloud-Native Architecture Overview | cloud-native, architecture, containers, distributed-systems, microservices, overview |
| tech_overview | 2: Security Considerations | security, best practices, compliance, risk management, guidelines |
| tech_overview | 3: Performance and Scalability | performance, scalability, technical (+ blank/placeholder) |
| mini_presentation | 1: Cloud Migration Strategy | cloud-migration, strategy, infrastructure, planning |
| mini_presentation | 2: Agenda | agenda, outline, structure (+ blank/placeholder) |
| mini_presentation | 3: Migration Approach | migration, approach, strategy (+ blank/placeholder) |
| mini_presentation | 4: Cost Analysis | cost analysis, finance, economics (+ blank/placeholder) |
| mini_presentation | 5: Summary and Next Steps | summary, next steps, conclusion (+ blank/placeholder) |
| generic_info | 1: Q3 Project Status Update | status-update, project-management, q3 (+ blank/placeholder) |
| generic_info | 2: Project Milestones | milestones, timeline, planning (+ blank/placeholder) |
| generic_info | 3: Team Highlights | team, highlights (+ blank/placeholder) |
| generic_info | 4: Next Steps and Risks | next steps, risks, roadmap, planning, action items |

### Feedback (Step 5)

| Deck | Chars | Summary |
|------|-------|---------|
| tech_overview | 3,706 | 3 slides reviewed; all flagged as blank/invisible; generic best practices provided per slide topic |
| mini_presentation | 5,744 | 5 slides reviewed; same blank-image caveat; topic-specific recommendations (agenda structure, cost charts, etc.) |
| generic_info | 4,693 | 4 slides reviewed; recommendations for status update structure, milestone timelines, risk matrices |

### Speaker Notes (Step 6)

| Deck | Coverage | Quality |
|------|----------|---------|
| tech_overview | 3/3 | Notes reference blank images but provide relevant talking points based on titles |
| mini_presentation | 5/5 | Well-structured with markdown headers; agenda slide notes walk through presentation flow |
| generic_info | 4/4 | Project management context inferred from titles; actionable speaker guidance |

### Improvements (Step 7)

| Deck | Chars | Summary |
|------|-------|---------|
| tech_overview | 5,680 | Font hierarchy, contrast fixes, architecture diagram recommendations |
| mini_presentation | 8,394 | Migration terminology, phased layouts, cost breakdown chart suggestions |
| generic_info | 7,172 | RAG status indicators, milestone timelines, risk matrix format, two-column layouts |

### Capability Analysis (Step 9)

| Deck | Total Items | Actionable | Full | Partial | None | Unknown |
|------|------------|------------|------|---------|------|---------|
| tech_overview | 43 | 29 (67%) | 22 | 7 | 1 | 13 |
| mini_presentation | 56 | 42 (75%) | 31 | 11 | 0 | 14 |
| generic_info | 55 | 33 (60%) | 24 | 9 | 0 | 22 |

### Export Artifacts (Step 8)

| File | Size |
|------|------|
| tech_overview-feedback.md | 3,831 bytes |
| tech_overview-capability-analysis.md | 9,029 bytes |
| mini_presentation-feedback.md | 5,892 bytes |
| mini_presentation-capability-analysis.md | 12,385 bytes |
| generic_info-feedback.md | 4,819 bytes |
| generic_info-capability-analysis.md | 10,784 bytes |

## Bugs Found & Fixed

### 1. conftest autouse fixture overrides E2E models.yaml path

**Root cause:** `tests/conftest.py` has an `autouse=True`, function-scoped `patch_default_config_path` fixture that redirects `DEFAULT_CONFIG_PATH` to `tmp_path/models.yaml` (which doesn't exist). The E2E test's module-scoped `real_models_yaml` fixture patches to the real project-root `models.yaml`, but the conftest fixture runs after it on every test, overwriting the patch.

**Fix:** Added a local `patch_default_config_path` fixture override in `tests/test_e2e_pipeline.py` that depends on `real_models_yaml` and yields without patching, letting the module-scoped patch remain in effect.

**Files changed:** `tests/test_e2e_pipeline.py`

### 2. Case-sensitive image extension matching

**Root cause:** `cli.py:380` searches for slide images with extensions `(".png", ".jpg", ".jpeg")` — all lowercase. PowerPoint on Windows exports as `.PNG` (uppercase), and the test placeholder images also use `.PNG`. On Linux (case-sensitive filesystem), `Slide1.png` ≠ `Slide1.PNG`, so all slides were skipped with "No image for slide N."

**Fix:** Added `.PNG` to the extension search list in `cli.py:380`.

**Files changed:** `outline2ppt/cli.py`

## Outstanding Issues

### 1. WSL Path Translation (Step 2)

PowerShell is found and invoked (`pwsh.exe` from PATH), but receives Linux `/tmp/pytest-of-matt/...` paths that Windows can't access. PowerShell reports `File not found` and the test falls back to placeholder PNGs. To get real image export, paths need to be converted to `\\wsl$\Ubuntu\tmp\...` format.

**Impact:** All LLM analysis operates on blank white images, causing 50–70% of feedback to discuss visibility/contrast issues rather than actual slide content.

### 2. Summary Tag Count = 0 (Step 10)

The database summary query `SELECT COUNT(DISTINCT tag_id) FROM slide_tags` returns 0, even though Step 4 verified tags exist via `get_slide_tags()`. Likely a db_path mismatch or query scope issue.

### 3. `test_gateway_live.py` Pre-existing Failure

Same `models.yaml` config path issue as bug #1 — the conftest autouse fixture redirects to a nonexistent temp file. Needs the same local override pattern.

## Suggested Next Steps

### High Priority

1. **Fix WSL path translation for image export** — Convert Linux paths to `\\wsl$\...` format when calling PowerShell from WSL. Biggest impact on LLM analysis quality.
2. **Debug Step 10 tag count = 0** — Investigate db_path mismatch in summary query.
3. **Fix `test_gateway_live.py`** — Apply same conftest override pattern.
4. **Commit the two bug fixes** — conftest override + `.PNG` extension are ready.

### Medium Priority

5. **Add text-only analysis fallback** — When images are blank/placeholders, use text-only prompts instead of vision API. Would produce much better feedback without requiring real images.
6. **Reduce LLM API cost in CI** — Consider caching/mocking for CI runs, keeping real LLM tests behind `pytest -m e2e` marker.

### Lower Priority

7. **Improve capability matrix classification** — "Unknown" category is 25–40% of items. Refine regex patterns or add more categories to increase actionable percentage.
