# Slide Improvement Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade `create --enhance` with better formatting, then add an `improve` command that closes the analyze → rewrite → apply feedback loop.

**Architecture:** Two phases. Phase 1 upgrades `_apply_bullets_to_text_frame()` with font sizing, bold lead-ins, numbered lists, column headers, and placeholder images. Phase 2 adds `outline2ppt/improve.py` with a per-slide pipeline: extract content → analyze with vision → LLM rewrites content → apply back to PPTX. Both phases use `_apply_bullets_to_text_frame()` as the shared content writer.

**Tech Stack:** python-pptx (Pt, RGBColor, MSO_SHAPE), existing LLMClient, existing analyze_slide()

---

## Phase 1: Enhanced Initial Generation

### Task 1: Add font sizing to `_apply_bullets_to_text_frame()`

**Files:**
- Modify: `outline2ppt/layouts.py:254-281`
- Test: `tests/test_layouts.py`

**Step 1: Write the failing test**

Add to `tests/test_layouts.py`:

```python
from pptx import Presentation
from pptx.util import Pt

from outline2ppt.layouts import _apply_bullets_to_text_frame


class TestApplyBulletsFormatting:
    """Tests for _apply_bullets_to_text_frame font sizing."""

    def _make_text_frame(self):
        """Create a real text frame from a blank slide."""
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        from pptx.util import Inches
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(3))
        return tb.text_frame

    def test_level_0_font_size(self):
        tf = self._make_text_frame()
        _apply_bullets_to_text_frame(tf, "Plain text line")
        run = tf.paragraphs[0].runs[0]
        assert run.font.size == Pt(22)

    def test_level_1_bullet_font_size(self):
        tf = self._make_text_frame()
        _apply_bullets_to_text_frame(tf, "- Bullet item")
        run = tf.paragraphs[0].runs[0]
        assert run.font.size == Pt(22)

    def test_level_2_subbullet_font_size(self):
        tf = self._make_text_frame()
        _apply_bullets_to_text_frame(tf, "  - Sub bullet")
        run = tf.paragraphs[0].runs[0]
        assert run.font.size == Pt(18)

    def test_mixed_levels_get_correct_sizes(self):
        tf = self._make_text_frame()
        _apply_bullets_to_text_frame(tf, "- Top bullet\n  - Sub bullet\n- Another top")
        assert tf.paragraphs[0].runs[0].font.size == Pt(22)
        assert tf.paragraphs[1].runs[0].font.size == Pt(18)
        assert tf.paragraphs[2].runs[0].font.size == Pt(22)
```

**Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_layouts.py::TestApplyBulletsFormatting -v`
Expected: FAIL — `_apply_bullets_to_text_frame` currently uses `p.text =` (no runs, no font size)

**Step 3: Write minimal implementation**

Modify `outline2ppt/layouts.py`. Add import at top:

```python
from pptx.util import Inches, Pt
```

Replace the `_apply_bullets_to_text_frame` function (lines 254-281):

```python
def _apply_bullets_to_text_frame(tf, content: str):
    """Apply bullet-processed content lines to a text frame.

    Processes markdown-style bullet markers and indentation into
    proper paragraph levels. Sets font sizes: Pt(22) for level 0-1,
    Pt(18) for level 2 sub-bullets.

    Args:
        tf: A python-pptx TextFrame object
        content: Multi-line text content with bullet points
    """
    first_para = True
    for line in content.split('\n'):
        if line.strip():
            if first_para:
                p = tf.paragraphs[0]
                first_para = False
            else:
                p = tf.add_paragraph()

            stripped = line.strip()
            if stripped.startswith('  -') or stripped.startswith('  •') or stripped.startswith('  *'):
                level = 2
                text = stripped.lstrip(' -•*')
            elif stripped.startswith(('-', '•', '*')):
                level = 1
                text = stripped.lstrip('-•* ')
            else:
                level = 0
                text = stripped

            p.level = level
            font_size = Pt(18) if level == 2 else Pt(22)

            run = p.add_run()
            run.text = text
            run.font.size = font_size
```

Note: We switch from `p.text = ...` to `p.add_run()` so we can set `run.font.size`. This is the key change — `p.text` creates a default run but doesn't let us control font properties.

**Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_layouts.py::TestApplyBulletsFormatting -v`
Expected: PASS

**Step 5: Run full test suite to check for regressions**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: All 374 pass. Some existing tests may need updating if they check `p.text` (which no longer works the same when using `add_run()`). If tests fail, check whether they assert on `p.text` and update to use `p.runs[0].text` instead.

**Step 6: Commit**

```bash
git add outline2ppt/layouts.py tests/test_layouts.py
git commit -m "feat: add font sizing to bullet text frames (Pt(22)/Pt(18))"
```

---

### Task 2: Add bold lead-in formatting

**Files:**
- Modify: `outline2ppt/layouts.py` (the `_apply_bullets_to_text_frame` function from Task 1)
- Test: `tests/test_layouts.py`

**Step 1: Write the failing test**

Add to `TestApplyBulletsFormatting` in `tests/test_layouts.py`:

