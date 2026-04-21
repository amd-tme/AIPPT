# PRD: Remix & Analyze UX Polish

**Date:** 2026-03-02
**Author:** Matt
**Status:** Draft

---

## Summary

Two minor UX issues in the remix and analyze pipelines create unnecessary noise for users: (1) remix emits spurious "newer version" warnings when the source deck is the same as the cataloged deck, and (2) `analyze` silently auto-catalogs slides as a side effect, which can surprise users who only wanted analysis. This PRD addresses both.

## Motivation

- **What problem does this solve?** Spurious warnings erode user trust in the version detection system (crying wolf), and silent side effects make the tool less predictable.
- **Who benefits?** Users running remix and analyze workflows, especially those learning the tool.
- **What happens if we don't do this?** Users see confusing warnings they can't act on, and may not realize their database was modified by an analyze command.

## Requirements

### Must Have

- [ ] Remix suppresses version warnings when the manifest source deck is the same file as the cataloged deck
- [ ] Analyze logs a clear message when it auto-catalogs (e.g., "Auto-cataloging deck into slides.db (use --no-catalog to skip)")

### Nice to Have

- [ ] `analyze` gains `--no-catalog` flag to skip auto-cataloging
- [ ] Remix version check compares content hashes rather than timestamps to avoid false positives from re-ingestion

### Out of Scope

- Redesigning the version detection algorithm
- Changing the catalog/analyze dependency (analyze needs slide records to store results)

---

## Design

### Approach

**1. Suppress same-deck version warnings**

In `remix.py` `check_newer_versions()`, the function queries the catalog for slides with matching titles in other decks. When the "newer" deck is the same file as the source deck in the manifest, the warning is meaningless. Fix: compare `deck_path` from the manifest entry against the `newer_deck` path — if they resolve to the same file (using `os.path.realpath()`), skip the warning.

**2. Explicit auto-catalog logging**

In `analyze.py`, the catalog step already logs `Cataloged N slides from deck-name` at INFO level. Enhance this to be more explicit about what happened:
- Log: `"Auto-cataloging {deck_name} into {db_path} for analysis tracking"`
- If `--no-catalog` is passed, skip the catalog step but warn if the deck isn't already cataloged (analysis results won't be stored in DB).

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/remix.py` | Modified | `check_newer_versions()` skips warnings when newer deck matches source deck |
| `outline2ppt/analyze.py` | Modified | More explicit auto-catalog logging; optional `--no-catalog` flag support |
| `outline2ppt/cli.py` | Modified | Add `--no-catalog` option to `analyze` subcommand (nice-to-have) |

### Data Model Changes

No data model changes.

---

## CLI Changes

### New Commands

None.

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `analyze` | New option `--no-catalog` | Skip auto-cataloging the deck before analysis (nice-to-have) |

### Example Usage

```bash
# Standard analyze (auto-catalogs, now with explicit log message)
python outline2ppt.py analyze deck.pptx --mode notes

# Analyze without cataloging (deck must already be in DB for result storage)
python outline2ppt.py analyze deck.pptx --mode notes --no-catalog

# Remix without spurious warnings
python outline2ppt.py remix manifest.yaml output.pptx
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_remix.py` | `TestVersionCheck` | Verify same-deck warnings suppressed; cross-deck warnings still emitted |
| `tests/test_analyze.py` | `TestAutoCatalog` | Verify explicit log message; verify `--no-catalog` skips cataloging |

### Integration Tests

None required.

### Manual Testing

1. Ingest a deck, export manifest, remix from same deck → verify no version warnings
2. Ingest two decks with overlapping slide titles, remix from older deck → verify cross-deck version warning still appears
3. Run `analyze --mode notes` → verify log explicitly mentions auto-cataloging

---

## Changelog Entry

```markdown
### Fixed
- Remix no longer shows spurious "newer version" warnings when source deck matches cataloged deck

### Changed
- Analyze now explicitly logs when auto-cataloging a deck before analysis
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Suppress same-deck version warnings in `check_newer_versions()` | `outline2ppt/remix.py` | -- |
| 2 | Add explicit auto-catalog log message in analyze | `outline2ppt/analyze.py` | -- |
| 3 | Add `--no-catalog` flag to analyze CLI (nice-to-have) | `outline2ppt/cli.py`, `outline2ppt/analyze.py` | 2 |
| 4 | Add unit tests for version check filtering | `tests/test_remix.py` | 1 |
| 5 | Add unit tests for catalog logging | `tests/test_analyze.py` | 2 |
| 6 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Question:** Should `--no-catalog` be the default? Most users running `analyze` probably expect it to "just work" including cataloging. **Recommendation:** Keep auto-catalog as default, make `--no-catalog` opt-in.
- **Risk:** Path comparison for same-deck detection could fail with symlinks or relative vs absolute paths. Mitigation: use `os.path.realpath()` for normalization.
- **Question:** Should version warnings include the content hash diff to help users understand what changed? **Recommendation:** Not in this PRD — keep it simple. Content hash comparison is a nice-to-have for a future iteration.

---

## References

- Remix module: `outline2ppt/remix.py` `check_newer_versions()`
- Analyze module: `outline2ppt/analyze.py`
- Test results: `docs/plans/2026-03-02-test-results-and-future-work.md`
