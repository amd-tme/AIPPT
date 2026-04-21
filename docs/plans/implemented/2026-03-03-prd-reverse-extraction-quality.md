# PRD: Reverse Extraction Quality Improvements

**Date:** 2026-03-03
**Author:** Matt
**Status:** Draft

---

## Summary

The `reverse` command produces noisy, flat markdown from PPTX files. Bullet hierarchy is lost, multi-run titles merge without spaces, "Default Section" headers appear verbatim, slides without title placeholders get generic "Untitled Slide" headings, tables lose structure, and decorative shape text (callout numbers, connector labels) pollutes the output. This PRD addresses all six issues with mechanical extraction improvements — no LLM dependency.

## Motivation

- **What problem does this solve?** Reversed markdown is hard to read and edit. Flat bullets lose the information hierarchy that makes outlines useful. Noise from diagram shapes makes the output unreliable for content-heavy decks.
- **Who benefits?** Any user who reverses a deck for editing, remixing, or feeding back into `create`.
- **What happens if we don't do this?** Users must manually clean up every reversed outline. The reverse → edit → create workflow requires significant post-processing.

## Requirements

### Must Have

- [ ] Bullet hierarchy preserved using `paragraph.level` (level 0 → `- `, level 1 → `  - `, level 2 → `    - `)
- [ ] Multi-run/multi-paragraph titles joined with proper spacing (no concatenation without separators)
- [ ] "Default Section" header suppressed — slides in that section still get `##` headings
- [ ] Smarter title fallback chain before defaulting to "Untitled Slide"
- [ ] Tables rendered as proper markdown tables with header row and separator
- [ ] Existing tests updated; new tests for each fix

### Nice to Have

- [ ] Conservative shape filtering: skip connectors, callouts, and shapes with ≤3-char numeric-only text
- [ ] Skip placeholder-type shapes: SLIDE_NUMBER, DATE, FOOTER

### Out of Scope

- LLM-powered reverse enhancement (covered by separate PRD: `2026-03-03-prd-enhanced-reverse.md`)
- Round-trip notes format (covered by `2026-03-02-prd-reverse-roundtrip-fix.md`)
- Two-column layout reconstruction

---

## Design

### Approach

Six targeted changes to `ppt2outline.py`, all backward-compatible. The output format remains markdown with `#`/`##` headings and `-` bullets — only the quality of extraction improves.

#### 1. Bullet Hierarchy via `paragraph.level`

Replace `shape.text` (which flattens all paragraphs) with paragraph-level iteration:

```python
for paragraph in text_frame.paragraphs:
    level = paragraph.level  # 0, 1, or 2
    indent = "  " * level
    text = paragraph.text.strip()
    if text:
        lines.append(f"{indent}- {text}")
```

This applies to both `extract_text_from_shape()` and the content-writing loop. The function signature changes to return structured lines rather than a flat string.

#### 2. Title Text Spacing

Replace `slide.shapes.title.text` with paragraph-aware extraction:

```python
title_parts = []
for para in slide.shapes.title.text_frame.paragraphs:
    if para.text.strip():
        title_parts.append(para.text.strip())
title = " — ".join(title_parts) if len(title_parts) > 1 else title_parts[0]
```

For multi-paragraph titles, use the first paragraph as the `##` heading and emit subsequent paragraphs as the first body content line(s). This handles cases like "Deploying AMD Instinct" + "Network Architecture, Cluster Validation, and Kubernetes" which currently merge as one string.

#### 3. Skip "Default Section"

```python
if section_name and section_name != current_section:
    current_section = section_name
    if section_name != "Default Section":
        f.write(f"# {section_name}\n\n")
```

#### 4. Smarter Title Fallback

Fallback chain when `slide.shapes.title` is empty:

1. `slide.shapes.title.text` (current behavior)
2. First placeholder with `placeholder_format.type == PP_PLACEHOLDER.SUBTITLE` (type 4)
3. First non-empty text shape's first paragraph, if it's a short single line (≤80 chars)
4. `"Untitled Slide"` (last resort)

```python
from pptx.enum.shapes import PP_PLACEHOLDER

def _extract_slide_title(slide) -> str:
    # 1. Standard title placeholder
    if slide.shapes.title and slide.shapes.title.text.strip():
        return _title_from_text_frame(slide.shapes.title.text_frame)

    # 2. Subtitle placeholder
    for shape in slide.placeholders:
        if shape.placeholder_format.type == PP_PLACEHOLDER.SUBTITLE:
            if shape.text.strip():
                return shape.text.strip()

    # 3. First short text shape
    for shape in slide.shapes:
        if shape.has_text_frame and shape.text.strip():
            first_line = shape.text_frame.paragraphs[0].text.strip()
            if first_line and len(first_line) <= 80:
                return first_line

    return "Untitled Slide"
```

#### 5. Markdown Table Formatting

When `shape.has_table`, emit a proper markdown table:

