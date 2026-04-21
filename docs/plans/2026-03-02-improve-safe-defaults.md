# PRD: Safe Defaults for Improve Command

**Date:** 2026-03-02
**Author:** Matt
**Status:** Draft

---

## Summary

Change the `improve` command so it no longer overwrites the source PPTX file by default. Instead, it should write to a `-improved` suffixed output file unless the user explicitly opts into in-place overwrite with `--in-place`.

## Motivation

- **What problem does this solve?** The current default (`--output` not specified → overwrite the source file) is destructive and surprising. Users lose their original deck with no warning and no easy way to undo. This was discovered when `improve` silently overwrote a cataloged v6 deck, making the "original" and "improved" files identical.
- **Who benefits?** All users of the `improve` command — especially those iterating on decks where the original serves as a baseline.
- **What happens if we don't do this?** Users continue to lose original decks without realizing it, leading to confusion (e.g., download endpoint serving improved content for the "original" deck).

## Requirements

### Must Have

- [ ] When `--output` is not specified, auto-generate output path as `<stem>-improved<ext>` (e.g., `deck.pptx` → `deck-improved.pptx`)
- [ ] Add `--in-place` flag to explicitly opt into overwriting the source file
- [ ] If auto-generated output path already exists, warn and require `--overwrite` or append a numeric suffix (e.g., `deck-improved-2.pptx`)
- [ ] Print the output path clearly in the summary so users know where the file landed

### Nice to Have

- [ ] Detect if output path matches input path and treat as `--in-place` (so `--output deck.pptx` on input `deck.pptx` still warns)

### Out of Scope

- Backup/versioning of original files
- Undo/rollback functionality
- Changes to the `create` or `enhance` commands

---

## Design

### Approach

The change is isolated to `cmd_improve()` in `cli.py` (argument handling and output path resolution) and `improve_deck()` in `improve.py` (the `save_path` default). The core improve logic (LLM calls, slide rewriting) is unaffected.

1. **CLI layer (`cli.py`):** Replace `--output` default behavior. Add `--in-place` flag. Compute the default output path from the input path before calling `improve_deck()`.
2. **Library layer (`improve.py`):** Remove the `output_path or pptx_path` fallback. Require `output_path` to always be explicitly set by the caller — if `None`, raise `ValueError`.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/cli.py` | Modified | Add `--in-place` arg, compute default output path, pass explicit `output_path` to `improve_deck()` |
| `outline2ppt/improve.py` | Modified | Remove in-place default in `improve_deck()`, require explicit `output_path` |

### Data Model Changes

No data model changes.

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `improve` | New default output | Writes to `<stem>-improved.pptx` instead of overwriting source |
| `improve` | New flag `--in-place` | Explicitly overwrite the source file |
| `improve` | Existing collision handling | If output file exists, append numeric suffix (`-improved-2.pptx`, etc.) |

### Example Usage

```bash
# Default: writes to deck-improved.pptx (source untouched)
python outline2ppt.py improve deck.pptx

# Explicit output path
python outline2ppt.py improve deck.pptx --output better-deck.pptx

# Opt into overwriting source (old default behavior)
python outline2ppt.py improve deck.pptx --in-place

# If deck-improved.pptx already exists, writes to deck-improved-2.pptx
python outline2ppt.py improve deck.pptx
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_improve.py` | `test_default_output_suffix` | Verify default output path is `<stem>-improved.pptx` |
| `tests/test_improve.py` | `test_in_place_flag` | Verify `--in-place` overwrites source |
| `tests/test_improve.py` | `test_collision_avoidance` | Verify numeric suffix when output exists |
| `tests/test_improve.py` | `test_explicit_output_path` | Verify `--output` still works as before |

### Manual Testing

1. Run `improve deck.pptx` — expect `deck-improved.pptx` created, `deck.pptx` unchanged
2. Run again — expect `deck-improved-2.pptx` created
3. Run `improve deck.pptx --in-place` — expect `deck.pptx` overwritten
4. Run `improve deck.pptx --output custom.pptx` — expect `custom.pptx` created

---

## Changelog Entry

```markdown
### Changed
- `improve` command no longer overwrites the source deck by default; writes to `<name>-improved.pptx` instead. Use `--in-place` to restore the old behavior.
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add `--in-place` flag and default output path logic to CLI | `cli.py` | -- |
| 2 | Remove in-place fallback in `improve_deck()`, require explicit `output_path` | `improve.py` | -- |
| 3 | Add collision avoidance (numeric suffix when output exists) | `cli.py` | 1 |
| 4 | Update summary output to print final output path | `cli.py` | 1 |
| 5 | Add unit tests | `tests/test_improve.py` | 1, 2, 3 |
| 6 | Update CLAUDE.md CLI examples and changelog | `CLAUDE.md`, `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Question:** Should `--in-place` print a warning like "Overwriting source file"? — Recommend yes, a single-line warning via `logger.warning()`.
- **Question:** Should the suffix be `-improved` or something else (e.g., `-v2`)? — `-improved` matches the existing convention the user already used manually.
- **Risk:** Existing scripts or workflows that rely on in-place overwrite will break — mitigated by the `--in-place` flag providing a simple migration path.
