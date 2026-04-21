# Reverse Round-Trip Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the reverse→create round-trip so speaker notes and analysis artifacts don't leak into slide body text.

**Architecture:** Two complementary changes: (1) change `ppt2outline.py` to emit notes as HTML comments instead of `*Notes:*` bullet lists, and (2) add pre-processing to `parse_outline()` in `parser.py` to strip HTML comment blocks and legacy `*Notes:*` sections. Also add `--strip-notes` CLI flag and strip analysis artifacts.

**Tech Stack:** Python, python-pptx, pytest

---

### Task 1: Add parser tests for HTML comment and *Notes:* stripping

**Files:**
- Modify: `tests/test_parser.py` (add new test class at end of file)

**Step 1: Write the failing tests**

Add a new test class `TestParseOutlineNotesStripping` at the end of `tests/test_parser.py`:

```python
class TestParseOutlineNotesStripping:
    """Tests that parse_outline strips notes blocks so they don't become slide content."""

    def test_strips_html_comment_notes(self):
        """HTML comment notes blocks should be removed before parsing."""
        outline = textwrap.dedent("""\
            # Slide One
            - Bullet one
            - Bullet two

            <!-- notes
            Speaker notes here
            Multi-line notes
            -->
        """)
        result = parse_outline(outline)
        assert len(result['slides']) == 1
        # Notes should not appear in content
        content_text = '\n'.join(result['slides'][0]['content'])
        assert 'Speaker notes' not in content_text
        assert '<!-- notes' not in content_text
        assert '-->' not in content_text

    def test_strips_legacy_notes_section(self):
        """Legacy *Notes:* sections should be removed before parsing."""
        outline = textwrap.dedent("""\
            # Slide One
            - Bullet one

            *Notes:*
            - Speaker notes here
            - More notes
        """)
        result = parse_outline(outline)
        assert len(result['slides']) == 1
        content_text = '\n'.join(result['slides'][0]['content'])
        assert 'Speaker notes' not in content_text
        assert '*Notes:*' not in content_text

    def test_strips_notes_between_slides(self):
        """Notes between slides should be stripped without affecting slide content."""
        outline = textwrap.dedent("""\
            # Slide One
            - Bullet one

            <!-- notes
            Notes for slide one
            -->

            # Slide Two
            - Bullet two
        """)
        result = parse_outline(outline)
        assert len(result['slides']) == 2
        content1 = '\n'.join(result['slides'][0]['content'])
        content2 = '\n'.join(result['slides'][1]['content'])
        assert 'Notes for slide one' not in content1
        assert 'Bullet two' in content2

    def test_preserves_regular_html_comments(self):
        """Regular HTML comments (not notes) should be preserved."""
        outline = textwrap.dedent("""\
            # Slide One
            - Bullet one
            <!-- This is a regular comment -->
        """)
        result = parse_outline(outline)
        content_text = '\n'.join(result['slides'][0]['content'])
        assert '<!-- This is a regular comment -->' in content_text

    def test_preserves_content_with_no_notes(self):
        """Outlines without notes should be unchanged."""
        outline = textwrap.dedent("""\
            # Slide One
            - Bullet one
            - Bullet two
        """)
        result = parse_outline(outline)
        assert len(result['slides']) == 1
        content_text = '\n'.join(result['slides'][0]['content'])
        assert 'Bullet one' in content_text
        assert 'Bullet two' in content_text

    def test_h2_mode_strips_notes(self):
        """Notes stripping works in hierarchical (H1 section / H2 slide) mode too."""
        outline = textwrap.dedent("""\
            # Section One

            ## Slide One
            - Bullet one

            <!-- notes
            Speaker notes
            -->

            ## Slide Two
            - Bullet two
        """)
        result = parse_outline(outline)
        assert len(result['slides']) == 2
        content1 = '\n'.join(result['slides'][0]['content'])
        assert 'Speaker notes' not in content1
```

