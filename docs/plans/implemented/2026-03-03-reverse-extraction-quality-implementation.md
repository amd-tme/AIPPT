# Reverse Extraction Quality Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve mechanical text extraction quality in the `reverse` command — preserve bullet hierarchy, fix titles, format tables, filter noise.

**Architecture:** Six targeted improvements to `ppt2outline.py`, all backward-compatible with the enhanced reverse feature just added. `extract_text_from_shape()` changes to paragraph-level extraction (preserving indentation), returns pre-formatted bullet lines. Two new helpers: `_should_skip_shape()` for filtering decorative shapes, `_extract_slide_title()` for smarter title resolution. Main loop updated to use the new helpers and skip "Default Section".

**Tech Stack:** python-pptx (paragraph.level, placeholder_format.type, shape_type enums)

---

### Task 1: Add shape filtering helper

**Files:**
- Modify: `outline2ppt/ppt2outline.py` — add `_should_skip_shape()` function
- Modify: `tests/test_ppt2outline.py` — add `TestShapeFiltering` class

**What to implement:**

Add this helper before `extract_text_from_shape()`:

```python
def _should_skip_shape(shape, title_shape=None) -> bool:
    """Return True if shape is decorative and should be excluded from extraction.

    Filters: title shape (already handled), slide number/date/footer placeholders,
    connector/freeform shapes, and shapes with short numeric-only text (callout labels).
    """
    # Skip title shape (handled separately)
    if title_shape is not None and shape == title_shape:
        return True

    # Skip placeholder types: slide number, date, footer
    if shape.is_placeholder:
        from pptx.enum.shapes import PP_PLACEHOLDER
        ph_type = shape.placeholder_format.type
        if ph_type in (
            PP_PLACEHOLDER.SLIDE_NUMBER,
            PP_PLACEHOLDER.DATE,
            PP_PLACEHOLDER.FOOTER,
        ):
            return True

    # Skip connectors and freeforms
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    if shape.shape_type in (MSO_SHAPE_TYPE.LINE, MSO_SHAPE_TYPE.FREEFORM):
        return True

    # Skip shapes with only short numeric text (callout numbers like "1", "2")
    if hasattr(shape, "text") and shape.text.strip():
        text = shape.text.strip()
        if len(text) <= 3 and text.isdigit():
            return True

    return False
```

**Tests to write:**

```python
class TestShapeFiltering:
    def test_skips_title_shape(self):
        title = MagicMock()
        assert _should_skip_shape(title, title_shape=title) is True

    def test_skips_slide_number_placeholder(self):
        from pptx.enum.shapes import PP_PLACEHOLDER
        shape = MagicMock()
        shape.is_placeholder = True
        shape.placeholder_format.type = PP_PLACEHOLDER.SLIDE_NUMBER
        shape.shape_type = 1  # AUTO_SHAPE
        shape.text = "42"
        assert _should_skip_shape(shape) is True

    def test_skips_footer_placeholder(self):
        from pptx.enum.shapes import PP_PLACEHOLDER
        shape = MagicMock()
        shape.is_placeholder = True
        shape.placeholder_format.type = PP_PLACEHOLDER.FOOTER
        shape.shape_type = 1
        shape.text = "Confidential"
        assert _should_skip_shape(shape) is True

    def test_skips_date_placeholder(self):
        from pptx.enum.shapes import PP_PLACEHOLDER
        shape = MagicMock()
        shape.is_placeholder = True
        shape.placeholder_format.type = PP_PLACEHOLDER.DATE
        shape.shape_type = 1
        shape.text = "2026-03-03"
        assert _should_skip_shape(shape) is True

    def test_skips_connector_line(self):
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        shape = MagicMock()
        shape.is_placeholder = False
        shape.shape_type = MSO_SHAPE_TYPE.LINE
        shape.text = ""
        assert _should_skip_shape(shape) is True

    def test_skips_freeform(self):
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        shape = MagicMock()
        shape.is_placeholder = False
        shape.shape_type = MSO_SHAPE_TYPE.FREEFORM
        shape.text = ""
        assert _should_skip_shape(shape) is True

    def test_skips_short_numeric_text(self):
        shape = MagicMock()
        shape.is_placeholder = False
        shape.shape_type = 1
        shape.text = "2"
        assert _should_skip_shape(shape) is True

    def test_keeps_normal_content_shape(self):
        shape = MagicMock()
        shape.is_placeholder = False
        shape.shape_type = 1
        shape.text = "Real content here"
        assert _should_skip_shape(shape) is False

    def test_keeps_non_numeric_short_text(self):
        shape = MagicMock()
        shape.is_placeholder = False
        shape.shape_type = 1
        shape.text = "OK"
        assert _should_skip_shape(shape) is False
```