```python
    def test_bold_lead_in_with_colon(self):
        tf = self._make_text_frame()
        _apply_bullets_to_text_frame(tf, "- Content hashing: SHA-256 for dedup")
        p = tf.paragraphs[0]
        # First run is the bold lead-in, second run is the rest
        assert len(p.runs) == 2
        assert p.runs[0].text == "Content hashing: "
        assert p.runs[0].font.bold is True
        assert p.runs[1].text == "SHA-256 for dedup"
        assert p.runs[1].font.bold is not True

    def test_bold_lead_in_with_em_dash(self):
        tf = self._make_text_frame()
        _apply_bullets_to_text_frame(tf, "- Graceful degradation — failures don't crash")
        p = tf.paragraphs[0]
        assert len(p.runs) == 2
        assert p.runs[0].text == "Graceful degradation — "
        assert p.runs[0].font.bold is True

    def test_no_bold_when_lead_in_too_long(self):
        tf = self._make_text_frame()
        _apply_bullets_to_text_frame(tf, "- This is a much longer phrase that has: a colon somewhere")
        p = tf.paragraphs[0]
        # More than 4 words before colon — no bold
        assert len(p.runs) == 1
        assert p.runs[0].font.bold is not True

    def test_no_bold_when_no_separator(self):
        tf = self._make_text_frame()
        _apply_bullets_to_text_frame(tf, "- Just a plain bullet point")
        p = tf.paragraphs[0]
        assert len(p.runs) == 1
        assert p.runs[0].font.bold is not True
```

**Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_layouts.py::TestApplyBulletsFormatting::test_bold_lead_in_with_colon -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Add a helper function to `layouts.py` above `_apply_bullets_to_text_frame`:

```python
import re

def _detect_lead_in(text: str):
    """Detect a bold lead-in pattern (1-4 words followed by : or —).

    Returns:
        Tuple of (lead_in, rest) if pattern found, or (None, text) if not.
    """
    # Match 1-4 words followed by ": " or " — "
    match = re.match(r'^(\S+(?:\s+\S+){0,3}(?::\s| — ))(.*)', text)
    if match:
        return match.group(1), match.group(2)
    return None, text
```

Then update the bottom of `_apply_bullets_to_text_frame` — replace the section that creates the run:

```python
            p.level = level
            font_size = Pt(18) if level == 2 else Pt(22)

            lead_in, rest = _detect_lead_in(text)
            if lead_in:
                run_bold = p.add_run()
                run_bold.text = lead_in
                run_bold.font.size = font_size
                run_bold.font.bold = True
                run_rest = p.add_run()
                run_rest.text = rest
                run_rest.font.size = font_size
            else:
                run = p.add_run()
                run.text = text
                run.font.size = font_size
```

**Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_layouts.py::TestApplyBulletsFormatting -v`
Expected: All pass

**Step 5: Commit**

```bash
git add outline2ppt/layouts.py tests/test_layouts.py
git commit -m "feat: add bold lead-in formatting for keyword: description bullets"
```

---

### Task 3: Add `numbered` layout type

**Files:**
- Modify: `outline2ppt/layouts.py:91` (KNOWN_LAYOUT_TYPES), `layouts.py:75-80` (layout_map), `layouts.py:155` (apply_layout_content)
- Modify: `outline2ppt/enhancer.py:27,79-84,92-96` (prompt)
- Test: `tests/test_layouts.py`

**Step 1: Write the failing tests**

Add to `tests/test_layouts.py`:

```python
from outline2ppt.layouts import apply_layout_content, KNOWN_LAYOUT_TYPES


class TestNumberedLayout:
    """Tests for numbered list layout support."""

    def _make_slide(self):
        prs = Presentation()
        layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(layout)
        return prs, slide

    def test_numbered_in_known_layout_types(self):
        assert 'numbered' in KNOWN_LAYOUT_TYPES

    def test_parse_numbered_layout(self):
        result = parse_layout_suggestion("numbered")
        assert result['type'] == 'numbered'

    def test_apply_bullets_numbered_items(self):
        """Numbered items (1., 2.) should be rendered with level 0 and font size."""
        from outline2ppt.layouts import _apply_bullets_to_text_frame
        from pptx.util import Inches
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(3))
        tf = tb.text_frame

        _apply_bullets_to_text_frame(tf, "1. First step\n2. Second step\n3. Third step")

        assert tf.paragraphs[0].runs[0].text == "1. First step"
        assert tf.paragraphs[0].level == 0
        assert tf.paragraphs[1].runs[0].text == "2. Second step"
        assert tf.paragraphs[2].runs[0].text == "3. Third step"
```

**Step 2: Run to verify failure**

Run: `venv/bin/python -m pytest tests/test_layouts.py::TestNumberedLayout -v`
Expected: FAIL — `numbered` not in KNOWN_LAYOUT_TYPES

**Step 3: Implement**

In `outline2ppt/layouts.py`:

1. Add `'numbered'` to `KNOWN_LAYOUT_TYPES` (line 91):
```python
KNOWN_LAYOUT_TYPES = {'bullet', 'two_column', 'diagram', 'basic', 'numbered'}
```

2. Add `'numbered'` to `layout_map` in `select_slide_layout` (line 75-80):
```python
    layout_map = {
        'diagram': 'Title Only',
        'two_column': 'Two Content',
        'bullet': 'Title and Content',
        'basic': 'Title and Content',
        'numbered': 'Title and Content',
    }
```

3. Add numbered case in `apply_layout_content` (after the bullet case, around line 178):
```python
        if layout_type in ('bullet', 'numbered'):
            apply_bullet_layout(slide, content, suggestions)