```python
if shape.has_table:
    table = shape.table
    rows_text = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        rows_text.append("| " + " | ".join(cells) + " |")
    if rows_text:
        # Insert separator after first row (header)
        header = rows_text[0]
        col_count = len(table.columns)
        separator = "| " + " | ".join(["---"] * col_count) + " |"
        lines = [header, separator] + rows_text[1:]
        return "\n".join(lines)
```

#### 6. Conservative Shape Filtering

Skip shapes that are decorative rather than content-bearing:

```python
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER

SKIP_PLACEHOLDER_TYPES = {
    PP_PLACEHOLDER.SLIDE_NUMBER,
    PP_PLACEHOLDER.DATE,
    PP_PLACEHOLDER.FOOTER,
}

def _should_skip_shape(shape) -> bool:
    # Skip title (already handled)
    # Skip placeholder types: slide number, date, footer
    if shape.is_placeholder:
        ph_type = shape.placeholder_format.type
        if ph_type in SKIP_PLACEHOLDER_TYPES:
            return True

    # Skip connectors and freeforms
    if shape.shape_type in (MSO_SHAPE_TYPE.LINE, MSO_SHAPE_TYPE.FREEFORM):
        return True

    # Skip shapes with only short numeric text (callout numbers like "1", "2")
    if hasattr(shape, "text") and shape.text.strip():
        text = shape.text.strip()
        if len(text) <= 3 and text.isdigit():
            return True

    return False
```

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/ppt2outline.py` | Modified | All six improvements: paragraph-level extraction, title spacing, Default Section skip, title fallback chain, table formatting, shape filtering |

### Data Model Changes

No data model changes.

---

## CLI Changes

No CLI changes. The `reverse` command behaves the same; only the output quality improves.

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_ppt2outline.py` | `TestBulletHierarchy` | Paragraph-level extraction with levels 0, 1, 2 |
| `tests/test_ppt2outline.py` | `TestTitleExtraction` | Multi-paragraph titles, subtitle fallback, first-text-shape fallback |
| `tests/test_ppt2outline.py` | `TestDefaultSectionSkip` | "Default Section" suppressed from output |
| `tests/test_ppt2outline.py` | `TestTableFormatting` | Markdown table with header separator |
| `tests/test_ppt2outline.py` | `TestShapeFiltering` | Connectors, callout numbers, footer/date/slide-number placeholders skipped |

### Manual Testing

1. Reverse the 3 test decks (Deploying AMD Instinct, Instinct Partitioning, Networking Advantages) — verify improved output quality
2. Verify bullet hierarchy with indented sub-bullets on content-heavy slides
3. Verify "Untitled Slide" count is reduced across all 3 decks
4. Verify diagram-heavy slides (MI300 Logical Architecture) produce less noise
5. Verify tables (Pollara spec tables) render as proper markdown tables

---

## Changelog Entry

```markdown
### Improved
- Reverse: bullet hierarchy preserved using paragraph indentation levels
- Reverse: multi-line titles joined with proper spacing
- Reverse: "Default Section" header suppressed from output
- Reverse: smarter title detection reduces "Untitled Slide" occurrences
- Reverse: tables rendered as proper markdown tables
- Reverse: decorative shapes (connectors, callout numbers, footers) filtered from output
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Refactor `extract_text_from_shape()` to use paragraph-level extraction with `level` | `outline2ppt/ppt2outline.py` | -- |
| 2 | Fix title extraction: paragraph-aware joining, multi-line handling | `outline2ppt/ppt2outline.py` | -- |
| 3 | Skip "Default Section" header emission | `outline2ppt/ppt2outline.py` | -- |
| 4 | Add title fallback chain (subtitle → first text shape → "Untitled Slide") | `outline2ppt/ppt2outline.py` | -- |
| 5 | Implement markdown table formatting for table shapes | `outline2ppt/ppt2outline.py` | 1 |
| 6 | Add conservative shape filtering | `outline2ppt/ppt2outline.py` | -- |
| 7 | Update existing tests and add new test cases for all 6 fixes | `tests/test_ppt2outline.py` | 1-6 |
| 8 | Manual validation with 3 test decks | -- | 7 |
| 9 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Shape filtering may skip meaningful content on unusual slide layouts — mitigation: conservative thresholds (≤3-char numeric only), easy to tune.
- **Risk:** Title fallback to first text shape may pick wrong element on some layouts — mitigation: 80-char length limit and single-paragraph check reduce false positives.
- **Question:** Should multi-paragraph titles use ` — ` separator or newline? Recommendation: first paragraph as heading, subsequent as body text (most natural for outline format).

---

## References

- Related PRDs: `docs/plans/2026-03-02-prd-reverse-roundtrip-fix.md` (notes format)
- Related PRDs: `docs/plans/2026-03-03-prd-enhanced-reverse.md` (LLM-powered reverse)
- Test decks: 3 uploaded PPTX files in `uploads/`
