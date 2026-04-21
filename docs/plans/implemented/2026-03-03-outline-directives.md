# PRD: Outline Directives (LAYOUT and IMAGE)

**Date:** 2026-03-03
**Author:** Matt
**Status:** Draft

---

## Summary

Extend the markdown outline format to support two new directives: `LAYOUT:` and `IMAGE:`. Authors can specify a known layout type and/or an image file for any slide directly in the outline, giving explicit control over slide structure and visuals without relying on LLM enhancement or image generation.

## Motivation

- **Problem:** In non-enhanced mode, every slide gets the `basic` layout. In enhanced mode, the LLM picks the layout but may not match the author's intent. There is no way to include pre-existing images (screenshots, pre-generated graphics) in a deck without LLM image generation.
- **Who benefits:** Authors who want quick, predictable control over slide appearance. Anyone with a few screenshots or diagrams ready to include alongside their outline.
- **Without this:** Authors must either accept basic layouts everywhere, rely on `--enhance` for layout variety, or manually edit the generated PPTX to add images and fix layouts.

## Requirements

### Must Have

- [ ] `LAYOUT: <type>` directive recognized in slide content, setting the layout for that slide
- [ ] `IMAGE: <path>` directive recognized in slide content, embedding an image file on the slide
- [ ] Directives stripped from slide content before rendering (not visible on the slide itself)
- [ ] Image paths resolved relative to the outline file's directory
- [ ] Graceful degradation: missing images log a warning and skip insertion; invalid layout types log a warning and fall back to `basic`
- [ ] Author-specified LAYOUT overrides LLM suggestion when `--enhance` is used
- [ ] Works in both legacy (H1-only) and hierarchical (H1 sections + H2 slides) outline modes
- [ ] Updated example outline demonstrating all directive combinations

### Nice to Have

- [ ] `IMAGE:` supports a positioning hint (e.g., `IMAGE: path.png | left` for two_column placement)
- [ ] Validation warning when IMAGE is used with a layout that has no natural image placement

### Out of Scope

- Multiple images per slide
- Image resizing/cropping directives
- New layout types beyond the existing set (`bullet`, `two_column`, `numbered`, `basic`, `diagram`)
- Changes to the `--enhance` LLM prompt or system prompt
- Changes to the `improve` pipeline
- Web UI changes (upload-based image handling is a separate concern)

---

## Design

### Approach

Add directive extraction to `parse_outline()` in `parser.py`. When the parser encounters lines matching `LAYOUT: <value>` or `IMAGE: <value>` within a slide's content, it stores them as metadata on the slide dict and excludes them from the content list. Downstream, `_add_slide()` in `cli.py` checks for these metadata keys before falling back to LLM suggestions or defaults.

This approach is consistent with the existing architecture: the parser handles syntax, `cli.py` orchestrates the pipeline, and `layouts.py` handles rendering.

### Directive Syntax

```
LAYOUT: <type>
IMAGE: <path>
```

Rules:
- Case-sensitive: `LAYOUT:` and `IMAGE:` (uppercase, matching the existing LLM output convention for `NARRATIVE:`, `LAYOUT:`, etc.)
- Must appear in the slide's content block (after the slide header line)
- Can appear in any order, but conventionally placed before bullet content
- One of each per slide (first occurrence wins if duplicated)
- `<type>` must be one of: `bullet`, `two_column`, `numbered`, `basic`, `diagram`
- `<path>` is relative to the outline file's directory

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/parser.py` | Modified | Extract `LAYOUT:` and `IMAGE:` directives from slide content during parsing; add `resolve_image_path()` helper |
| `outline2ppt/cli.py` | Modified | `_add_slide()` honors `slide['layout']` override and `slide['image']` for image insertion; `cmd_create()` resolves image paths after parsing |
| `outline2ppt/layouts.py` | Modified | `apply_layout_content()` gains `image_path` parameter for author-provided images |
| `examples/outline-with-directives.md` | New | Example outline demonstrating LAYOUT and IMAGE usage |

### Data Model Changes

No data model changes.

---

## How Directives Flow Through the Pipeline

### Non-enhanced mode (no `--enhance`)

```
outline.md
  → parse_outline()
    → slide dict: {title, content, section, layout?, image?}
  → resolve_image_path() for each slide with image
  → _add_slide()
    → layout from slide['layout'] or default 'basic'
    → if slide['image']: insert image via add_picture()
    → apply_layout_content() with remaining text content
```

### Enhanced mode (`--enhance`)

```
outline.md
  → parse_outline()
    → slide dict: {title, content, section, layout?, image?}
  → resolve_image_path() for each slide with image
  → enhance_with_llm() for each slide
    → LLM sees content (directives already stripped)
    → LLM returns NARRATIVE/LAYOUT/VISUALS/TALKING_POINTS
  → _add_slide()
    → layout from slide['layout'] (author wins) OR parse LLM's LAYOUT
    → if slide['image']: insert image via add_picture()
    → apply_layout_content() with original content