```

4. Update `_apply_bullets_to_text_frame` to handle numbered items — in the line parsing section, add numbered detection before the bullet check:
```python
            # Detect numbered items: "1. ", "2. ", etc.
            num_match = re.match(r'^(\d+\.\s)(.*)', stripped)
            if num_match:
                level = 0
                text = stripped  # Keep the number prefix
            elif stripped.startswith('  -') or stripped.startswith('  •') or stripped.startswith('  *'):
                level = 2
                text = stripped.lstrip(' -•*')
            elif stripped.startswith(('-', '•', '*')):
                level = 1
                text = stripped.lstrip('-•* ')
            else:
                level = 0
                text = stripped
```

**Step 4: Run tests**

Run: `venv/bin/python -m pytest tests/test_layouts.py::TestNumberedLayout -v`
Expected: PASS

**Step 5: Update enhance prompt**

In `outline2ppt/enhancer.py`, update the prompt (line 76-96). Add `numbered` to the layout options:

```python
    prompt = f"""For this slide, provide enhancement suggestions:

1. A brief narrative (2-3 sentences) contextualizing the slide content
2. A layout type — output ONLY the keyword, nothing else on that line:
   - bullet — Best for lists, key points, single-topic content, or detailed descriptions
   - numbered — Best for sequential steps, processes, or ordered workflows
   - two_column — Best when content has natural pairs, parallel concepts, comparisons, before/after, input/output, problem/solution, or can be meaningfully split into two complementary halves
   - basic — Use only for minimal content, single statements, or title-only slides
{diagram_guidance}
   Aim for layout variety across the deck. Not every slide should be bullet — use two_column for slides where the content naturally divides into two groups. Use numbered for sequential processes.
3. Presentation delivery tips (these appear in speaker notes — focus on what to emphasize verbally, how to pace the content, and key points to expand on rather than graphic design suggestions)
4. Additional talking points the presenter should cover

Slide Title: {slide['title']}
Content:
{content_text}

Format your response exactly as:
NARRATIVE: [2-3 sentences]
LAYOUT: [single keyword only: bullet, numbered, two_column, basic, or diagram]
VISUALS: [delivery tips and emphasis guidance]
TALKING_POINTS: [additional points]
"""
```

Also update `SYSTEM_PROMPT` (line 19-39) to add numbered:

```python
    "- numbered: title + numbered body text (1., 2., 3.) for sequential steps\n"
```

**Step 6: Run full suite**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: All pass

**Step 7: Commit**

```bash
git add outline2ppt/layouts.py outline2ppt/enhancer.py tests/test_layouts.py
git commit -m "feat: add numbered layout type for sequential content"
```

---

### Task 4: Add column headers to two-column layout

**Files:**
- Modify: `outline2ppt/layouts.py:284-324` (apply_two_column_layout)
- Modify: `outline2ppt/parser.py:95-119` (parse_llm_suggestions)
- Modify: `outline2ppt/enhancer.py` (prompt format)
- Test: `tests/test_layouts.py`, `tests/test_parser.py`

**Step 1: Write the failing tests**

Add to `tests/test_parser.py`:

```python
class TestParseLayoutColumnHeaders:
    """Test parsing column headers from LAYOUT line."""

    def test_two_column_with_headers(self):
        content = [
            "NARRATIVE: some narrative",
            "LAYOUT: two_column | Left Header | Right Header",
            "VISUALS: tips",
            "TALKING_POINTS: points",
        ]
        result = parse_llm_suggestions(content)
        assert result['LAYOUT'] == 'two_column | Left Header | Right Header'

    def test_parse_column_headers_from_layout(self):
        from outline2ppt.parser import parse_column_headers
        left, right = parse_column_headers("two_column | Cataloging | Search")
        assert left == "Cataloging"
        assert right == "Search"

    def test_parse_column_headers_none_when_absent(self):
        from outline2ppt.parser import parse_column_headers
        left, right = parse_column_headers("two_column")
        assert left is None
        assert right is None

    def test_parse_column_headers_none_for_other_layout(self):
        from outline2ppt.parser import parse_column_headers
        left, right = parse_column_headers("bullet")
        assert left is None
        assert right is None
```

Add to `tests/test_layouts.py`:

```python
class TestTwoColumnWithHeaders:
    """Test column headers in two-column layout."""

    def test_column_headers_applied_as_bold_first_para(self):
        from outline2ppt.layouts import _apply_bullets_to_text_frame
        from pptx.util import Inches

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(3))
        tf = tb.text_frame

        # Simulate applying a column header then content
        _apply_bullets_to_text_frame(tf, "- Item one\n- Item two", header="My Header")

        # First paragraph should be the bold header
        assert tf.paragraphs[0].runs[0].text == "My Header"
        assert tf.paragraphs[0].runs[0].font.bold is True
        # Second paragraph should be actual content
        assert tf.paragraphs[1].runs[0].text == "Item one"
```

**Step 2: Run to verify failure**

Run: `venv/bin/python -m pytest tests/test_parser.py::TestParseLayoutColumnHeaders tests/test_layouts.py::TestTwoColumnWithHeaders -v`
Expected: FAIL — `parse_column_headers` doesn't exist, `header` param not supported

**Step 3: Implement parser change**

Add to `outline2ppt/parser.py` after `parse_llm_suggestions`:

```python
def parse_column_headers(layout_text: str):
    """Parse column headers from LAYOUT line.

    Expected format: "two_column | Left Header | Right Header"

    Returns:
        Tuple of (left_header, right_header), or (None, None) if not present.
    """
    if '|' not in layout_text:
        return None, None
    parts = [p.strip() for p in layout_text.split('|')]
    if len(parts) >= 3:
        return parts[1], parts[2]
    return None, None
