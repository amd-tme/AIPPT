# Design: End-to-End Pipeline Tests

**Date:** 2026-02-26
**Author:** Matt Elliott
**Status:** Approved

---

## Summary

Add script-based end-to-end tests that exercise the full Outline2PPT pipeline: create a deck from a markdown outline, export slide images via PowerShell, catalog the deck, run AI analysis (tags, feedback, notes, improvements) with real LLM API calls, save/export results, and analyze the feedback against python-pptx capabilities.

Three test decks cover different content types: a short technical overview, a mid-length mini-presentation, and a generic informational deck. Tests use the real `models.yaml` and `gateway.yaml` configuration and make actual LLM API calls via the AMD gateway.

## Motivation

- Existing tests use mocked LLM responses — they validate code paths but not the actual AI pipeline quality
- The `export-images` command has never been tested from WSL (and has a bug: hardcodes `powershell` instead of detecting `pwsh.exe`)
- The feedback-to-code loop (can LLM suggestions be applied via python-pptx?) has not been analyzed
- No test validates the full user workflow from outline to actionable analysis

## Test Decks

| Deck | Slides | Content | Purpose |
|------|--------|---------|---------|
| `tech_overview` | 3 | Title + Architecture Overview + Security Considerations | Technical content, bullet-heavy layouts |
| `mini_presentation` | 5 | Title + Agenda + Cloud Migration + Cost Analysis + Summary | Longer deck, varied content types |
| `generic_info` | 4 | Title + Q3 Project Update + Team Highlights + Next Steps | Non-technical, general business content |

## Test Pipeline (per deck)

```
Step 1: Write outline.md
  → Assert: file exists, correct H1 header count

Step 2: Create deck via cmd_create (no --enhance)
  → Assert: output.pptx exists, correct slide count

Step 3: Export images via PowerShell (skip if pwsh unavailable)
  → cmd_export_images → Slide1.png through SlideN.png
  → Assert: image files exist for each slide

Step 4: Catalog deck into SQLite
  → cmd_catalog with --images-dir
  → Assert: deck_id > 0, correct slide count in DB

Step 5: Generate tags (real LLM call)
  → cmd_analyze --mode tags
  → Assert: each slide has 1+ tags in DB

Step 6: Generate feedback (real LLM call)
  → cmd_analyze --mode feedback
  → Assert: non-empty feedback for each slide

Step 7: Generate notes (real LLM call)
  → cmd_analyze --mode notes
  → Assert: notes written back to PPTX

Step 8: Generate improvements (real LLM call)
  → cmd_analyze --mode improvements
  → Assert: result contains ## Visual Design, ## Technical Accuracy, etc.

Step 9: Export feedback to markdown file
  → Write results to exports/deck-name-feedback.md
  → Assert: file exists, non-empty

Step 10: Capability analysis
  → Classify feedback items against python-pptx capability matrix
  → Write to exports/deck-name-capability-analysis.md
```

## Capability Matrix

Maps common LLM feedback categories to python-pptx support levels:

| Category | Support | python-pptx API |
|---|---|---|
| Font size/style | Full | `paragraph.font.size = Pt(14)` |
| Font color | Full | `paragraph.font.color.rgb = RGBColor(...)` |
| Text content | Full | `shape.text_frame.text = "..."` |
| Bold/italic/underline | Full | `run.font.bold = True` |
| Bullet formatting | Full | `paragraph.level = 1` |
| Speaker notes | Full | `slide.notes_slide.notes_text_frame.text` |
| Shape position/size | Full | `shape.left`, `shape.width` |
| Add/remove shapes | Full | `slide.shapes.add_textbox()`, element removal |
| Background color | Full | `slide.background.fill.solid()` |
| Table formatting | Full | Cell text, merging, borders |
| Layout selection | Partial | Can switch but template must have layouts |
| Color palette | Partial | Individual colors, no theme swap |
| Image replacement | Partial | Add/replace images, not edit them |
| Slide reordering | Partial | XML manipulation required |
| Complex diagrams | None | Cannot create SmartArt programmatically |
| Animations | None | Not supported by python-pptx |
| 3D effects | None | Not supported |
| Chart redesign | Limited | Modify data, limited styling |

The capability analysis step classifies each bullet point from the improvements feedback against this matrix using keyword matching and writes a summary showing what percentage of feedback is actionable.

## Bug Fix: PowerShell Detection

`cmd_export_images` (cli.py:598) hardcodes `"powershell"` which doesn't resolve on WSL. Fix: detect available PowerShell executable from a priority list: `pwsh.exe`, `pwsh`, `powershell.exe`, `powershell`.

## Test Infrastructure

**File:** `tests/test_e2e_pipeline.py`
**Marker:** `@pytest.mark.e2e`
**Skip conditions:**
- `AMD_LLM_KEY` not set → skip all E2E tests
- `pwsh.exe` not found → skip export-images step (continue with rest of pipeline using programmatically-generated placeholder images)

**Outline files:** `tests/e2e_outlines/` directory with 3 markdown files

**Config:** Uses real `models.yaml` and `gateway.yaml` from project root (not test fixtures)

**pytest marker** added to `pyproject.toml`:
```ini
[tool.pytest.ini_options]
markers = ["e2e: end-to-end tests requiring API keys and optional PowerPoint"]
```

### Running

```bash
# E2E tests only
AMD_LLM_KEY=<key> python -m pytest tests/test_e2e_pipeline.py -m e2e -v -s

# Everything except E2E
python -m pytest tests/ -v -m "not e2e"
```

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Fix `cmd_export_images` PowerShell detection | `outline2ppt/cli.py` | — |
| 2 | Create 3 test outline markdown files | `tests/e2e_outlines/*.md` | — |
| 3 | Add `e2e` marker to pytest config | `pyproject.toml` | — |
| 4 | Write E2E test fixtures (workspace, config, skip logic) | `tests/test_e2e_pipeline.py` | 1, 2, 3 |
| 5 | Write pipeline test: create + export-images + catalog | `tests/test_e2e_pipeline.py` | 4 |
| 6 | Write pipeline test: analyze (tags, feedback, notes, improvements) | `tests/test_e2e_pipeline.py` | 5 |
| 7 | Write capability analysis logic and export | `tests/test_e2e_pipeline.py` | 6 |
| 8 | Run full E2E suite and verify | — | all |

## Estimated Cost

- 12 slides across 3 decks × 4 analysis modes = 48 LLM calls
- Vision model (claude-sonnet-4-6), ~500-1000 tokens per response
- ~$0.50-1.00 per full test run
