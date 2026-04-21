# PRD: Layout Variety & Numbered Layout Rendering

**Date:** 2026-03-02
**Author:** Matt
**Status:** Draft

---

## Summary

The enhanced generate pipeline (`create --enhance`) selects layout types per slide, but two issues reduce layout effectiveness: (1) the `numbered` layout type renders identically to `bullet` on the slide body because original outline content lacks numbered prefixes, and (2) the LLM prompt update that capped `two_column` at ~40% has overcorrected — zero two_column layouts were selected across 14 slides, down from 5-10 in prior versions. This PRD fixes numbered rendering and rebalances the prompt for better layout variety.

## Motivation

- **What problem does this solve?** Layout types should produce visibly distinct slides. Currently `numbered` and `bullet` look identical, wasting a layout choice. Meanwhile, two_column layouts have disappeared entirely, reducing visual variety.
- **Who benefits?** End users generating enhanced decks — they expect varied, purposeful layouts.
- **What happens if we don't do this?** All slides look like bullet lists regardless of LLM suggestion, and the layout variety feature is cosmetically broken.

## Requirements

### Must Have

- [ ] `numbered` layout renders with `1.`, `2.`, `3.` prefixes on slide body content
- [ ] Prompt tuning restores two_column usage to ~15-30% of slides (when content warrants it)
- [ ] A 14-slide test deck produces at least 3 distinct layout types

### Nice to Have

- [ ] `apply_bullet_layout()` differentiates numbered vs bullet formatting (e.g., bold number prefix, different indent)
- [ ] Layout distribution summary logged after enhance completes (e.g., "Layout mix: 8 bullet, 3 numbered, 3 two_column")

### Out of Scope

- Adding new layout types beyond the existing set
- Changing the PPTX slide layout mapping (numbered and bullet both use "Title and Content" — this is correct)
- Diagram layout improvements (requires image generation pipeline work)

---

## Design

### Approach

**1. Numbered layout rendering**

In `apply_bullet_layout()` (`layouts.py`), when `layout_type == 'numbered'`, prepend sequential numbers to top-level bullet items. The function already receives `layout_type` via `apply_layout_content()` — it just doesn't use it.

Implementation:
- Split content into lines
- For each top-level line (not indented), prepend `{n}. ` if it doesn't already start with a number
- Pass modified content to existing bullet rendering logic

This approach preserves the original content in the outline/notes while adding visual numbering on the slide.

**2. Prompt rebalancing**

The current prompt in `enhancer.py` SYSTEM_PROMPT says:
- "Use two_column for no more than ~40% of slides"
- "Prefer bullet for general content"

This is too restrictive. Rebalance to:
- Remove the 40% cap language
- Add positive guidance: "Use two_column when content has natural pairs, contrasts, or parallel structure — expect 2-4 two_column slides in a typical 10-15 slide deck"
- Add an example in the user prompt showing when two_column is appropriate

**3. Layout summary logging**

After all slides are enhanced, log a one-line summary of the layout distribution.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/layouts.py` | Modified | `apply_bullet_layout()` gains `layout_type` parameter; numbers top-level items when `layout_type == 'numbered'` |
| `outline2ppt/enhancer.py` | Modified | Rebalance SYSTEM_PROMPT for two_column guidance; add layout summary logging |

### Data Model Changes

No data model changes.

---

## CLI Changes

No CLI changes.

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_layouts.py` | `TestNumberedLayout` | Verify numbered prefixes applied to top-level items; sub-items not numbered; pre-numbered items not double-numbered |
| `tests/test_enhancer.py` | `TestPromptContent` | Verify updated prompt contains two_column guidance |

### Integration Tests

None required — prompt changes validated by e2e testing.

### Manual Testing

1. Run `create --enhance --test 5` on a test outline → verify at least one slide has visible numbered prefixes
2. Run `create --enhance` on the full 14-slide outline → verify at least 2 layout types appear, ideally 3
3. Inspect two_column slides (if generated) → verify content is split meaningfully

---

## Changelog Entry

```markdown
### Fixed
- Numbered layout now renders with sequential number prefixes on slide body content
- Rebalanced enhance prompt to restore two_column layout variety
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add `layout_type` parameter to `apply_bullet_layout()` and apply numbered prefixes | `outline2ppt/layouts.py` | -- |
| 2 | Update `apply_layout_content()` to pass `layout_type` through to `apply_bullet_layout()` | `outline2ppt/layouts.py` | 1 |
| 3 | Rebalance SYSTEM_PROMPT two_column and numbered guidance | `outline2ppt/enhancer.py` | -- |
| 4 | Add layout distribution summary logging after enhance | `outline2ppt/enhancer.py` or `outline2ppt/cli.py` | -- |
| 5 | Add unit tests for numbered rendering | `tests/test_layouts.py` | 1, 2 |
| 6 | Update existing prompt tests if assertions changed | `tests/test_enhancer.py` | 3 |
| 7 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Question:** Should numbered items also get bold number styling (e.g., **1.** Item text)? This adds visual distinction but increases complexity. **Recommendation:** Start with plain `1. ` prefix; bold styling can be a follow-up.
- **Risk:** Prompt rebalancing may overcorrect in the other direction (too many two_column). Mitigation: test with 2-3 different outlines and tune iteratively.
- **Question:** Should `apply_bullet_layout()` always receive `layout_type`, or should we create a separate `apply_numbered_layout()` function? **Recommendation:** Pass `layout_type` as parameter — the rendering logic is 90% shared, a separate function would duplicate code.

---

## References

- Related PRDs: `docs/plans/2026-03-02-prd-enhanced-generation.md`
- Prompt guidance: `outline2ppt/enhancer.py` SYSTEM_PROMPT
- Layout rendering: `outline2ppt/layouts.py` apply_bullet_layout()