**After implementing:**
1. Run: `venv/bin/python -m pytest tests/test_ppt2outline.py::TestShapeFiltering -v`
2. Run: `venv/bin/python -m pytest tests/test_ppt2outline.py -v` (all tests still pass)
3. Commit: `git commit -m "feat(reverse): add shape filtering helper to skip decorative shapes"`

---

### Task 2: Add title extraction helper

**Files:**
- Modify: `outline2ppt/ppt2outline.py` — add `_extract_slide_title()` function
- Modify: `tests/test_ppt2outline.py` — add `TestTitleExtraction` class

**What to implement:**

Add this helper:

```python
def _extract_slide_title(slide) -> str:
    """Extract slide title with fallback chain.

    Resolution order:
    1. Standard title placeholder (paragraph-aware for multi-line titles)
    2. Subtitle placeholder
    3. First short text shape (<=80 chars)
    4. "Untitled Slide" (last resort)
    """
    # 1. Standard title placeholder
    if slide.shapes.title and slide.shapes.title.text.strip():
        tf = slide.shapes.title.text_frame
        parts = [p.text.strip() for p in tf.paragraphs if p.text.strip()]
        if len(parts) > 1:
            return " — ".join(parts)
        return parts[0] if parts else "Untitled Slide"

    # 2. Subtitle placeholder
    from pptx.enum.shapes import PP_PLACEHOLDER
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

**Tests to write:**

```python
class TestTitleExtraction:
    def test_standard_title(self):
        """Uses title placeholder when available."""
        from pptx import Presentation
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "My Title"
        assert _extract_slide_title(slide) == "My Title"

    def test_multi_paragraph_title(self):
        """Joins multi-paragraph titles with em dash."""
        from pptx import Presentation
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        tf = slide.shapes.title.text_frame
        tf.paragraphs[0].text = "Main Title"
        tf.add_paragraph().text = "Subtitle Line"
        assert _extract_slide_title(slide) == "Main Title — Subtitle Line"

    def test_fallback_to_untitled(self):
        """Returns 'Untitled Slide' when no title source found."""
        from pptx import Presentation
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
        # Clear any auto-generated text
        for shape in slide.shapes:
            if shape.has_text_frame:
                shape.text_frame.paragraphs[0].text = ""
        assert _extract_slide_title(slide) == "Untitled Slide"

    def test_whitespace_only_title_triggers_fallback(self):
        """Title with only whitespace triggers fallback chain."""
        from pptx import Presentation
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "   "
        # No other text shapes, should fall back
        result = _extract_slide_title(slide)
        # May find subtitle placeholder or fall to Untitled
        assert result is not None
```

**After implementing:**
1. Run: `venv/bin/python -m pytest tests/test_ppt2outline.py::TestTitleExtraction -v`
2. Run: `venv/bin/python -m pytest tests/test_ppt2outline.py -v`
3. Commit: `git commit -m "feat(reverse): add title extraction helper with fallback chain"`

---

### Task 3: Refactor extract_text_from_shape + update main loop

This is the core task. It changes `extract_text_from_shape()` to use paragraph-level extraction with `level` indentation, formats tables as markdown, and updates the main `convert_pptx_to_outline()` loop to use the new helpers.

**Files:**
- Modify: `outline2ppt/ppt2outline.py` — refactor `extract_text_from_shape()`, update `convert_pptx_to_outline()` main loop
- Modify: `tests/test_ppt2outline.py` — update existing tests, add new tests

**What to implement:**

#### 3a. Refactor `extract_text_from_shape()`

Replace the current implementation with paragraph-aware extraction:

```python
def extract_text_from_shape(shape) -> str:
    """Extract text from a shape, preserving bullet hierarchy and table structure.

    Returns pre-formatted lines:
    - Text frames: each paragraph as "  " * level + "- " + text
    - Groups: recursive extraction
    - Tables: markdown table with header separator
    """
    lines = []

    # Text frame: extract with paragraph-level indentation
    if hasattr(shape, "has_text_frame") and shape.has_text_frame:
        for paragraph in shape.text_frame.paragraphs:
            text = paragraph.text.strip()
            if text:
                level = paragraph.level or 0
                indent = "  " * level
                lines.append(f"{indent}- {text}")

    # Group shapes: recursively extract
    elif hasattr(shape, "shapes"):
        for subshape in shape.shapes:
            subtext = extract_text_from_shape(subshape)
            if subtext:
                lines.append(subtext)

    # Table: render as markdown table
    elif hasattr(shape, "has_table") and shape.has_table:
        table = shape.table
        rows_text = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows_text.append("| " + " | ".join(cells) + " |")
        if rows_text:
            col_count = len(table.columns)
            separator = "| " + " | ".join(["---"] * col_count) + " |"
            lines = [rows_text[0], separator] + rows_text[1:]

    return "\n".join(lines)