```

**Step 4: Implement layout change**

Update `_apply_bullets_to_text_frame` signature and body in `layouts.py`:

```python
def _apply_bullets_to_text_frame(tf, content: str, header: str = None):
```

At the top of the function body, before the `first_para` loop, add:

```python
    if header:
        p = tf.paragraphs[0]
        p.level = 0
        run = p.add_run()
        run.text = header
        run.font.bold = True
        run.font.size = Pt(22)
        first_para = False  # Next content line creates a new paragraph
    else:
        first_para = True
```

Remove the existing `first_para = True` line that follows.

**Step 5: Wire up column headers in apply_two_column_layout**

Update `apply_two_column_layout` (line 284) to accept and use headers:

```python
def apply_two_column_layout(slide, content: str, suggestions: Optional[Dict] = None):
```

Add header parsing inside the function, before calling `_apply_bullets_to_text_frame`:

```python
    from outline2ppt.parser import parse_column_headers
    left_header, right_header = None, None
    if suggestions:
        left_header, right_header = parse_column_headers(suggestions.get('LAYOUT', ''))

    _apply_bullets_to_text_frame(left_tf, left_content, header=left_header)
    _apply_bullets_to_text_frame(right_tf, right_content, header=right_header)
```

**Step 6: Update enhance prompt**

In `enhancer.py`, update the LAYOUT format line (around line 94):

Change:
```
LAYOUT: [single keyword only: bullet, numbered, two_column, basic, or diagram]
```
To:
```
LAYOUT: [keyword, or for two_column include headers: two_column | Left Header | Right Header]
```

**Step 7: Run tests**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: All pass

**Step 8: Commit**

```bash
git add outline2ppt/layouts.py outline2ppt/parser.py outline2ppt/enhancer.py tests/test_layouts.py tests/test_parser.py
git commit -m "feat: add column headers to two-column layout via LLM suggestion"
```

---

### Task 5: Add placeholder image for diagram fallback

**Files:**
- Modify: `outline2ppt/layouts.py` (new function)
- Modify: `outline2ppt/cli.py:231-235` (diagram fallback in `_add_slide`)
- Test: `tests/test_layouts.py`

**Step 1: Write the failing test**

Add to `tests/test_layouts.py`:

```python
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor


class TestPlaceholderImage:
    """Tests for diagram placeholder shape."""

    def test_adds_placeholder_shape(self):
        from outline2ppt.layouts import apply_placeholder_image
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        shape_count_before = len(slide.shapes)

        apply_placeholder_image(slide, "Architecture flow diagram")

        assert len(slide.shapes) == shape_count_before + 1

    def test_placeholder_contains_description(self):
        from outline2ppt.layouts import apply_placeholder_image
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])

        apply_placeholder_image(slide, "Network topology diagram")

        # Find the new shape (last added)
        shape = slide.shapes[-1]
        assert "Network topology diagram" in shape.text_frame.text
```

**Step 2: Run to verify failure**

Run: `venv/bin/python -m pytest tests/test_layouts.py::TestPlaceholderImage -v`
Expected: FAIL — function doesn't exist

**Step 3: Implement**

Add to `outline2ppt/layouts.py`:

```python
from pptx.dml.color import RGBColor


def apply_placeholder_image(slide, description: str):
    """Insert a placeholder rectangle with description text for future image generation.

    Creates a centered light gray rectangle in the content area with
    descriptive text indicating what image should be generated.

    Args:
        slide: A python-pptx Slide object
        description: Description of the intended diagram/image
    """
    left = Inches(1.5)
    top = Inches(2.0)
    width = Inches(7.0)
    height = Inches(4.0)

    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, left, top, width, height
    )

    # Light gray fill
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(0xE0, 0xE0, 0xE0)

    # Thin border
    shape.line.color.rgb = RGBColor(0xB0, 0xB0, 0xB0)
    shape.line.width = Pt(1)

    # Add description text
    tf = shape.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = f"[Image: {description}]"
    run.font.size = Pt(16)
    run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
    run.font.italic = True
```

**Step 4: Update diagram fallback in cli.py**

In `outline2ppt/cli.py`, replace the diagram-to-bullet remap (lines 231-235):

```python
        # When diagram is requested but image gen is disabled,
        # use bullet layout but also add a placeholder image shape
        if layout_info['type'] == 'diagram' and image_gen == 'none':
            logger.info("Diagram layout requested but image gen disabled — adding placeholder")
            layout_info['type'] = 'bullet'
            layout_info['_add_placeholder'] = True
            layout_info['_placeholder_desc'] = suggestions.get('VISUALS', 'Diagram')
```

Then after `apply_layout_content(...)` (around line 266), add:

```python
        # Add placeholder image if diagram was requested without image gen
        if layout_info.get('_add_placeholder'):
            from outline2ppt.layouts import apply_placeholder_image
            apply_placeholder_image(slide, layout_info['_placeholder_desc'])