Ensure `import textwrap` is at the top of the test file (add if missing).

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_parser.py::TestParseOutlineNotesStripping -v`
Expected: FAIL — notes content appears in slide content because stripping isn't implemented yet.

---

### Task 2: Implement notes stripping in parse_outline()

**Files:**
- Modify: `outline2ppt/parser.py` (add `_strip_notes_blocks()` function, call it from `parse_outline()`)

**Step 1: Add the `_strip_notes_blocks` helper**

Add this function before `parse_outline()` (after `resolve_image_path()`, around line 75):

```python
def _strip_notes_blocks(text: str) -> str:
    """Remove notes blocks from outline text before parsing.

    Strips two formats:
    1. HTML comment notes: <!-- notes ... -->
    2. Legacy notes: *Notes:* followed by bullet lines
    """
    import re

    # Strip HTML comment notes blocks (<!-- notes ... -->)
    text = re.sub(
        r'<!-- *notes\b.*?-->',
        '',
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Strip legacy *Notes:* sections (italic header + bullet lines until blank line or heading)
    text = re.sub(
        r'^\*Notes:\*\s*\n(?:- .*\n?)*',
        '',
        text,
        flags=re.MULTILINE,
    )

    return text
```

**Step 2: Call it from `parse_outline()`**

In `parse_outline()`, add one line after `lines = outline.split('\n')` — actually, apply the stripping **before** splitting. Change the first line of the function body:

Replace (line 91 of `parser.py`):
```python
    lines = outline.split('\n')
```

With:
```python
    outline = _strip_notes_blocks(outline)
    lines = outline.split('\n')
```

**Step 3: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_parser.py::TestParseOutlineNotesStripping -v`
Expected: All 6 tests PASS.

**Step 4: Run full parser test suite for regressions**

Run: `venv/bin/python -m pytest tests/test_parser.py -v`
Expected: All existing tests still pass.

**Step 5: Commit**

```bash
git add outline2ppt/parser.py tests/test_parser.py
git commit -m "feat(parser): strip notes blocks from outline before parsing

Removes HTML comment notes (<!-- notes ... -->) and legacy *Notes:*
sections so reversed markdown round-trips cleanly through create."
```

---

### Task 3: Add ppt2outline tests for HTML comment notes output and artifact stripping

**Files:**
- Modify: `tests/test_ppt2outline.py` (add new test class at end of file)

**Step 1: Write the failing tests**

Add a new test class `TestNotesFormat` at the end of `tests/test_ppt2outline.py`:

```python
class TestNotesFormat:
    """Tests that reverse outputs notes as HTML comments, not bullet lists."""

    def test_notes_as_html_comments(self, tmp_path):
        """Notes should be emitted as <!-- notes ... --> blocks."""
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "Test Slide"
        # Add notes
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = "Speaker notes here"

        pptx_path = str(tmp_path / "test.pptx")
        md_path = str(tmp_path / "test.md")
        prs.save(pptx_path)

        convert_pptx_to_outline(pptx_path, md_path, include_notes=True)

        content = open(md_path).read()
        assert '<!-- notes' in content
        assert 'Speaker notes here' in content
        assert '-->' in content
        # Must NOT use legacy format
        assert '*Notes:*' not in content

    def test_notes_html_comment_multiline(self, tmp_path):
        """Multi-line notes should all appear inside the HTML comment."""
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "Test Slide"
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = "Line one\nLine two\nLine three"

        pptx_path = str(tmp_path / "test.pptx")
        md_path = str(tmp_path / "test.md")
        prs.save(pptx_path)

        convert_pptx_to_outline(pptx_path, md_path, include_notes=True)

        content = open(md_path).read()
        assert '<!-- notes' in content
        assert 'Line one' in content
        assert 'Line two' in content
        assert 'Line three' in content

    def test_strips_analysis_artifacts(self, tmp_path):
        """Analysis artifacts should be stripped from notes."""
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "Test Slide"
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = (
            "Good speaker notes\n"
            "[Note: analysis based on slide text only — no image was available]\n"
            "More notes"
        )

        pptx_path = str(tmp_path / "test.pptx")
        md_path = str(tmp_path / "test.md")
        prs.save(pptx_path)

        convert_pptx_to_outline(pptx_path, md_path, include_notes=True)

        content = open(md_path).read()
        assert 'Good speaker notes' in content
        assert 'More notes' in content
        assert '[Note: analysis based on slide text only' not in content

    def test_no_notes_flag_omits_notes(self, tmp_path):
        """include_notes=False should still produce no notes at all."""
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "Test Slide"
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = "Speaker notes"

        pptx_path = str(tmp_path / "test.pptx")
        md_path = str(tmp_path / "test.md")
        prs.save(pptx_path)

        convert_pptx_to_outline(pptx_path, md_path, include_notes=False)

        content = open(md_path).read()
        assert '<!-- notes' not in content
        assert 'Speaker notes' not in content
```

Ensure `from pptx import Presentation` is imported (it should already be).

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_ppt2outline.py::TestNotesFormat -v`
Expected: FAIL — notes are still emitted in `*Notes:*` format.

---

### Task 4: Change ppt2outline.py notes output to HTML comments and strip artifacts

**Files:**
- Modify: `outline2ppt/ppt2outline.py` (two places where notes are written, plus artifact stripping)

**Step 1: Create a helper function for notes formatting**

Add this helper function before `convert_pptx_to_outline()` (around line 199):

```python
def _format_notes_as_comment(notes_text: str) -> str:
    """Format speaker notes as an HTML comment block, stripping analysis artifacts."""
    # Strip analysis artifacts
    lines = []
    for line in notes_text.split('\n'):
        if line.strip().startswith('[Note: analysis based on slide text only'):
            continue
        if line.strip():
            lines.append(line)
    if not lines:
        return ''
    return '<!-- notes\n' + '\n'.join(lines) + '\n-->\n'
```

**Step 2: Replace notes output in the LLM-enhanced path**

Replace lines 274-277 (inside the `if llm_output:` block):
```python
                                f.write("\n*Notes:*\n")
                                for line in notes_text.split('\n'):
                                    if line.strip():
                                        f.write(f"- {line}\n")
```

With:
```python
                                comment = _format_notes_as_comment(notes_text)
                                if comment:
                                    f.write("\n" + comment)
```

**Step 3: Replace notes output in the mechanical extraction path**

Replace lines 305-308 (inside the mechanical extraction block):
```python
                        f.write("\n*Notes:*\n")
                        for line in notes_text.split('\n'):
                            if line.strip():
                                f.write(f"- {line}\n")
```

With:
```python
                        comment = _format_notes_as_comment(notes_text)
                        if comment:
                            f.write("\n" + comment)
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_ppt2outline.py::TestNotesFormat -v`
Expected: All 4 tests PASS.

**Step 5: Run full ppt2outline test suite for regressions**

Run: `venv/bin/python -m pytest tests/test_ppt2outline.py -v`
Expected: All existing tests still pass. Check `TestConvertPptxToOutline::test_include_notes_true` — it may need updating since the notes format changed from `*Notes:*` to `<!-- notes`. If it asserts on the old format, update the assertion.

**Step 6: Commit**

```bash
git add outline2ppt/ppt2outline.py tests/test_ppt2outline.py
git commit -m "feat(reverse): emit notes as HTML comments, strip analysis artifacts

Notes output changes from *Notes:* bullet list to <!-- notes ... -->
HTML comments. Analysis artifacts like [Note: analysis based on slide
text only] are stripped from the notes output."
```

---

### Task 5: Add --strip-notes CLI flag

**Files:**
- Modify: `outline2ppt/cli.py` (add argument, pass to function)
- Modify: `tests/test_cli.py` (add test for new flag)

**Step 1: Write the failing test**

Add to the `TestCmdReverse` class in `tests/test_cli.py`:

```python
    def test_reverse_strip_notes(self, tmp_path):
        """--strip-notes should omit notes entirely."""
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "Test"
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = "Hidden notes"

        pptx_path = str(tmp_path / "test.pptx")
        md_path = str(tmp_path / "test.md")
        prs.save(pptx_path)

        args = argparse.Namespace(
            input=pptx_path,
            output=md_path,
            no_notes=False,
            strip_notes=True,
            enhance=False,
            images_dir=None,
        )
        result = cmd_reverse(args)
        assert result == 0

        content = open(md_path).read()
        assert 'Hidden notes' not in content
        assert '<!-- notes' not in content
```

**Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_cli.py::TestCmdReverse::test_reverse_strip_notes -v`
Expected: FAIL — `strip_notes` attribute not expected.

**Step 3: Add the CLI argument**

In `outline2ppt/cli.py`, after line 1235 (`--no-notes` argument), add:

```python
    p_reverse.add_argument("--strip-notes", action="store_true",
                           help="Omit speaker notes entirely from output")
```

**Step 4: Update cmd_reverse to handle the flag**

In `cmd_reverse()` (around line 438), update the `include_notes` logic:

Replace:
```python
    include_notes = not getattr(args, 'no_notes', False)
```

With:
```python
    strip_notes = getattr(args, 'strip_notes', False)
    include_notes = not getattr(args, 'no_notes', False) and not strip_notes
```

**Step 5: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_cli.py::TestCmdReverse::test_reverse_strip_notes -v`
Expected: PASS.

**Step 6: Run full CLI test suite**

Run: `venv/bin/python -m pytest tests/test_cli.py -v`
Expected: All tests pass.

**Step 7: Commit**

```bash
git add outline2ppt/cli.py tests/test_cli.py
git commit -m "feat(reverse): add --strip-notes flag to omit notes entirely"
```

---

### Task 6: Add round-trip integration test

**Files:**
- Modify: `tests/test_integration.py` (add new test class at end of file)

**Step 1: Write the integration test**

Add at the end of `tests/test_integration.py`:

```python
class TestReverseRoundTrip:
    """Test that reverse → create round-trip preserves content without notes leakage."""

    def test_roundtrip_no_notes_leakage(self, tmp_path):
        """Create a deck, reverse it (with notes), create from reversed md — no notes in body."""
        from outline2ppt.ppt2outline import convert_pptx_to_outline
        from outline2ppt.cli import create_deck

        # Step 1: Create a simple deck from outline
        outline = textwrap.dedent("""\
            # Test Slide
            - Bullet one
            - Bullet two
        """)
        outline_path = tmp_path / "original.md"
        outline_path.write_text(outline)

        template_pptx = tmp_path / "template.pptx"
        Presentation().save(str(template_pptx))

        first_pptx = str(tmp_path / "first.pptx")
        create_deck(outline, str(template_pptx), first_pptx, outline_path=str(outline_path))

        # Manually add speaker notes to the first slide
        from pptx import Presentation as PresentationClass
        prs = PresentationClass(first_pptx)
        slide = prs.slides[0]
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = "These are speaker notes that should NOT appear on slides"
        prs.save(first_pptx)

        # Step 2: Reverse the deck to markdown (notes included)
        reversed_md = str(tmp_path / "reversed.md")
        convert_pptx_to_outline(first_pptx, reversed_md, include_notes=True)

        # Verify reversed markdown has notes as HTML comments
        reversed_content = open(reversed_md).read()
        assert '<!-- notes' in reversed_content
        assert '*Notes:*' not in reversed_content

        # Step 3: Create a new deck from the reversed markdown
        second_pptx = str(tmp_path / "second.pptx")
        create_deck(reversed_content, str(template_pptx), second_pptx, outline_path=reversed_md)

        # Step 4: Verify no notes content leaked into slide body
        prs2 = PresentationClass(second_pptx)
        for slide in prs2.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    text = shape.text_frame.text
                    assert 'speaker notes' not in text.lower(), \
                        f"Notes leaked into slide body: {text}"
                    assert 'should NOT appear' not in text

    def test_roundtrip_legacy_notes_stripped(self, tmp_path):
        """Legacy *Notes:* format in markdown should be stripped by create."""
        from outline2ppt.cli import create_deck

        # Simulate old-format reversed markdown with *Notes:* sections
        legacy_md = textwrap.dedent("""\
            # Test Slide
            - Bullet one
            - Bullet two

            *Notes:*
            - Old format speaker notes
            - Should not appear on slide
        """)

        template_pptx = tmp_path / "template.pptx"
        Presentation().save(str(template_pptx))

        output_pptx = str(tmp_path / "output.pptx")
        md_path = tmp_path / "legacy.md"
        md_path.write_text(legacy_md)
        create_deck(legacy_md, str(template_pptx), output_pptx, outline_path=str(md_path))

        from pptx import Presentation as PresentationClass
        prs = PresentationClass(output_pptx)
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    text = shape.text_frame.text
                    assert 'Old format speaker notes' not in text
                    assert '*Notes:*' not in text
```

Ensure `import textwrap` and `from pptx import Presentation` are available at the top of the test file (add if missing).

**Step 2: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_integration.py::TestReverseRoundTrip -v`
Expected: PASS (both parser stripping and notes format changes should make this work).

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add reverse round-trip integration tests

Verifies that create → reverse → create doesn't leak notes into
slide body, and that legacy *Notes:* format is also handled."
```

---

### Task 7: Run full test suite and update changelog

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Run the full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests pass (including any that needed assertion updates in Task 4).

**Step 2: Update the changelog**

Add to `CHANGELOG.md` under `## [Unreleased]`, in a `### Fixed` section (create it if it doesn't exist, place it after the last existing section under Unreleased):

```markdown
### Fixed
- Reverse round-trip: speaker notes no longer leak into slide body when reversed markdown is used with `create`
- Reverse: analysis artifacts (`[Note: analysis based on slide text only...]`) stripped from speaker notes
- Reverse: notes now emitted as HTML comments (`<!-- notes ... -->`) instead of `*Notes:*` bullet lists
- New `--strip-notes` flag on `reverse` command to omit speaker notes entirely
```

**Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for reverse round-trip fix"
```

---

### Task 8: Final verification

**Step 1: Run the full test suite one more time**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests pass.

**Step 2: Verify the changes look correct**

Run: `git log --oneline -5`
Expected: 4-5 commits for this feature branch.

---

## Summary of All Changes

| File | Change |
|------|--------|
| `outline2ppt/parser.py` | Add `_strip_notes_blocks()`, call it from `parse_outline()` |
| `outline2ppt/ppt2outline.py` | Add `_format_notes_as_comment()`, change notes output from `*Notes:*` to `<!-- notes -->`, strip analysis artifacts |
| `outline2ppt/cli.py` | Add `--strip-notes` argument to reverse command |
| `tests/test_parser.py` | Add `TestParseOutlineNotesStripping` class (6 tests) |
| `tests/test_ppt2outline.py` | Add `TestNotesFormat` class (4 tests) |
| `tests/test_cli.py` | Add `test_reverse_strip_notes` test |
| `tests/test_integration.py` | Add `TestReverseRoundTrip` class (2 tests) |
| `CHANGELOG.md` | Add Fixed section with round-trip fix entries |
