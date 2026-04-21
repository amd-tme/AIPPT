# PRD: Unified Ingest Command

**Date:** 2026-02-26
**Author:** Matt Shams
**Status:** In Progress

---

## Summary

Add an `ingest` CLI subcommand that automates the PowerPoint ingestion pipeline — image export, cataloging, and optional tag generation — in a single invocation. Today this requires 3 separate commands with manually coordinated paths; `ingest` reduces it to one.

## Motivation

- **Problem:** Ingesting a deck requires running `export-images`, `catalog`, and optionally `analyze --mode tags` in sequence, each with matching `--images-dir` and `--db` flags. This is error-prone and tedious.
- **Who benefits:** Any user building a slide library — the primary use case for Outline2PPT's catalog/search/remix workflow.
- **If we don't do this:** Users continue running 3+ commands manually, increasing friction and likelihood of mismatched paths.

## Requirements

### Must Have

- [x] New `ingest` subcommand that runs export-images → catalog in sequence
- [x] `--tags` flag to optionally run tag generation after cataloging
- [x] Hard failure with clear error if PowerShell/PowerPoint is unavailable for image export
- [x] Auto-derived `--images-dir` default (`images/<deck-name>/`) matching existing convention
- [x] Progress output showing each step as it runs
- [x] Summary output at completion (deck_id, slide count, tag count if applicable)
- [x] Support for existing flags: `--db`, `--taxonomy`, `--model`, `--gateway-config`, `--api-key`, `--width`, `--height`

### Nice to Have

- [ ] `--skip-images` flag to skip export and catalog with existing/no images (for re-ingestion or text-only environments)

### Out of Scope

- Batch/directory mode (users can loop in shell)
- Running feedback, notes, or improvements modes during ingest (run separately)
- Web UI integration (future work)

---

## Design

### Approach

Add a `cmd_ingest()` function to `cli.py` that orchestrates calls to the existing internal functions: `cmd_export_images()` for PNG export, `catalog_deck()` for database ingestion, and `cmd_analyze()` for optional tagging. No new modules needed — this is pure orchestration of existing capabilities.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/cli.py` | Modified | Add `cmd_ingest()` function and `ingest` subparser to `build_parser()` |

### Data Model Changes

No data model changes. Uses existing `decks`, `slides`, `tags`, `slide_tags`, `sections`, `slide_sections` tables.

---

## CLI Changes

### New Commands

```
outline2ppt ingest <deck> [--images-dir DIR] [--db PATH]
                          [--tags] [--taxonomy CSV] [--model MODEL]
                          [--gateway-config YAML] [--api-key KEY]
                          [--width N] [--height N]
```

**Arguments:**
- `deck` (required): Path to the PowerPoint file

**Options:**
- `--images-dir DIR`: Directory for exported PNG images (default: `images/<deck-name>/`)
- `--db PATH`: SQLite database path (default: `slides.db`)
- `--tags`: Enable AI tag generation after cataloging
- `--taxonomy CSV`: Constrain tags to taxonomy file (implies `--tags`)
- `--model MODEL`: LLM model override for tag generation (default: from models.yaml)
- `--gateway-config YAML`: Path to gateway configuration file
- `--api-key KEY`: Direct API key for LLM provider
- `--width N`: Image export width in pixels (default: 1920)
- `--height N`: Image export height in pixels (default: 1080)

### Example Usage

```bash
# Basic ingest: export images + catalog
python outline2ppt.py ingest my-deck.pptx

# Ingest with auto-generated tags
python outline2ppt.py ingest my-deck.pptx --tags --model gpt-4o

# Ingest with taxonomy-constrained tags
python outline2ppt.py ingest my-deck.pptx --tags --taxonomy tags.csv

# Custom paths
python outline2ppt.py ingest my-deck.pptx --images-dir /data/images/my-deck/ --db /data/slides.db
```

### Modified Commands

None. Existing `export-images`, `catalog`, and `analyze` commands remain unchanged.

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_cli.py` | `TestIngestCommand` | Argument parsing, step orchestration with mocked internals, error handling on export failure, `--tags` flag behavior, `--taxonomy` implies `--tags` |

### Integration Tests

The existing E2E pipeline (`tests/test_e2e_pipeline.py`) already validates the export → catalog → analyze flow. A lightweight integration test can verify `cmd_ingest` calls the steps in order with correct arguments.

### Manual Testing

1. `python outline2ppt.py ingest deck.pptx` — images exported, deck cataloged, summary printed
2. `python outline2ppt.py ingest deck.pptx --tags` — same as above + tags generated and stored
3. Run on system without PowerShell — clear error message, no partial state

---

## Changelog Entry

```markdown
### Added
- `ingest` CLI command: one-step PowerPoint ingestion (image export + catalog + optional tagging)
```

---

## Implementation Tasks

| # | Task | Files | Status |
|---|------|-------|--------|
| 1 | Add `ingest` subparser + stub `cmd_ingest()` | `cli.py`, `tests/test_cli.py` | Done (96ef677) |
| 2 | Implement `cmd_ingest` — export + catalog + optional tags | `cli.py`, `tests/test_cli.py` | Done (9d717ee) |
| 3 | Add `--tags` step tests for `cmd_ingest` | `tests/test_cli.py` | Pending |
| 4 | Manual smoke test + final cleanup | -- | Pending |

### Remaining work

- **Task 3:** Add tests covering `--tags` flag triggering `cmd_analyze`, `--taxonomy` passthrough, and tag failure resilience (non-fatal).
- **Task 4:** Verify `outline2ppt.py ingest --help` works (add `ingest` to `outline2ppt.py` subcommands set on line 19). Run full test suite. Remove redundant `import argparse` inside `cmd_ingest` body.
- **Code review note:** `outline2ppt.py` wrapper script's `subcommands` set does not include `ingest` yet — must be added or the legacy wrapper will misroute the command.

---

## Risks & Open Questions

- **Risk:** Image export is platform-dependent (requires PowerShell + PowerPoint). Mitigated by hard failure with clear error message rather than silent degradation.
- **Question (resolved):** Whether to support `--skip-images` for text-only environments — deferred to nice-to-have; users can run `catalog` directly for that workflow.
- **Note:** `--taxonomy` does NOT imply `--tags` — both must be specified explicitly. This was a deliberate design choice confirmed during brainstorming.

---

## References

- Implementation plan: `docs/plans/2026-02-26-ingest-command.md`
- Related PRDs: `docs/plans/2026-02-26-post-e2e-remediation.md` (context for E2E testing)
- E2E test results: `docs/plans/2026-02-26-e2e-test-results.md`
- Branch: `feature/ingest` (worktree at `~/git/aippt-ingest`, based on `actually-useful`)
- Tests: 326 passing (9 ingest-specific: 4 parser + 5 orchestration)