```

**Step 5: Run tests**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: All pass

**Step 6: Commit**

```bash
git add outline2ppt/layouts.py outline2ppt/cli.py tests/test_layouts.py
git commit -m "feat: add placeholder image shape for diagram fallback"
```

---

### Task 6: Phase 1 integration test

**Files:**
- No new files — run against real template

**Step 1: Run the full test suite**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: All pass

**Step 2: Generate an enhanced deck with the improvements**

Run: `venv/bin/python outline2ppt.py --debug create outlines/outline2ppt-overview.md "templates/AMD Powerpoint Template.pptx" output/outline2ppt-overview-enhanced-v5.pptx --enhance`

**Step 3: Inspect the output**

```python
venv/bin/python -c "
from pptx import Presentation
from pptx.util import Pt
prs = Presentation('output/outline2ppt-overview-enhanced-v5.pptx')
for i, slide in enumerate(prs.slides, 1):
    title = slide.shapes.title.text if slide.shapes.title else '?'
    for shape in slide.placeholders:
        if shape.placeholder_format.idx == 0:
            continue
        for p in shape.text_frame.paragraphs:
            if p.runs:
                r = p.runs[0]
                print(f'Slide {i} [{title}] level={p.level} bold={r.font.bold} size={r.font.size} text={r.text[:50]}')
                break
    break  # Just check first slide for quick verification
"
```

Expected: Font sizes are Pt(22) or Pt(18), bold lead-ins appear where appropriate.

**Step 4: Commit the test output reference (optional)**

```bash
git add -f output/outline2ppt-overview-enhanced-v5.pptx  # Only if you want to track it
```

---

## Phase 2: Improve Command

### Task 7: Create `outline2ppt/improve.py` with core functions

**Files:**
- Create: `outline2ppt/improve.py`
- Test: `tests/test_improve.py`

**Step 1: Write the failing tests**

Create `tests/test_improve.py`:

```python
"""Tests for outline2ppt.improve module."""

import pytest
from unittest.mock import MagicMock, patch
from pptx import Presentation
from pptx.util import Inches

from outline2ppt.improve import (
    build_rewrite_prompt,
    parse_rewritten_content,
    extract_slide_content,
)


class TestBuildRewritePrompt:
    def test_includes_title(self):
        prompt = build_rewrite_prompt("My Title", "- bullet 1", "some feedback")
        assert "My Title" in prompt

    def test_includes_current_content(self):
        prompt = build_rewrite_prompt("Title", "- bullet 1\n- bullet 2", "feedback")
        assert "- bullet 1" in prompt
        assert "- bullet 2" in prompt

    def test_includes_feedback(self):
        prompt = build_rewrite_prompt("Title", "- content", "Add more detail about X")
        assert "Add more detail about X" in prompt

    def test_includes_constraints(self):
        prompt = build_rewrite_prompt("Title", "- content", "feedback")
        assert "Return ONLY improved bullet content" in prompt


class TestParseRewrittenContent:
    def test_extracts_bullets(self):
        response = "- Improved bullet one\n- Improved bullet two\n- Third bullet"
        result = parse_rewritten_content(response)
        assert "- Improved bullet one" in result
        assert "- Improved bullet two" in result

    def test_strips_preamble_text(self):
        response = "Here are the improvements:\n\n- Actual bullet\n- Another bullet"
        result = parse_rewritten_content(response)
        assert "Here are the improvements" not in result
        assert "- Actual bullet" in result

    def test_handles_numbered_items(self):
        response = "1. First step\n2. Second step"
        result = parse_rewritten_content(response)
        assert "1. First step" in result

    def test_preserves_sub_bullets(self):
        response = "- Top level\n  - Sub bullet\n- Another top"
        result = parse_rewritten_content(response)
        assert "  - Sub bullet" in result


class TestExtractSlideContent:
    def test_extracts_title_and_body(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        # Add a textbox with content (simulating a body placeholder)
        tb = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(5), Inches(3))
        tf = tb.text_frame
        tf.paragraphs[0].text = "First bullet"
        tf.add_paragraph().text = "Second bullet"

        title, body = extract_slide_content(slide)
        assert "First bullet" in body
        assert "Second bullet" in body
```

**Step 2: Run to verify failure**

Run: `venv/bin/python -m pytest tests/test_improve.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement**

Create `outline2ppt/improve.py`:

