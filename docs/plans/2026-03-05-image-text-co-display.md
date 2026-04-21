# PRD: Image + Text Co-display on Slides

**Date:** 2026-03-05
**Author:** Matt
**Status:** Draft

---

## Summary

Currently, the `IMAGE:` directive takes the full content area and moves all bullet text to speaker notes. This PRD changes `IMAGE:` behavior so that when used without `LAYOUT: diagram`, the slide displays both the image and the text side-by-side using the template's built-in "Screenshot and caption" layout. Authors who want full-image slides can still use `LAYOUT: diagram` with `IMAGE:`.

## Motivation

- **What problem does this solve?** Authors embed images to support their content, not replace it. The current all-or-nothing behavior forces a choice: show the image or show the text. Most presentations benefit from both visible on the same slide.
- **Who benefits?** End users creating decks with embedded images — diagrams alongside explanatory bullets, screenshots with captions, etc.
- **What happens if we don't do this?** Authors must choose between image-only slides (text hidden in notes) or text-only slides (no image). Neither is ideal for most use cases.

## Requirements

### Must Have

- [ ] `IMAGE:` without `LAYOUT:` uses template picture+text layout (text and image both visible)
- [ ] `IMAGE:` + `LAYOUT: diagram` retains current behavior (full-image, text to notes)
- [ ] `IMAGE:` + `LAYOUT: bullet` or `LAYOUT: numbered` uses picture+text layout
- [ ] `IMAGE:` + `LAYOUT: two_column` retains current behavior (full-image, text to notes — no picture placeholder available)
- [ ] New layout function `_apply_image_with_text()` populates both picture and text placeholders
- [ ] Fallback: if template lacks the picture+text layout, fall back to current full-image behavior
- [ ] Update example outline `examples/outline-with-directives.md` to reflect new behavior
- [ ] Existing tests updated; new tests for co-display rendering

### Nice to Have

- [ ] Support both "Screenshot and caption" (layout 21, image left) and "Product/Feature" (layout 11, image left) with an optional `IMAGE_POSITION:` directive for author control

### Out of Scope

- Adding new template layouts to corp.pptx
- Supporting arbitrary image sizes or aspect ratio control
- Image cropping or scaling beyond what python-pptx provides natively

---

## Design

### Approach

Change the decision logic in `apply_layout_content()` so that `IMAGE:` no longer unconditionally calls `_apply_author_image()`. Instead, check the layout type: if `diagram` or `two_column`, use full-image behavior; otherwise, use the template's "Screenshot and caption" layout to show both image and text.

### Behavior Matrix

| IMAGE: | LAYOUT: | Result | Template Layout Used |
|--------|---------|--------|---------------------|
| set | (none) | **NEW:** Image + text side-by-side | Screenshot and caption (21) |
| set | diagram | Full-image, text to notes (unchanged) | Title Only (7) |
| set | bullet | **NEW:** Image + text side-by-side | Screenshot and caption (21) |
| set | numbered | **NEW:** Image + text side-by-side | Screenshot and caption (21) |
| set | basic | **NEW:** Image + text side-by-side | Screenshot and caption (21) |
| set | two_column | Full-image, text to notes (unchanged) | Two Content (5) |
| not set | any | Normal layout rendering (unchanged) | varies |

### Template Layout: "Screenshot and caption" (index 21)

```
┌───────────────────────────────────────┐
│ [Title]                    idx=0      │
├─────────────────────────┬─────────────┤
│                         │             │
│   [PICTURE]             │   [TEXT]    │
│   idx=12                │   idx=13   │
│   7.9 x 5.3 in         │   3.8x4.6  │
│                         │             │
└─────────────────────────┴─────────────┘
```

- Picture placeholder: idx=12, PICTURE type (18), 7.9x5.3in at (0.6, 1.6)
- Text placeholder: idx=13, BODY type (2), 3.8x4.6in at (8.9, 2.2)
- Title: idx=0, standard position

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `aippt/layouts.py` | Modified | Add `_apply_image_with_text()`, update `apply_layout_content()` decision logic |
| `aippt/cli.py` | Modified | Update `_add_slide()` to select "Screenshot and caption" layout when image+text co-display is needed |
| `aippt/parser.py` | No change | Directive extraction unchanged |
| `examples/outline-with-directives.md` | Modified | Update examples to show new behavior |

### Key Changes

**`layouts.py`** — New function:

```python
def _apply_image_with_text(slide, image_path: str, content: str):
    """Insert image into picture placeholder and text into body placeholder.

    Used with template layouts that have both a PICTURE and BODY placeholder
    (e.g., 'Screenshot and caption').
    """
    # Find picture placeholder (type 18) and body placeholder
    pic_ph = None
    text_ph = None
    for shape in slide.placeholders:
        idx = shape.placeholder_format.idx
        if idx == 0:  # skip title
            continue
        if shape.placeholder_format.type == 18:  # PICTURE
            pic_ph = shape
        elif text_ph is None:
            text_ph = shape

    if pic_ph:
        pic_ph.insert_picture(open(image_path, 'rb'))
    else:
        # Fallback: add picture as shape
        slide.shapes.add_picture(image_path, Inches(0.6), Inches(1.6), Inches(7.9), Inches(5.3))

    if text_ph and content.strip():
        _apply_bullets_to_text_frame(text_ph.text_frame, content)
```

