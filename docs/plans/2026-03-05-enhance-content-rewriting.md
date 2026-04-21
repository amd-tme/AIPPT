# PRD: Content Enhancement in --enhance Mode

**Date:** 2026-03-05
**Author:** Matt
**Status:** Draft

---

## Summary

The `--enhance` pipeline currently generates speaker notes metadata (NARRATIVE, LAYOUT, VISUALS, TALKING_POINTS) but never rewrites the slide body text. The original author bullets appear verbatim on every slide regardless of enhancement. This PRD adds a `CONTENT:` section to the LLM enhancer output so that `--enhance` produces polished, fleshed-out bullet content that replaces the original on the slide body.

## Motivation

- **What problem does this solve?** Authors write terse outline bullets as a skeleton. `--enhance` should flesh them out into presentation-ready text — adding detail, improving wording, and filling gaps — without requiring the author to manually rewrite every slide.
- **Who benefits?** End users creating decks from outlines. The current `--enhance` flag is underwhelming because the slide body is identical to the non-enhanced version.
- **What happens if we don't do this?** `--enhance` remains cosmetic — it only affects speaker notes, not the visible slide content.

## Requirements

### Must Have

- [ ] LLM enhancer produces a `CONTENT:` section with expanded/polished bullet text
- [ ] Enhanced content replaces original bullets on the slide body
- [ ] Original bullet count and order are preserved (expand, don't restructure)
- [ ] Author `LAYOUT:` directives still override LLM layout suggestions
- [ ] `IMAGE:` directive behavior unchanged (image slides move text to notes, but enhanced text goes to notes instead of original)
- [ ] Graceful fallback: if `CONTENT:` parsing fails, use original content
- [ ] `parse_llm_suggestions()` updated to extract the new `CONTENT:` field
- [ ] Existing tests updated; new tests for content extraction and fallback

### Nice to Have

- [ ] `--enhance` with `--verbose` logs a diff between original and enhanced content

### Out of Scope

- Rewriting speaker notes content (NARRATIVE/VISUALS/TALKING_POINTS remain as-is)
- Changing the number of LLM calls per slide (still one call)
- Adding a separate `--rewrite` flag (enhancement is all-or-nothing)

---

## Design

### Approach

Add a `CONTENT:` block to the enhancer prompt and response format. The LLM receives the original bullets and returns polished versions in the same structure. In `_add_slide()`, parse the `CONTENT:` section from the enhanced response and use it as the slide body instead of always falling back to `original_content`.

### Data Flow (Current)

```
outline bullets → enhance_with_llm() → NARRATIVE/LAYOUT/VISUALS/TALKING_POINTS
                                         ↓
_add_slide(content=enhanced, original_content=original)
    → slide body uses original_content (line 385-386 of cli.py)
    → speaker notes use parsed suggestions
```

### Data Flow (Proposed)

```
outline bullets → enhance_with_llm() → CONTENT/NARRATIVE/LAYOUT/VISUALS/TALKING_POINTS
                                         ↓
_add_slide(content=enhanced, original_content=original)
    → parse CONTENT: from enhanced response
    → slide body uses CONTENT: (falls back to original_content if missing)
    → speaker notes use parsed suggestions (unchanged)
```

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `aippt/enhancer.py` | Modified | Add `CONTENT:` to prompt template and response format |
| `aippt/parser.py` | Modified | Update `parse_llm_suggestions()` to extract `CONTENT:` field |
| `aippt/cli.py` | Modified | Use parsed `CONTENT:` for slide body instead of `original_content` |

### Key Changes

**`enhancer.py`** — Update the prompt to request a `CONTENT:` block:

```
CONTENT:
- Enhanced bullet 1
- Enhanced bullet 2
- Enhanced bullet 3
NARRATIVE: [2-3 sentences]
LAYOUT: [keyword]
VISUALS: [delivery tips]
TALKING_POINTS: [additional points]
```

The prompt must instruct the LLM to:
- Preserve the number of top-level bullets from the original
- Preserve the order and intent of each bullet
- Expand terse phrases into complete, presentation-ready text
- Keep sub-bullets if present in the original
- Not add markdown formatting beyond bullet markers

**`parser.py`** — `parse_llm_suggestions()` currently extracts NARRATIVE, LAYOUT, VISUALS, TALKING_POINTS by splitting on known headers. Add `CONTENT` to the set of recognized headers. The extracted value is multi-line (the bullet list).

**`cli.py`** — In `_add_slide()`, replace lines 383-388:

```python
# Current: always use original_content
if original_content:
    slide_content = '\n'.join(original_content) ...

# Proposed: prefer CONTENT: from suggestions, fall back to original
enhanced_content = suggestions.get('CONTENT', '').strip()
if enhanced_content:
    slide_content = enhanced_content
elif original_content:
    slide_content = '\n'.join(original_content) ...
```

### Data Model Changes

No data model changes.

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `aippt create --enhance` | Behavior change | Slide body text is now enhanced by the LLM instead of using original verbatim |

No new flags or arguments required.

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_enhancer.py` | `test_content_section_in_prompt`, `test_content_parsing` | Verify CONTENT: appears in prompt and is parsed from response |
| `tests/test_parser.py` | `test_parse_llm_suggestions_with_content` | Verify parse_llm_suggestions extracts CONTENT field |
| `tests/test_cli.py` | `test_add_slide_uses_enhanced_content`, `test_add_slide_fallback_to_original` | Verify slide body uses CONTENT when available, falls back to original |

### Manual Testing

1. Run `aippt create outline.md template.pptx out-plain.pptx` — verify original bullets on slides
2. Run `aippt create outline.md template.pptx out-enhanced.pptx --enhance` — verify slide body text is expanded/polished compared to plain version
3. Verify speaker notes still contain NARRATIVE/VISUALS/TALKING_POINTS
4. Test with directive slides (LAYOUT:, IMAGE:) — verify directives still honored, enhanced content used appropriately
5. Compare plain vs enhanced output side-by-side for content quality

---

## Changelog Entry

```markdown
### Changed
- `--enhance` mode now rewrites slide body text with expanded, polished content instead of using original bullets verbatim
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add CONTENT: to enhancer prompt and response format | `aippt/enhancer.py` | -- |
| 2 | Update parse_llm_suggestions() to extract CONTENT field | `aippt/parser.py` | -- |
| 3 | Use parsed CONTENT for slide body in _add_slide() | `aippt/cli.py` | 1, 2 |
| 4 | Add unit tests for content extraction and fallback | `tests/test_enhancer.py`, `tests/test_parser.py`, `tests/test_cli.py` | 1, 2, 3 |
| 5 | Manual validation with meme-directives-test.md | -- | 3 |
| 6 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** LLM returns wrong number of bullets, breaking two_column midpoint splits — Mitigation: prompt explicitly instructs "preserve the number and order of original bullets"; fallback to original if count mismatch detected
- **Risk:** CONTENT: block parsing conflicts with bullet markers in other sections — Mitigation: CONTENT: is first in the response format, terminated by NARRATIVE: header
- **Question:** Should we validate bullet count matches between original and enhanced? Conservative approach: log a warning but use enhanced content anyway, since the LLM generally follows instructions well

---

## References

- Related PRDs: `docs/plans/2026-03-05-image-text-co-display.md`
- Current enhancer: `aippt/enhancer.py`
- Current parser: `aippt/parser.py` (`parse_llm_suggestions()`)
- Current slide builder: `aippt/cli.py` (`_add_slide()`)