```python
"""Slide improvement pipeline.

Analyzes existing slides with multimodal feedback, rewrites content
via LLM, and applies improvements back to the PPTX.
"""

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


REWRITE_SYSTEM_PROMPT = (
    "You are a presentation content expert rewriting slide content based on "
    "expert feedback. You improve specificity, organization, and detail while "
    "keeping the same topic and title.\n\n"
    "Constraints:\n"
    "- Return ONLY the improved bullet content, nothing else\n"
    "- One bullet per line starting with '- '\n"
    "- Use '  - ' (2-space indent) for sub-bullets\n"
    "- Use numbered items (1., 2., 3.) if the content is sequential\n"
    "- Use 'Keyword: description' format for bold lead-ins where appropriate\n"
    "- Keep total content to 4-8 bullets (with sub-bullets as needed)\n"
    "- Focus on: specificity, concrete examples, technical accuracy, "
    "logical organization\n"
    "- Do NOT suggest colors, fonts, icons, shapes, or visual design changes\n"
    "- Do NOT include any preamble, explanation, or commentary"
)


def build_rewrite_prompt(title: str, current_content: str, feedback: str) -> str:
    """Build the prompt for LLM content rewrite.

    Args:
        title: Slide title
        current_content: Current bullet content as newline-separated text
        feedback: Structured improvement feedback from analysis

    Returns:
        Prompt string for LLM
    """
    return f"""Rewrite this slide's content to address the expert feedback below.
Return ONLY improved bullet content — no preamble, no explanation.

Slide title: {title}

Current content:
{current_content}

Expert feedback:
{feedback}
"""


def parse_rewritten_content(response: str) -> str:
    """Parse LLM response to extract only bullet/numbered content lines.

    Strips any preamble text the LLM may add before the actual bullets.

    Args:
        response: Raw LLM response text

    Returns:
        Cleaned content string with only bullet/numbered lines
    """
    lines = response.strip().split('\n')
    content_lines = []
    for line in lines:
        stripped = line.strip()
        # Keep lines that start with bullet markers, numbered items, or indented sub-bullets
        if (stripped.startswith(('-', '•', '*')) or
                re.match(r'^\d+\.', stripped) or
                line.startswith('  ')):
            content_lines.append(line)
    return '\n'.join(content_lines) if content_lines else response.strip()


def extract_slide_content(slide) -> Tuple[str, str]:
    """Extract title and body text from a PPTX slide.

    Args:
        slide: A pptx.slide.Slide object

    Returns:
        Tuple of (title, body_text)
    """
    title = ""
    if slide.shapes.title:
        title = slide.shapes.title.text

    body_lines = []
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        # Skip the title shape
        if shape.has_text_frame and shape.text_frame.text.strip() == title.strip():
            continue
        for para in shape.text_frame.paragraphs:
            text = para.text.strip()
            if text:
                prefix = "  - " if para.level >= 2 else "- " if para.level >= 1 else ""
                body_lines.append(f"{prefix}{text}")

    return title, '\n'.join(body_lines)


def improve_slide(slide, image_path: Optional[str], client, dry_run: bool = False):
    """Run the improve pipeline on a single slide.

    Args:
        slide: A pptx.slide.Slide object
        image_path: Path to slide PNG image (or None for text-only)
        client: LLMClient instance
        dry_run: If True, return changes without applying

    Returns:
        Dict with 'title', 'original', 'improved', 'feedback', 'applied'
    """
    from outline2ppt.analyze import analyze_slide
    from outline2ppt.layouts import _apply_bullets_to_text_frame

    title, current_content = extract_slide_content(slide)

    if not current_content.strip():
        logger.info(f"Skipping slide '{title}' — no body content")
        return {'title': title, 'original': '', 'improved': '', 'feedback': '', 'applied': False}

    # Step 1: Analyze
    feedback = analyze_slide(
        client=client,
        image_path=image_path,
        mode='improvements',
        title=title,
        content_text=current_content,
    )

    # Step 2: Rewrite
    prompt = build_rewrite_prompt(title, current_content, feedback)
    improved = client.generate_text(
        prompt=prompt,
        system_prompt=REWRITE_SYSTEM_PROMPT,
        max_tokens=1000,
        temperature=0.3,
    )
    improved = parse_rewritten_content(improved)

    result = {
        'title': title,
        'original': current_content,
        'improved': improved,
        'feedback': feedback,
        'applied': False,
    }

    if dry_run:
        return result

    # Step 3: Apply — find the body placeholder and rewrite it
    body_placeholder = None
    for shape in slide.placeholders:
        idx = shape.placeholder_format.idx
        if idx > 0:
            body_placeholder = shape
            break

    if body_placeholder:
        tf = body_placeholder.text_frame
        tf.clear()
        _apply_bullets_to_text_frame(tf, improved)
        result['applied'] = True
    else:
        logger.warning(f"No body placeholder found for slide '{title}' — skipping apply")

    # Step 4: Update speaker notes with revision history
    try:
        notes_tf = slide.notes_slide.notes_text_frame
        existing_notes = notes_tf.text
        revision = f"\n\n--- Revision ---\nOriginal:\n{current_content}\n\nImproved:\n{improved}"
        notes_tf.text = existing_notes + revision
    except Exception as e:
        logger.warning(f"Could not update notes for slide '{title}': {e}")

    return result


def improve_deck(pptx_path: str, output_path: Optional[str] = None,
                 images_dir: Optional[str] = None, slides_filter: Optional[list] = None,
                 passes: int = 1, dry_run: bool = False, client=None):
    """Run the improve pipeline on an entire deck.

    Args:
        pptx_path: Path to the PPTX file
        output_path: Output path (default: overwrite in-place)
        images_dir: Directory with slide images
        slides_filter: List of 1-based slide numbers to improve (None = all)
        passes: Number of improvement passes
        dry_run: If True, show changes without modifying
        client: LLMClient instance

    Returns:
        List of result dicts, one per slide processed
    """
    import os
    from pptx import Presentation

    prs = Presentation(pptx_path)
    save_path = output_path or pptx_path
    all_results = []

    for pass_num in range(1, passes + 1):
        if passes > 1:
            logger.info(f"=== Pass {pass_num}/{passes} ===")

        for i, slide in enumerate(prs.slides, 1):
            if slides_filter and i not in slides_filter:
                continue

            # Find image path
            image_path = None
            if images_dir:
                for ext in ('.png', '.jpg', '.jpeg'):
                    candidate = os.path.join(images_dir, f"slide_{i}{ext}")
                    if os.path.exists(candidate):
                        image_path = candidate
                        break

            logger.info(f"Improving slide {i}/{len(prs.slides)}")

            try:
                result = improve_slide(slide, image_path, client, dry_run=dry_run)
                result['slide_num'] = i
                result['pass'] = pass_num
                all_results.append(result)

                if result['applied']:
                    logger.info(f"  Applied improvements to: {result['title']}")
                elif dry_run and result['improved']:
                    logger.info(f"  [DRY RUN] Would improve: {result['title']}")
            except Exception as e:
                logger.error(f"Error improving slide {i}: {e}")
                continue

        # Save after each pass
        if not dry_run:
            prs.save(save_path)
            logger.info(f"Saved improved deck to: {save_path}")

    return all_results
```