**`layouts.py`** — Update `apply_layout_content()`:

```python
def apply_layout_content(..., image_path=None):
    if image_path:
        # Full-image behavior only for diagram and two_column
        if layout_type in ('diagram', 'two_column'):
            _apply_author_image(slide, image_path, content)
        else:
            _apply_image_with_text(slide, image_path, content)
        return
    # ... rest unchanged
```

**`cli.py`** — Update `_add_slide()` layout selection:

When `image_path` is set and `layout_type` is not `diagram` or `two_column`, select the "Screenshot and caption" slide layout instead of the normal layout:

```python
# Before selecting layout, check if we need image+text co-display
if image_path and layout_info['type'] not in ('diagram', 'two_column'):
    slide_layout = select_slide_layout(prs, 'image_text')  # new mapping
else:
    slide_layout = select_slide_layout(prs, layout_info['type'])
```

Add `'image_text': 'Screenshot and caption'` to the `layout_map` in `select_slide_layout()`.

### Data Model Changes

No data model changes.

---

## CLI Changes

No new CLI commands or flags. This is a behavior change in how existing `IMAGE:` directives are rendered.

### Breaking Change

`IMAGE:` without `LAYOUT:` previously rendered as full-image with text in notes. It will now render as image+text side-by-side. Authors who want the old full-image behavior should add `LAYOUT: diagram`.

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_layouts.py` | `test_apply_image_with_text`, `test_image_with_text_fallback` | New co-display function and fallback behavior |
| `tests/test_layouts.py` | `test_apply_layout_content_image_diagram_unchanged` | Verify diagram+image retains full-image behavior |
| `tests/test_layouts.py` | `test_apply_layout_content_image_no_layout_co_display` | Verify image without layout uses co-display |
| `tests/test_cli.py` | `test_add_slide_selects_screenshot_layout` | Verify correct template layout selected for image+text |

### Manual Testing

1. Run meme-directives-test.md — verify slides with `IMAGE:` only (slides 5, 7, 10) now show image+text side-by-side
2. Verify slides with `IMAGE:` + `LAYOUT: diagram` (slides 2, 9) still show full-image
3. Verify slides with no `IMAGE:` render normally
4. Test with a template that lacks "Screenshot and caption" layout — verify graceful fallback to full-image
5. Check text formatting in the narrow text placeholder (3.8in wide) — verify bullets render cleanly at smaller width

---

## Changelog Entry

```markdown
### Changed
- `IMAGE:` directive without `LAYOUT: diagram` now displays both image and text side-by-side using the template's picture+text layout, instead of hiding text in speaker notes
- `IMAGE:` + `LAYOUT: diagram` retains the previous full-image behavior
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add `image_text` to layout_map in select_slide_layout() | `aippt/layouts.py` | -- |
| 2 | Implement `_apply_image_with_text()` function | `aippt/layouts.py` | -- |
| 3 | Update `apply_layout_content()` decision logic | `aippt/layouts.py` | 2 |
| 4 | Update `_add_slide()` to select correct layout for image+text | `aippt/cli.py` | 1 |
| 5 | Add unit tests for co-display rendering | `tests/test_layouts.py`, `tests/test_cli.py` | 1, 2, 3, 4 |
| 6 | Update example outlines and directive docs | `examples/outline-with-directives.md` | 3, 4 |
| 7 | Manual validation with meme-directives-test.md | -- | 4 |
| 8 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** "Screenshot and caption" layout has a narrow text area (3.8in) — slides with many bullets may overflow — Mitigation: `_apply_bullets_to_text_frame` already handles font sizing based on bullet count; may need to reduce font size further for narrow placeholders
- **Risk:** Template portability — other templates may not have a "Screenshot and caption" layout — Mitigation: fallback to current full-image behavior when layout not found; document template requirements
- **Question:** Should we support "Product/Feature" (layout 11) as an alternative image-left layout? Deferring to Nice to Have — start with one layout and expand if needed
- **Breaking change:** `IMAGE:` without `LAYOUT:` changes behavior. The example outline and directive docs must be updated. Existing user outlines with `IMAGE:` alone will render differently.

---

## References

- Related PRDs: `docs/plans/2026-03-05-enhance-content-rewriting.md`
- Template inspection: corp.pptx layout 21 ("Screenshot and caption")
- Current image handling: `aippt/layouts.py` (`_apply_author_image()`)
- Directive parsing: `aippt/parser.py` (`_extract_directives()`)
