# Testing Results - 2026-02-20

## Environment
- **Branch**: `actually-useful`
- **Test deck**: `decks/4Q25-Instinct-Partitioning.pptx` (61 slides)
- **Slide images**: `decks/4Q25-Instinct-Partitioning/` (61 PNG files)
- **Python**: 3.14 (venv)
- **Platform**: Windows 11

## Test Results

| # | Test | Command | Result | Notes |
|---|------|---------|--------|-------|
| 1 | Reverse (PPTX to MD) | `aippt.py reverse decks/4Q25-Instinct-Partitioning.pptx decks/4Q25-Instinct-Partitioning-reversed.md` | PASS | 61 slides extracted. Titles, bullet content, and speaker notes all captured correctly. Diagram-heavy slides produce fragmented bullet lists (expected -- text shapes extracted individually). |
| 2 | Catalog (PPTX to SQLite) | `aippt.py catalog decks/4Q25-Instinct-Partitioning.pptx --images-dir decks/4Q25-Instinct-Partitioning --db decks/test-slides.db` | PASS | 61 slides cataloged. Image paths resolved to absolute paths. All tables created (decks, slides, tags, slide_tags, taxonomy). |
| 3 | Search | `aippt.py search --title-contains ROCm --db decks/test-slides.db` | STUB | "Search command not yet implemented" -- exits cleanly with warning. Expected; this is Task 12. |
| 4 | Export | `aippt.py export decks/4Q25-Instinct-Partitioning.pptx --db decks/test-slides.db --output decks/test-export.csv` | STUB | "Export command not yet implemented" -- exits cleanly with warning. Expected; this is Task 9-10. |
| 5 | Analyze (feedback mode) | `aippt.py analyze decks/4Q25-Instinct-Partitioning.pptx --mode feedback --images-dir decks/4Q25-Instinct-Partitioning --model gpt-4o --gateway-config gateway.yaml --db decks/test-slides.db` | PASS | All 61 slides analyzed via AMD LLM Gateway (gpt-4o, `llm-api.amd.com/OpenAI`). Each slide received structured design feedback (visual clarity, content density, layout effectiveness, suggestions). Gateway returned HTTP 200 for all requests. |
| 6 | Create (MD to PPTX) | `aippt.py create decks/4Q25-Instinct-Partitioning-reversed.md decks/4Q25-Instinct-Partitioning.pptx decks/test-roundtrip-output.pptx --test 5` | PASS | 5 slides created from reversed markdown using original PPTX as template. Progress saved after each slide. |

## Bug Found and Fixed

### UnicodeDecodeError on Windows (encoding issue)

**Symptom**: `UnicodeDecodeError: 'charmap' codec can't decode byte 0x9d` when running `create` with a markdown file containing Unicode characters (trademark symbols, checkmarks, etc.).

**Root cause**: Several `open()` calls in the codebase did not specify `encoding='utf-8'`, causing Windows to default to `cp1252`.

**Files fixed**:
- `aippt/cli.py:45` -- `open(args.outline, 'r')` -> `open(args.outline, 'r', encoding='utf-8')`
- `aippt/analyze.py:92` -- `open(csv_path, "r")` -> `open(csv_path, "r", encoding="utf-8")`
- `aippt/catalog.py:23` -- `open(SCHEMA_PATH)` -> `open(SCHEMA_PATH, encoding="utf-8")`

## Unit Tests

- **187 passing, 3 skipped** (as of last `pytest` run)
- Gateway tests skipped unless `AMD_LLM_KEY` env var is set

## Observations

1. **Reverse conversion**: Diagram-heavy slides (logical architecture diagrams) extract individual shape labels as separate bullet points. This is inherent to text extraction from PPTX shapes and is expected behavior.
2. **Catalog**: Untitled slides are stored with empty string title (vs. "Untitled Slide" in reverse output). Both behaviors are reasonable for their respective contexts.
3. **Gateway integration**: AMD LLM Gateway worked reliably for all 61 slides with `gpt-4o`. Authentication via `Ocp-Apim-Subscription-Key` header functioned correctly.
4. **Stubs**: Search (Task 12) and Export (Task 9-10) are properly stubbed -- they log a warning and exit cleanly rather than crashing.

## Next Steps

- Implement Tasks 9-10: Export module and CLI command
- Implement Tasks 11-12: Remix module, search, and remix CLI commands
- Task 13: FastAPI web UI
- Tasks 14-16: Requirements, docs, integration tests