**Step 4: Run tests**

Run: `venv/bin/python -m pytest tests/test_improve.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add outline2ppt/improve.py tests/test_improve.py
git commit -m "feat: add improve.py with slide rewrite pipeline"
```

---

### Task 8: Add mocked `improve_slide` and `improve_deck` tests

**Files:**
- Modify: `tests/test_improve.py`

**Step 1: Write the tests**

Add to `tests/test_improve.py`:

```python
class TestImproveSlide:
    """Test improve_slide with mocked LLM."""

    def _make_slide_with_content(self):
        prs = Presentation()
        layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(layout)
        # Add title
        if slide.shapes.title:
            slide.shapes.title.text = "Test Title"
        # Add body content via textbox
        tb = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(5), Inches(3))
        tf = tb.text_frame
        tf.paragraphs[0].text = "Original bullet one"
        tf.add_paragraph().text = "Original bullet two"
        return prs, slide

    @patch('outline2ppt.improve.analyze_slide')
    def test_dry_run_does_not_modify(self, mock_analyze):
        from outline2ppt.improve import improve_slide
        mock_analyze.return_value = "## Visual Design\nAdd more detail"
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "- Improved bullet\n- Better bullet"

        _, slide = self._make_slide_with_content()
        result = improve_slide(slide, None, mock_client, dry_run=True)

        assert result['applied'] is False
        assert "Improved bullet" in result['improved']

    @patch('outline2ppt.improve.analyze_slide')
    def test_returns_original_and_improved(self, mock_analyze):
        from outline2ppt.improve import improve_slide
        mock_analyze.return_value = "## Visual Design\nFeedback here"
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "- New content\n- More content"

        _, slide = self._make_slide_with_content()
        result = improve_slide(slide, None, mock_client, dry_run=True)

        assert "Original bullet one" in result['original']
        assert "New content" in result['improved']
        assert result['title'] == "Test Title"


class TestImproveDeck:
    """Test improve_deck orchestration with mocked LLM."""

    @patch('outline2ppt.improve.improve_slide')
    def test_filters_slides(self, mock_improve):
        from outline2ppt.improve import improve_deck
        mock_improve.return_value = {
            'title': 'Test', 'original': '', 'improved': '',
            'feedback': '', 'applied': False
        }
        mock_client = MagicMock()

        # Create a temp pptx with 3 slides
        prs = Presentation()
        for _ in range(3):
            prs.slides.add_slide(prs.slide_layouts[0])
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as f:
            prs.save(f.name)
            tmp_path = f.name

        try:
            improve_deck(tmp_path, slides_filter=[1, 3], dry_run=True, client=mock_client)
            # Should only be called for slides 1 and 3
            assert mock_improve.call_count == 2
        finally:
            os.unlink(tmp_path)
```

**Step 2: Run tests**

Run: `venv/bin/python -m pytest tests/test_improve.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_improve.py
git commit -m "test: add mocked improve_slide and improve_deck tests"
```

---

### Task 9: Wire up CLI `cmd_improve` and subcommand

**Files:**
- Modify: `outline2ppt/cli.py` (add cmd_improve function and argparse subcommand)
- Modify: `outline2ppt.py:19` (add 'improve' to subcommands set)

**Step 1: Add `cmd_improve` to `cli.py`**

Add after `cmd_analyze` function (around line 630):

```python
def cmd_improve(args):
    """Improve an existing presentation using LLM analysis and rewrite."""
    from outline2ppt.improve import improve_deck
    from outline2ppt.llm import LLMClient, load_gateway_config
    from outline2ppt.config import get_model_default, ConfigError

    if not os.path.exists(args.deck):
        logger.error(f"File not found: {args.deck}")
        return 1

    # Resolve model
    try:
        model = args.model or get_model_default("improve", fallback="enhance")
    except ConfigError as exc:
        logger.error(str(exc))
        return 1

    # Setup LLM client
    gateway = None
    if args.gateway_config and os.path.exists(args.gateway_config):
        gateway = load_gateway_config(args.gateway_config)
        if gateway:
            logger.info(f"Using gateway config: {args.gateway_config}")

    try:
        client = LLMClient(model=model, api_key=args.api_key, gateway=gateway)
    except (ConfigError, ValueError) as exc:
        logger.error(str(exc))
        return 1

    logger.info(f"Using model: {model} via {client.model_config.provider} API")

    # Auto-detect images directory
    images_dir = getattr(args, 'images_dir', None)
    if not images_dir:
        deck_name = os.path.splitext(os.path.basename(args.deck))[0]
        candidate = os.path.join('images', deck_name)
        if os.path.isdir(candidate):
            images_dir = candidate
            logger.info(f"Auto-detected images directory: {images_dir}")

    # Parse slides filter
    slides_filter = None
    if args.slides:
        slides_filter = [int(s.strip()) for s in args.slides.split(',')]

    results = improve_deck(
        pptx_path=args.deck,
        output_path=args.output,
        images_dir=images_dir,
        slides_filter=slides_filter,
        passes=args.passes,
        dry_run=args.dry_run,
        client=client,
    )

    # Print summary
    applied = sum(1 for r in results if r.get('applied'))
    skipped = sum(1 for r in results if not r.get('applied') and not args.dry_run)

    if args.dry_run:
        print(f"\n[DRY RUN] Would improve {len(results)} slide(s)")
        for r in results:
            if r.get('improved'):
                print(f"\n--- Slide {r.get('slide_num', '?')}: {r['title']} ---")
                print(f"Original:\n{r['original']}\n")
                print(f"Improved:\n{r['improved']}")
    else:
        print(f"\nImproved {applied} slide(s), skipped {skipped}")

    return 0
```