```

**Key changes from current code:**
- Uses `has_text_frame` + `text_frame.paragraphs` instead of `shape.text` (flat)
- Each paragraph gets indentation from `paragraph.level`
- Each paragraph is prefixed with `- ` (bullet)
- Tables emit markdown table format with `|` separators and `---` header row
- Returns pre-formatted string (lines already have `- ` prefix and indentation)

#### 3b. Update `convert_pptx_to_outline()` main loop

Replace the title extraction, shape iteration, and content writing sections:

1. **Title:** Replace inline title code with `_extract_slide_title(slide)` call
2. **Section skip:** Add `if section_name != "Default Section":` guard
3. **Shape loop:** Add `_should_skip_shape()` filter before `extract_text_from_shape()`
4. **Content writing:** Since `extract_text_from_shape()` now returns pre-formatted lines, the writing loop simplifies — just write each line directly (no more `startswith` check for adding `- ` prefix)

The enhanced reverse path also needs updating: it builds `mechanical_text` from `extract_text_from_shape()` — no change needed since the function still returns a string. But the shape loop should use `_should_skip_shape()` there too for better LLM context.

Updated main loop (mechanical path):
```python
                # Use new title helper
                title = _extract_slide_title(slide)

                # Skip "Default Section"
                if section_name and section_name != current_section:
                    current_section = section_name
                    if section_name != "Default Section":
                        f.write(f"# {section_name}\n\n")

                # ...enhanced path shape extraction should also use _should_skip_shape...

                # Mechanical extraction
                content = []
                for shape in slide.shapes:
                    if _should_skip_shape(shape, title_shape=slide.shapes.title):
                        continue
                    text = extract_text_from_shape(shape)
                    if text:
                        content.append(text)

                # Write content — lines are pre-formatted with bullets
                for text in content:
                    for line in text.split('\n'):
                        if line.strip():
                            f.write(f"{line}\n")
```

#### 3c. Update existing tests

The existing `TestExtractTextFromShape` tests will need updating because the return format changes:
- `"Simple text content"` → `"- Simple text content"`
- `"Text with spaces"` → `"- Text with spaces"`
- Group shapes: each subshape gets `- ` prefix
- Table: now uses markdown table format `| Cell 1 | Cell 2 |`
- Empty shape: still returns `""`

**Updated test expectations:**

```python
class TestExtractTextFromShape:
    def test_extracts_simple_text(self):
        shape = MagicMock()
        shape.has_text_frame = True
        para = MagicMock()
        para.text = "Simple text content"
        para.level = 0
        shape.text_frame.paragraphs = [para]
        result = extract_text_from_shape(shape)
        assert result == "- Simple text content"

    def test_extracts_text_with_whitespace(self):
        shape = MagicMock()
        shape.has_text_frame = True
        para = MagicMock()
        para.text = "  Text with spaces  "
        para.level = 0
        shape.text_frame.paragraphs = [para]
        result = extract_text_from_shape(shape)
        assert result == "- Text with spaces"

    def test_preserves_bullet_hierarchy(self):
        shape = MagicMock()
        shape.has_text_frame = True
        p0 = MagicMock(); p0.text = "Top level"; p0.level = 0
        p1 = MagicMock(); p1.text = "Indented"; p1.level = 1
        p2 = MagicMock(); p2.text = "Deep indent"; p2.level = 2
        shape.text_frame.paragraphs = [p0, p1, p2]
        result = extract_text_from_shape(shape)
        assert "- Top level" in result
        assert "  - Indented" in result
        assert "    - Deep indent" in result

    def test_handles_table_as_markdown(self):
        # Table shape mock...
        # Result should be markdown table with | and --- separator
        ...

    # ... other existing tests updated ...
```

Also add `TestBulletHierarchy` and `TestTableFormatting` classes as specified in the PRD testing section.

**After implementing:**
1. Run: `venv/bin/python -m pytest tests/test_ppt2outline.py -v`
2. Run: `venv/bin/python -m pytest tests/ -v` (full suite — CLI tests, enhanced reverse tests, etc.)
3. Commit: `git commit -m "feat(reverse): paragraph-level bullet hierarchy, markdown tables, shape filtering, title fallback"`

---

### Task 4: Full test suite verification + changelog

**Files:**
- Modify: `CHANGELOG.md`

**Steps:**

1. Run: `venv/bin/python -m pytest tests/ -v` — all tests pass
2. Verify `reverse --help` still works: `venv/bin/python outline2ppt.py reverse --help`
3. Add changelog entries under `## [Unreleased]` → `### Improved`:

```markdown
### Improved
- Reverse: bullet hierarchy preserved using paragraph indentation levels
- Reverse: multi-line titles joined with proper spacing
- Reverse: "Default Section" header suppressed from output
- Reverse: smarter title detection reduces "Untitled Slide" occurrences
- Reverse: tables rendered as proper markdown tables
- Reverse: decorative shapes (connectors, callout numbers, footers) filtered from output
```

4. Commit: `git commit -m "docs: add changelog entries for reverse extraction quality improvements"`