```

### Image Placement by Layout Type

| Layout | Image Placement | Text Content |
|--------|----------------|--------------|
| `diagram` | Full content area (Inches(1), Inches(1.5), 8w × 4h) | Key points below image |
| `bullet` / `basic` / `numbered` | Full content area (same as diagram) | Moved to speaker notes |
| `two_column` | Full content area (same as diagram) | Moved to speaker notes |

When IMAGE is specified, the image takes priority over the content area. The bullet content is preserved in speaker notes so the presenter still has the information. This is the simplest correct behavior -- authors who want text alongside images can use the `improve` pipeline or edit the PPTX afterward.

Future enhancement: positioning hints (`IMAGE: path.png | left`) could enable text+image side-by-side in two_column layouts.

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `outline2ppt create` | New behavior | Recognizes LAYOUT and IMAGE directives in outlines |

No new CLI flags are needed. The feature activates automatically when directives appear in the outline.

### Example Usage

```bash
# Create with directives (no --enhance needed for layout control)
python outline2ppt.py create outline-with-images.md template.pptx output.pptx

# Combine with enhancement (author LAYOUT overrides LLM)
python outline2ppt.py create outline-with-images.md template.pptx output.pptx --enhance --model gpt-4o
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_parser.py` | `TestDirectiveParsing` | `parse_outline()` with LAYOUT, IMAGE, both, neither, invalid values |
| `tests/test_parser.py` | `TestResolveImagePath` | Path resolution, missing files, various extensions |
| `tests/test_layouts.py` | `TestImageInsertion` | `apply_layout_content()` with image_path parameter |
| `tests/test_cli.py` | `TestAddSlideDirectives` | `_add_slide()` with layout override, image insertion, enhanced mode override |

### Integration Tests

Add to `tests/test_integration.py`:
- End-to-end test: outline with LAYOUT directives → PPTX with correct layout types
- End-to-end test: outline with IMAGE directive → PPTX with embedded image
- End-to-end test: outline with both directives + `--enhance` → author layout wins

### Manual Testing

1. Create a deck from `examples/outline-with-directives.md` without `--enhance` -- verify layout types match directives and images appear
2. Create a deck from same outline with `--enhance` -- verify author LAYOUT overrides LLM suggestion
3. Create a deck with a missing image path -- verify warning logged and slide created without image
4. Create a deck with an invalid LAYOUT type -- verify warning logged and basic layout used

---

## Changelog Entry

```markdown
### Added
- Outline directives: `LAYOUT:` to specify slide layout type and `IMAGE:` to embed images directly from the outline
- Author-specified layouts override LLM suggestions when using `--enhance`
- Image paths resolved relative to the outline file's directory
- New example outline: `examples/outline-with-directives.md`
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Extract LAYOUT/IMAGE directives in `parse_outline()` | `outline2ppt/parser.py` | -- |
| 2 | Add `resolve_image_path()` helper | `outline2ppt/parser.py` | -- |
| 3 | Add parser unit tests for directive extraction | `tests/test_parser.py` | 1, 2 |
| 4 | Update `apply_layout_content()` to accept `image_path` | `outline2ppt/layouts.py` | -- |
| 5 | Update `_add_slide()` to honor directives | `outline2ppt/cli.py` | 1, 2, 4 |
| 6 | Update `cmd_create()` to resolve image paths after parsing | `outline2ppt/cli.py` | 2, 5 |
| 7 | Add CLI and layout unit tests for directives | `tests/test_cli.py`, `tests/test_layouts.py` | 4, 5, 6 |
| 8 | Add integration tests | `tests/test_integration.py` | 5, 6 |
| 9 | Create example outline with directives | `examples/outline-with-directives.md` | -- |
| 10 | Update CLAUDE.md outline format docs | `CLAUDE.md` | 9 |
| 11 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** `LAYOUT:` lines in slide content could collide with the LLM's `LAYOUT:` response in enhanced mode -- mitigated by extracting author directives in the parser *before* LLM content is mixed in. The parser runs on the raw outline; LLM suggestions are parsed separately by `parse_llm_suggestions()`.
- **Risk:** Large images could exceed slide boundaries or look stretched -- mitigated by using the same sizing as existing `apply_diagram_layout()` (8" × 4"), which works well for landscape images. Authors can adjust in PowerPoint afterward.
- **Question:** Should `IMAGE:` support URLs (download at create time)? Deferred to a future enhancement -- local files only for v1.
- **Question:** Should the `reverse` command output LAYOUT/IMAGE directives when converting PPTX → markdown? Deferred -- would require detecting layout types and extracting embedded images, which is complex.

---

## References

- Existing layout types: `outline2ppt/layouts.py:93` (`KNOWN_LAYOUT_TYPES`)
- Parser: `outline2ppt/parser.py`
- Create pipeline: `outline2ppt/cli.py:10-296` (`cmd_create`, `_add_slide`)
- Image handling: `outline2ppt/images.py`
- PRD template: `docs/plans/PRD-TEMPLATE.md`