**Step 2: Add argparse subcommand**

In the `build_parser` function (around line 1030, after the ingest subparser), add:

```python
    # improve
    p_improve = sub.add_parser("improve", help="Improve slides using LLM analysis and rewrite")
    p_improve.add_argument("deck", help="PowerPoint file to improve")
    p_improve.add_argument("--output", default=None, help="Save to different file (default: overwrite)")
    p_improve.add_argument("--dry-run", action="store_true", help="Show changes without modifying")
    p_improve.add_argument("--slides", default=None, help="Comma-separated slide numbers to improve")
    p_improve.add_argument("--passes", type=int, default=1, help="Number of improvement passes")
    p_improve.add_argument("--images-dir", default=None, help="Slide images directory")
    p_improve.add_argument("--model", default=None, help="Model for rewrite")
    p_improve.add_argument("--gateway-config", default="gateway.yaml", help="Gateway config path")
    p_improve.add_argument("--api-key", default=None, help="API key")
    p_improve.add_argument("--db", default="slides.db", help="Database path")
```

**Step 3: Add to command dispatch**

In the command dispatch dict (around line 1094), add:

```python
        "improve": cmd_improve,
```

**Step 4: Update `outline2ppt.py` subcommands set**

The subcommands set already has `'ingest'` and `'tags'` from our earlier fix. Add `'improve'`:

```python
        subcommands = {'create', 'reverse', 'catalog', 'search', 'remix', 'analyze', 'export', 'export-images', 'serve', 'models', 'ingest', 'tags', 'improve'}
```

**Step 5: Run tests**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: All pass

**Step 6: Verify CLI help**

Run: `venv/bin/python outline2ppt.py improve --help`
Expected: Shows help with all options

**Step 7: Commit**

```bash
git add outline2ppt/cli.py outline2ppt.py
git commit -m "feat: add improve CLI subcommand"
```

---

### Task 10: Handle `get_model_default` fallback for "improve" operation

**Files:**
- Modify: `outline2ppt/config.py` (check if `get_model_default` supports fallback param)

**Step 1: Check current implementation**

Read `outline2ppt/config.py` to see how `get_model_default` works. If it doesn't support a `fallback` parameter, either:
- Add a `fallback` kwarg that tries another operation name, or
- Just use `get_model_default("enhance")` in `cmd_improve` instead

**Step 2: Implement the simplest approach**

If `get_model_default` doesn't have fallback, change `cmd_improve` to:

```python
    model = args.model or get_model_default("enhance")
```

This is simpler than modifying config.py and means `improve` uses the same model as `enhance` by default. Users can add an `improve` key to `models.yaml` later if they want a different model.

**Step 3: Run tests and commit**

```bash
git add outline2ppt/cli.py
git commit -m "fix: use enhance model default for improve command"
```

---

### Task 11: End-to-end manual test

**Step 1: Run the full pipeline**

```bash
# Generate enhanced deck
venv/bin/python outline2ppt.py create outlines/outline2ppt-overview.md \
  "templates/AMD Powerpoint Template.pptx" \
  output/outline2ppt-overview-enhanced-v5.pptx --enhance

# Ingest (exports images + catalogs)
venv/bin/python outline2ppt.py ingest output/outline2ppt-overview-enhanced-v5.pptx

# Dry run improve to preview changes
venv/bin/python outline2ppt.py improve output/outline2ppt-overview-enhanced-v5.pptx --dry-run

# Improve specific slides
venv/bin/python outline2ppt.py improve output/outline2ppt-overview-enhanced-v5.pptx \
  --slides 1,2,3 --output output/outline2ppt-overview-improved-v5.pptx
```

**Step 2: Verify output**

```bash
# Reverse to markdown to inspect
venv/bin/python outline2ppt.py reverse output/outline2ppt-overview-improved-v5.pptx \
  output/outline2ppt-overview-improved-v5.md
```

Check:
- [ ] Improved slides have more specific, detailed bullet content
- [ ] Font sizes are Pt(22) / Pt(18)
- [ ] Bold lead-ins appear where content has "Keyword: description" patterns
- [ ] Speaker notes contain revision history
- [ ] Non-improved slides are unchanged
- [ ] PPTX opens cleanly in PowerPoint

**Step 3: Run full test suite one final time**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: All pass

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete improve pipeline — generate, analyze, rewrite, apply"
```
