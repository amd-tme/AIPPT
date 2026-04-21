# Test Results & Future Work

**Date:** 2026-03-02
**Branch:** actually-useful
**Base SHA:** d912fdca7cb85edd2cc75fb0ba71d434e3121606

---

## Test Results Summary

### Unit Tests
- **406 tests pass** (up from 374 at session start)
- 27 deselected (e2e/live markers excluded by default)
- Runtime: ~5s

### New Tests Added This Session

| Test File | Class | Tests | Coverage |
|-----------|-------|-------|----------|
| `tests/test_layouts.py` | `TestApplyBulletsFormatting` | 8 | Font sizing (Pt(22)/Pt(18)), bold lead-ins |
| `tests/test_layouts.py` | `TestNumberedLayout` | 3 | Numbered layout type selection and rendering |
| `tests/test_layouts.py` | `TestTwoColumnWithHeaders` | 2 | Column headers in two-column layouts |
| `tests/test_layouts.py` | `TestPlaceholderImage` | 3 | Gray rectangle placeholder for diagram fallback |
| `tests/test_parser.py` | `TestParseLayoutColumnHeaders` | 4 | Parsing `two_column \| Header1 \| Header2` format |
| `tests/test_improve.py` | `TestBuildRewritePrompt` | 4 | Prompt assembly with title, content, feedback |
| `tests/test_improve.py` | `TestParseRewrittenContent` | 4 | Parsing LLM response into bullet lines |
| `tests/test_improve.py` | `TestExtractSlideContent` | 1 | Extracting title and body from PPTX slide |
| `tests/test_improve.py` | `TestImproveSlide` | 2 | Mocked end-to-end slide improvement |
| `tests/test_improve.py` | `TestImproveDeck` | 1 | Multi-slide filtering and orchestration |

### E2E Pipeline Test (Manual)
- Generated enhanced deck v5 (14 slides) with `create --enhance`
- Layout distribution: 1 basic, 10 two_column, 3 numbered
- Verified: font sizes (Pt(22)/Pt(18)), bold lead-ins, column headers
- Ran `improve --dry-run --slides 1,2` — LLM analysis + rewrite worked
- Ran `improve --slides 1,2 --output improved.pptx` — content applied correctly
- Speaker notes contain revision history

---

## Implemented Features (This Session)

### Phase 1: Enhanced Initial Generation
1. **Font sizing** — Pt(22) for level 0/1, Pt(18) for level 2 sub-bullets
2. **Bold lead-ins** — "Keyword: rest" pattern detected and split into bold + normal runs
3. **Numbered layout** — `numbered` layout type for sequential/step content
4. **Column headers** — Two-column layouts get LLM-generated bold header paragraphs
5. **Placeholder images** — Gray rectangle with description text for diagram fallback

### Phase 2: Improve Command
6. **`outline2ppt/improve.py`** — Full pipeline: extract → analyze → rewrite → apply
7. **CLI `improve` subcommand** — `--dry-run`, `--slides`, `--passes`, `--output`
8. **Speaker notes revision history** — Original + improved content appended to notes
9. **Graceful degradation** — Individual slide failures don't abort the batch
10. **Model default** — Uses `enhance` model default from models.yaml

---

## Known Limitations & Future Work

### High Priority

- **Two-column improve**: `improve_slide` only rewrites the first body placeholder
  (`idx > 0`). Two-column slides have two body placeholders (idx 12 and 13). The
  second column retains its original content after improvement. Fix: detect
  two-column layout and improve both placeholders, or merge both columns into
  a single content block for the LLM and re-split on return.

- **Numbered content from LLM**: The LLM sometimes omits `1.`, `2.` prefixes even
  when `numbered` layout is selected. The code correctly handles numbered items
  when present, but the LLM needs stronger prompt guidance to consistently
  produce them. Consider adding few-shot examples to the enhance prompt.

### Medium Priority

- **Image re-export after improvement**: The improve pipeline doesn't re-export
  slide images after applying changes. Multi-pass improvement (`--passes 2`)
  analyzes the original images on subsequent passes. Requires PowerPoint on
  Windows for image export (via COM automation) or LibreOffice fallback on Linux.

- **`improve` model in models.yaml**: Currently falls back to `enhance` model
  default. Could add dedicated `improve` operation to models.yaml with a
  potentially cheaper/faster model for the rewrite step (analysis still uses
  vision model).

- **Improve summary granularity**: The applied/skipped counts don't distinguish
  between "no content to improve" and "placeholder not found". Could add
  `no_content` and `failed` categories to the result summary.

- **Enhance prompt variety**: The LLM heavily favors `two_column` layout (10/14
  slides in v5 test). Could adjust prompt weighting or add stronger variety
  guidance. Consider tracking layout distribution and nudging the LLM toward
  underused types.

### Low Priority / Nice to Have

- **Auto font scaling**: Fewer than 3 bullets could trigger larger font size
- **Subtitle support**: Basic layout title slides could include a tagline
- **`--no-reexport` flag**: Skip image re-export for faster single-pass runs
- **Split recommendation logging**: When analysis suggests splitting a slide,
  log it as a recommendation rather than silently ignoring
- **Improve specific content types**: Could add `--focus` flag (e.g., `--focus accuracy`
  or `--focus detail`) to steer the rewrite toward specific improvement goals

### Testing Gaps

- `TestExtractSlideContent` uses a textbox, not a real body placeholder.
  A test with a proper slide layout (e.g., `slide_layouts[1]`) setting
  `para.level` values would better cover the level-to-prefix mapping.

- No test for `improve_slide` with `dry_run=False` (the apply path). Would need
  a slide with a real body placeholder to verify `tf.clear()` and
  `_apply_bullets_to_text_frame()` are called correctly.

- No test for multi-pass behavior (`passes > 1`).

- No test for two-column improve behavior (verifying second column is preserved
  or handled).

---

## Bugs Fixed This Session

1. **Bullet slides empty body**: `apply_basic_layout` searched for `type == 2`
   (BODY) but AMD template uses type 7 (OBJECT). Fixed: match by `idx > 0`.

2. **Two-column all-in-left**: `split_content_for_columns` counted trailing
   empty lines, skewing the midpoint. Fixed: strip empty lines before split.

3. **`ingest` CLI misroute**: `ingest` and `tags` were missing from the
   subcommands set in `outline2ppt.py`. Fixed: added both.

4. **Level 2 sub-bullet detection**: `line.strip()` before level check caused
   sub-bullets to match as level 1. Fixed: check `line.startswith('  ')` on
   original line before stripping.

5. **Level 0 prefix in extract_slide_content**: Level 0 paragraphs got no
   dash prefix, making extracted content look like plain text. Fixed: level 0
   always gets `"- "` prefix.

6. **Image filename convention**: `improve_deck` looked for `slide_1.png` but
   export produces `Slide1.PNG`. Fixed: match `Slide{i}` pattern.
