# PRD: Insight-Driven Title Rewriting

**Date:** 2026-03-09
**Author:** Matt Shamshoian
**Status:** Draft

---

## Summary

Extend the `improve` pipeline to rewrite slide titles alongside body content. The analysis step evaluates whether a title is generic (e.g., "The Problem", "Architecture") and suggests an insight-driven alternative that communicates the slide's key takeaway (e.g., "3 Hours Lost Per Engineer Per Day", "Production-Ready AI Stack"). Original titles are preserved in metadata for rollback. Users can opt out with `--keep-titles`.

## Motivation

- **Problem:** The current improve pipeline rewrites body content but never touches titles. Generic titles are one of the most common presentation weaknesses — they tell the audience what *category* the slide is about, not what *insight* it delivers. slide-creator's prompt writing guidelines demonstrate that insight-driven titles ("Engineers Waste 3 Hours/Day Searching for Answers" vs "The Problem") dramatically improve audience engagement.
- **Who benefits:** Anyone running `aippt improve` on decks with generic or label-style titles.
- **What happens if we don't do this:** Improved body content sits under weak titles, reducing the impact of the improvement.

## Requirements

### Must Have

- [ ] **Title evaluation:** During the `analyze_slide(mode='improvements')` call, the analysis prompt also evaluates the title and suggests whether it should be rewritten
- [ ] **Title rewrite:** When analysis recommends a title change, the rewrite step generates an improved title alongside the body content
- [ ] **Title application:** Apply the improved title to the slide's title placeholder
- [ ] **Original title preservation:** Store the original title in `[AIPPT-META]` for rollback
- [ ] **`--keep-titles` flag:** Opt-out flag to skip title rewriting (body-only improvement, current behavior)

### Nice to Have

- [ ] **Title-only mode:** `--titles-only` flag that improves titles without touching body content (fast pass for title polish)
- [ ] **Title quality heuristics:** Simple pre-check to skip title rewriting for titles that are already insight-driven (saves an LLM call)

### Out of Scope

- Title rewriting during `create --enhance` — the enhance pipeline already writes titles from the outline; this is for post-creation improvement only
- Subtitle generation — only the main title placeholder is modified

---

## Design

### Approach

Modify the analysis and rewrite prompts in `improve.py` to include title evaluation and rewriting. The title rewrite is returned as a separate field in the LLM response, parsed alongside the body content rewrite. Title application uses the existing slide title placeholder.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `aippt/improve.py` | Modified | Add title evaluation to analysis prompt, title field to rewrite prompt/response, title application logic |
| `aippt/cli.py` | Modified | Add `--keep-titles` CLI arg, pass through to `improve_deck()` |

### Modified Analysis Prompt

The `analyze_slide(mode='improvements')` prompt in `analyze.py` is extended with a fifth evaluation dimension:

```
5. Title Quality
- Is the title insight-driven (communicates the key takeaway) or generic (just a category label)?
- If generic, suggest an insight-driven alternative based on the slide content
- Good titles: "3 Hours Lost Per Engineer Per Day", "Production-Ready AI Stack", "290 Chunks, 2-Second Queries"
- Weak titles: "The Problem", "Architecture", "Results", "Overview", "Summary"
```

### Modified Rewrite Prompt

The `build_rewrite_prompt()` function is extended to request a title when the analysis recommends one:

```
Also provide an improved title if the expert feedback suggests the current title is generic.

Format:
TITLE: [improved title, or KEEP if the current title is good]
CONTENT:
- bullet 1
- bullet 2
```

### Response Parsing

`parse_rewritten_content()` is extended to extract the `TITLE:` line before the `CONTENT:` section. If `TITLE: KEEP` or no `TITLE:` line is present, the title is left unchanged.

```python
def parse_rewrite_response(response: str) -> Tuple[Optional[str], str]:
    """Parse LLM rewrite response into (new_title, improved_content).

    Returns (None, content) if title should be kept.
    """
```

### Title Application

After body content is applied, the title placeholder is updated if a new title was provided:

```python
if new_title and slide.shapes.title:
    slide.shapes.title.text = new_title
```

Font formatting (size, bold, color) is preserved by re-applying the title's existing run-level formatting after setting the text.

