# PRD: Reverse Round-Trip Fix

**Date:** 2026-03-02
**Author:** Matt
**Status:** Draft

---

## Summary

The `reverse` command converts PPTX slides to markdown, but speaker notes are emitted as regular bullet content under `*Notes:*` headers. When the reversed markdown is fed back into `create`, these notes appear as slide body text — breaking round-trip fidelity. This PRD fixes the reverse output format and hardens the create parser to ignore note blocks.

## Motivation

- **What problem does this solve?** A reversed markdown file cannot be used as input to `create` without manual editing. Notes content pollutes the slide body, and analysis artifacts (e.g., `[Note: analysis based on slide text only]`) get embedded in production slides.
- **Who benefits?** Any user who reverse-engineers a deck to edit and regenerate it.
- **What happens if we don't do this?** The reverse → edit → create workflow is effectively broken for decks that have speaker notes.

## Requirements

### Must Have

- [ ] Reversed markdown places speaker notes in a format that `parse_outline()` ignores (not as bullet content)
- [ ] Round-trip test: `create` → `reverse` → `create` produces slides with body content only (no notes leakage)
- [ ] Analysis artifacts (`[Note: analysis based on slide text only — no image was available]`) stripped from reversed notes

### Nice to Have

- [ ] Reversed notes use a fenced block or HTML comment so they survive markdown editing but are excluded from `create`
- [ ] CLI flag `--strip-notes` on `reverse` to omit notes entirely

### Out of Scope

- Preserving notes through `create` (notes are generated fresh by `--enhance` or `analyze --mode notes`)
- Two-column layout preservation in reverse output

---

## Design

### Approach

Two complementary changes:

1. **`ppt2outline.py` (reverse output)**: Change notes formatting from `*Notes:*` bullet list to a fenced section that `parse_outline()` will skip. Recommended format:

   ```markdown
   <!-- notes
   Speaker notes text here...
   -->
   ```

   HTML comments are invisible to most markdown renderers and naturally excluded from outline parsing. Alternative: use a `> [!NOTE]` callout block, but this requires parser changes.

2. **`parser.py` (parse_outline)**: Add a guard to strip any `*Notes:*` sections and HTML comment blocks before parsing. This handles both old-format and new-format reversed files.

3. **Strip analysis artifacts**: In `ppt2outline.py`, filter out lines matching `[Note: analysis based on slide text only` before emitting notes.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/ppt2outline.py` | Modified | Change notes output format from bullet list to HTML comment block; strip analysis artifacts |
| `outline2ppt/parser.py` | Modified | Add pre-processing step to `parse_outline()` that removes HTML comment blocks and legacy `*Notes:*` sections |

### Data Model Changes

No data model changes.

---

## CLI Changes

### New Commands

None.

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `reverse` | New option `--strip-notes` | Omit speaker notes entirely from reversed markdown (nice-to-have) |

### Example Usage

```bash
# Standard reverse (notes in HTML comments)
python outline2ppt.py reverse deck.pptx output.md

# Strip notes entirely
python outline2ppt.py reverse deck.pptx output.md --strip-notes

# Round-trip
python outline2ppt.py reverse deck.pptx outline.md
python outline2ppt.py create outline.md template.pptx roundtrip.pptx
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_ppt2outline.py` | `TestNotesFormat` | Notes output as HTML comments, analysis artifact stripping |
| `tests/test_parser.py` | `TestParseOutlineNotesStripping` | HTML comment removal, legacy `*Notes:*` removal |

### Integration Tests

Add a round-trip test to `tests/test_integration.py`:
- Create a deck with `--enhance` (mocked LLM), reverse it, create from reversed markdown, verify no notes in slide body.

### Manual Testing

1. `reverse` a deck with speaker notes → verify notes appear as `<!-- notes ... -->` in markdown
2. Feed reversed markdown into `create` → verify slide body has no notes content
3. Reverse a deck that was processed by `analyze --mode notes` → verify `[Note: analysis based on slide text only]` is not present

---

## Changelog Entry

```markdown
### Fixed
- Reverse round-trip: speaker notes no longer leak into slide body when reversed markdown is used with `create`
- Analysis artifacts stripped from reversed speaker notes
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Change notes output format in reverse to HTML comments | `outline2ppt/ppt2outline.py` | -- |
| 2 | Strip analysis artifacts from notes during reverse | `outline2ppt/ppt2outline.py` | 1 |
| 3 | Add HTML comment and `*Notes:*` stripping to `parse_outline()` | `outline2ppt/parser.py` | -- |
| 4 | Add `--strip-notes` flag to reverse CLI | `outline2ppt/cli.py`, `outline2ppt/ppt2outline.py` | 1 |
| 5 | Add unit tests for notes format and stripping | `tests/test_ppt2outline.py`, `tests/test_parser.py` | 1, 2, 3 |
| 6 | Add round-trip integration test | `tests/test_integration.py` | 1, 2, 3 |
| 7 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Question:** HTML comments vs `> [!NOTE]` callout — HTML comments are simpler (no parser changes needed for most cases) but invisible in rendered markdown. Callouts are visible but require explicit parser handling. **Recommendation:** HTML comments.
- **Risk:** Existing users may have scripts that parse the `*Notes:*` format — mitigation: the parser handles both old and new formats.

---

## References

- Related PRDs: `docs/plans/2026-02-27-enhanced-reverse.md`
- Test results: `docs/plans/2026-03-02-test-results-and-future-work.md`