### Title Quality Heuristics (Nice to Have)

Simple pre-check to detect titles that are likely already insight-driven:

```python
GENERIC_TITLE_PATTERNS = [
    r'^(The )?(Problem|Solution|Architecture|Overview|Summary|Introduction|'
    r'Background|Conclusion|Results|Agenda|Outline|Next Steps|Questions|'
    r'Key (Findings|Takeaways|Points))$'
]

def is_generic_title(title: str) -> bool:
    """Check if a title matches common generic patterns."""
```

When `is_generic_title()` returns False, the title rewrite step is skipped (the analysis still runs, but the rewrite prompt doesn't request a new title). This saves an LLM token overhead for titles that are already specific.

### Data Model Changes

No data model changes.

#### Metadata extension

```json
{
  "operation": "improve",
  "title_rewritten": true,
  "original_title": "The Problem",
  "new_title": "Engineers Waste 3 Hours/Day Searching for Answers"
}
```

New fields: `title_rewritten` (bool), `original_title` (string, only when title was changed), `new_title` (string, only when title was changed).

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `aippt improve` | New option `--keep-titles` | Skip title rewriting; improve body content only |
| `aippt improve` | Behavior change | Now evaluates and rewrites generic titles by default |

### Example Usage

```bash
# Default: improve body + titles (new behavior)
aippt improve deck.pptx --images-dir images/deck/

# Improve body only, keep original titles
aippt improve deck.pptx --keep-titles --images-dir images/deck/

# Dry run shows proposed title changes
aippt improve deck.pptx --dry-run --images-dir images/deck/
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_improve.py` | `TestParseRewriteResponse` | Title extraction from rewrite response, KEEP handling, missing TITLE line |
| `tests/test_improve.py` | `TestIsGenericTitle` | Generic pattern matching, false positives, edge cases |
| `tests/test_improve.py` | `TestTitleApplication` | Title placeholder text update, formatting preservation |
| `tests/test_improve.py` | `TestKeepTitlesFlag` | Verify `--keep-titles` skips title rewriting |

### Manual Testing

1. Run `improve` on a deck with generic titles ("The Problem", "Architecture", "Results") — verify titles are rewritten to insight-driven versions
2. Run `improve` on a deck with already-specific titles — verify titles are left unchanged (or only minor polish)
3. Run with `--keep-titles` — verify body is improved but titles untouched
4. Run `--dry-run` — verify proposed title changes shown in output
5. Check `[AIPPT-META]` in speaker notes — verify `original_title` preserved for rollback

---

## Changelog Entry

```markdown
### Added
- Insight-driven title rewriting in `improve` pipeline: generic titles like "The Problem" are rewritten to convey the slide's key takeaway
- `--keep-titles` flag to skip title rewriting during improvement
- Original titles preserved in slide metadata for rollback
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Extend analysis prompt with title evaluation dimension | `improve.py` | -- |
| 2 | Extend rewrite prompt to request TITLE field | `improve.py` | -- |
| 3 | Implement `parse_rewrite_response()` with title extraction | `improve.py` | 2 |
| 4 | Add title application logic with formatting preservation | `improve.py` | 3 |
| 5 | Implement `is_generic_title()` heuristic (nice to have) | `improve.py` | -- |
| 6 | Add `--keep-titles` CLI arg | `cli.py` | 4 |
| 7 | Record title changes in metadata | `improve.py` | 4 |
| 8 | Add unit tests | `tests/test_improve.py` | 1-5 |
| 9 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** LLM may rewrite titles that were intentionally concise/generic (e.g., section dividers) — mitigated by `--keep-titles` escape hatch and the `TITLE: KEEP` mechanism in the rewrite response
- **Risk:** Title formatting (font size, color, bold) may be lost when setting new text — mitigated by re-applying run-level formatting from the original title
- **Question:** Should title rewriting be integrated into the validation loop (PRD: Iterative Improvement)? Recommend treating them as independent — title rewrite doesn't need multi-pass validation since it's a single transformation.

---

## References

- Inspired by: slide-creator skill's "Slide Titles" section — insight-driven titles that communicate the takeaway, not the category
- Related: `aippt/improve.py` (current body-only rewrite pipeline)
