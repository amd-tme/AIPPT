# Enhanced Reverse Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `--enhance` mode to the `reverse` command that uses multimodal LLMs to generate high-quality markdown outlines from PPTX files.

**Architecture:** Extends `convert_pptx_to_outline()` with an optional LLM path that sends each slide's image + extracted text to a vision model, producing structured markdown instead of mechanical text extraction. Reuses existing `LLMClient` and `generate_text_with_image()` from the analyze pipeline.

**Tech Stack:** python-pptx, LLMClient (anthropic/openai SDKs), models.yaml config system

---

### Task 1: Add `reverse` to VALID_OPERATIONS and models.yaml

**Files:**
- Modify: `outline2ppt/config.py:22` (VALID_OPERATIONS set)
- Modify: `models.yaml:74-80` (defaults section)

**Step 1: Write the failing test**

Add to `tests/test_config.py` (or create if needed):

```python
def test_reverse_is_valid_operation():
    from outline2ppt.config import VALID_OPERATIONS
    assert "reverse" in VALID_OPERATIONS
```

**Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_config.py::test_reverse_is_valid_operation -v`
Expected: FAIL — "reverse" not in VALID_OPERATIONS

**Step 3: Add `reverse` to VALID_OPERATIONS**

In `outline2ppt/config.py:22`, change:
```python
VALID_OPERATIONS = {"enhance", "feedback", "notes", "tags", "image", "improve"}
```
to:
```python
VALID_OPERATIONS = {"enhance", "feedback", "notes", "tags", "image", "improve", "reverse"}
```

`reverse` should be optional (not required), same as `improve`. In `config.py:131`, change:
```python
required_ops = VALID_OPERATIONS - {"improve"}
```
to:
```python
required_ops = VALID_OPERATIONS - {"improve", "reverse"}
```

**Step 4: Add `reverse` default to models.yaml**

Append to the `defaults:` section:
```yaml
  reverse: claude-sonnet-4-6
```

**Step 5: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_config.py::test_reverse_is_valid_operation -v`
Expected: PASS

**Step 6: Run full test suite to check nothing broke**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

**Step 7: Commit**

```bash
git add outline2ppt/config.py models.yaml tests/test_config.py
git commit -m "feat(reverse): add reverse operation to model config"
```

---

### Task 2: Add CLI flags for enhanced reverse

**Files:**
- Modify: `outline2ppt/cli.py:1144-1148` (reverse parser)
- Modify: `outline2ppt/cli.py:374-388` (cmd_reverse function)

**Step 1: Write the failing test**

Add to `tests/test_cli.py` (find the existing CLI test file or add a test):

```python
def test_reverse_enhance_flag_exists():
    """Verify --enhance flag is registered on the reverse subcommand."""
    import sys
    from unittest.mock import patch
    from outline2ppt.cli import main

    with patch.object(sys, 'argv', ['outline2ppt', 'reverse', '--help']):
        try:
            main()
        except SystemExit:
            pass
    # If we get here without error, the parser accepted --enhance
```

Actually, a cleaner approach — test that the parser accepts the flags:

```python
def test_reverse_parser_accepts_enhance_flags():
    """Verify --enhance and related flags are registered on reverse."""
    from outline2ppt.cli import main
    import argparse

    # Build the parser directly
    parser = argparse.ArgumentParser()
    # We'll test via cmd_reverse accepting these args
    # Just verify the CLI help text includes --enhance
    import subprocess
    result = subprocess.run(
        [sys.executable, "outline2ppt.py", "reverse", "--help"],
        capture_output=True, text=True
    )
    assert "--enhance" in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_cli.py::test_reverse_parser_accepts_enhance_flags -v`
Expected: FAIL — "--enhance" not in help output

**Step 3: Add CLI flags to reverse parser**

In `outline2ppt/cli.py`, after line 1148 (`--no-notes`), add:

```python
    p_reverse.add_argument("--enhance", action="store_true",
                           help="Use LLM to generate high-quality outline (multimodal)")
    p_reverse.add_argument("--model", default=None,
                           help="Model to use for enhancement (overrides models.yaml)")
    p_reverse.add_argument("--gateway-config", default="gateway.yaml",
                           help="Path to gateway YAML config")
    p_reverse.add_argument("--images-dir",
                           help="Directory with pre-exported slide images (Slide1.PNG, ...)")
```

**Step 4: Update cmd_reverse to pass new args through**

Replace `cmd_reverse` (lines 374-388) with:

```python
def cmd_reverse(args):
    """Convert a PowerPoint back to markdown outline."""
    from outline2ppt.ppt2outline import convert_pptx_to_outline

    if not os.path.exists(args.input):
        logger.error(f"File not found: {args.input}")
        return 1

    output = args.output or os.path.splitext(args.input)[0] + '.md'
    include_notes = not getattr(args, 'no_notes', False)
    enhance = getattr(args, 'enhance', False)

    # Enhanced mode: set up LLM client
    llm_client = None
    if enhance:
        from outline2ppt.llm import LLMClient, load_gateway_config
        from outline2ppt.config import get_model_default, ConfigError

        try:
            model = getattr(args, 'model', None) or get_model_default("reverse")
        except (ConfigError, ValueError) as exc:
            logger.error(str(exc))
            return 1

        gateway = None
        gateway_config_path = getattr(args, 'gateway_config', None)
        if gateway_config_path and os.path.exists(gateway_config_path):
            gateway = load_gateway_config(gateway_config_path)

        try:
            llm_client = LLMClient(model=model, gateway=gateway)
        except (ConfigError, ValueError) as exc:
            logger.error(str(exc))
            return 1

        print(f"Enhanced reverse using model: {model}")

    images_dir = getattr(args, 'images_dir', None)

    success = convert_pptx_to_outline(
        args.input, output, include_notes,
        enhance=enhance, llm_client=llm_client, images_dir=images_dir,
    )

    if success:
        print(f"Converted to: {output}")
    return 0 if success else 1
```

**Step 5: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_cli.py::test_reverse_parser_accepts_enhance_flags -v`
Expected: PASS

**Step 6: Commit**

```bash
git add outline2ppt/cli.py
git commit -m "feat(reverse): add --enhance, --model, --gateway-config, --images-dir CLI flags"
```

---

### Task 3: Define the reverse enhancement system prompt and LLM integration

**Files:**
- Modify: `outline2ppt/ppt2outline.py`
- Test: `tests/test_ppt2outline.py`

**Step 1: Write the failing tests for enhanced reverse**

Add to `tests/test_ppt2outline.py`:

```python
class TestEnhancedReverse:
    """Tests for --enhance LLM-powered outline generation."""

    @pytest.fixture
    def sample_pptx_path(self, tmp_path):
        """Create a minimal PPTX for testing."""
        from pptx import Presentation
        prs = Presentation()
        layout = prs.slide_layouts[0]

        slide1 = prs.slides.add_slide(layout)
        slide1.shapes.title.text = "Architecture Overview"

        slide2 = prs.slides.add_slide(layout)
        slide2.shapes.title.text = "Network Topology"

        path = tmp_path / "test.pptx"
        prs.save(str(path))
        return str(path)

    @pytest.fixture
    def mock_llm_client(self):
        client = MagicMock()
        client.generate_text_with_image.return_value = (
            "## Architecture Overview\n\n"
            "- System uses microservices architecture\n"
            "- Three main components: API, Worker, Database\n"
        )
        client.generate_text.return_value = (
            "## Architecture Overview\n\n"
            "- System uses microservices architecture\n"
            "- Three main components: API, Worker, Database\n"
        )
        return client

    def test_enhance_uses_llm_output(self, sample_pptx_path, tmp_path, mock_llm_client):
        """Enhanced reverse should use LLM-generated outline instead of mechanical extraction."""
        output = str(tmp_path / "output.md")

        # Create fake images directory
        images_dir = str(tmp_path / "images")
        os.makedirs(images_dir)
        # Create a non-trivial fake image for slide 1
        with open(os.path.join(images_dir, "Slide1.PNG"), "wb") as f:
            f.write(b"\x89PNG" + b"\x00" * 10000)  # >5KB to avoid placeholder detection

        result = convert_pptx_to_outline(
            sample_pptx_path, output, include_notes=True,
            enhance=True, llm_client=mock_llm_client, images_dir=images_dir,
        )

        assert result is True
        mock_llm_client.generate_text_with_image.assert_called()
        with open(output) as f:
            content = f.read()
        assert "microservices architecture" in content

    def test_enhance_falls_back_without_images(self, sample_pptx_path, tmp_path, mock_llm_client):
        """When no images dir is provided, enhanced reverse uses text-only LLM."""
        output = str(tmp_path / "output.md")

        result = convert_pptx_to_outline(
            sample_pptx_path, output, include_notes=True,
            enhance=True, llm_client=mock_llm_client, images_dir=None,
        )

        assert result is True
        # Should use text-only generate_text since no images available
        mock_llm_client.generate_text.assert_called()

    def test_enhance_graceful_degradation_on_llm_failure(
        self, sample_pptx_path, tmp_path
    ):
        """If LLM fails for a slide, fall back to mechanical extraction."""
        output = str(tmp_path / "output.md")

        failing_client = MagicMock()
        failing_client.generate_text.side_effect = Exception("API Error")
        failing_client.generate_text_with_image.side_effect = Exception("API Error")

        result = convert_pptx_to_outline(
            sample_pptx_path, output, include_notes=True,
            enhance=True, llm_client=failing_client, images_dir=None,
        )

        assert result is True
        assert os.path.exists(output)
        with open(output) as f:
            content = f.read()
        # Should still have slide titles from mechanical fallback
        assert "Architecture Overview" in content

    def test_enhance_without_client_falls_back_to_mechanical(
        self, sample_pptx_path, tmp_path
    ):
        """If enhance=True but no client, use mechanical extraction."""
        output = str(tmp_path / "output.md")

        result = convert_pptx_to_outline(
            sample_pptx_path, output, include_notes=True,
            enhance=True, llm_client=None, images_dir=None,
        )

        assert result is True
        with open(output) as f:
            content = f.read()
        assert "Architecture Overview" in content

    def test_non_enhanced_unchanged(self, sample_pptx_path, tmp_path):
        """Non-enhanced reverse should work exactly as before."""
        output = str(tmp_path / "output.md")

        result = convert_pptx_to_outline(sample_pptx_path, output)

        assert result is True
        with open(output) as f:
            content = f.read()
        assert "Architecture Overview" in content
```

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_ppt2outline.py::TestEnhancedReverse -v`
Expected: FAIL — `convert_pptx_to_outline()` doesn't accept `enhance` parameter

**Step 3: Implement the enhanced reverse in ppt2outline.py**

Replace the full content of `outline2ppt/ppt2outline.py`:

```python
"""PowerPoint to markdown outline conversion."""
import logging
import os

from pptx import Presentation

logger = logging.getLogger(__name__)

# System prompt for LLM-powered outline generation
REVERSE_SYSTEM_PROMPT = """You are an expert at converting presentation slides into structured markdown outlines.
Given a slide image and its extracted text content, produce a clean markdown outline that:
- Uses the slide title as an H2 heading (## Title)
- Converts bullet points into a hierarchical list with proper indentation
- Describes diagrams, charts, and visual elements as concise bullet points
- Omits decorative text, watermarks, and slide furniture (page numbers, dates, footers)
- Preserves technical accuracy — do not invent content not present on the slide
- Keep descriptions concise: 1-2 sentences per visual element

Return ONLY the markdown outline. Do not include commentary or explanation."""

REVERSE_TEXT_ONLY_SYSTEM_PROMPT = """You are an expert at converting presentation slide content into structured markdown outlines.
Given a slide's extracted text content, produce a clean markdown outline that:
- Uses the slide title as an H2 heading (## Title)
- Converts bullet points into a hierarchical list with proper indentation
- Cleans up duplicated or garbled text from shape extraction
- Omits decorative text, watermarks, and slide furniture (page numbers, dates, footers)
- Preserves technical accuracy — do not invent content not present on the slide

Return ONLY the markdown outline. Do not include commentary or explanation."""


def extract_text_from_shape(shape) -> str:
    """Extract text from a shape, handling various shape types."""
    text = ""

    # If shape has text
    if hasattr(shape, "text") and shape.text:
        text = shape.text.strip()

    # If shape is a group, recursively extract text from its elements
    elif hasattr(shape, "shapes"):
        for subshape in shape.shapes:
            subtext = extract_text_from_shape(subshape)
            if subtext:
                text += subtext + "\n"

    # If shape is a table, extract text from cells
    elif hasattr(shape, "has_table") and shape.has_table:
        table = shape.table
        for row in table.rows:
            row_text = []
            for cell in row.cells:
                if cell.text:
                    row_text.append(cell.text.strip())
            if row_text:
                text += " | ".join(row_text) + "\n"

    return text.strip()


def _resolve_slide_image(slide_number: int, images_dir: str | None) -> str | None:
    """Find the image file for a slide by number.

    Follows the Slide{i}.PNG convention used by analyze and improve.
    Returns the path if found, None otherwise.
    """
    if not images_dir or not os.path.isdir(images_dir):
        return None

    for ext in (".PNG", ".png", ".jpg", ".jpeg"):
        candidate = os.path.join(images_dir, f"Slide{slide_number}{ext}")
        if os.path.exists(candidate):
            return candidate
    return None


def _enhance_slide_with_llm(
    llm_client,
    slide_number: int,
    title: str,
    mechanical_text: str,
    image_path: str | None,
) -> str | None:
    """Send a single slide to the LLM for enhanced outline generation.

    Returns the LLM-generated markdown, or None on failure (caller should
    fall back to mechanical extraction).
    """
    if image_path and os.path.exists(image_path):
        prompt = (
            f"Convert this slide to a markdown outline.\n\n"
            f"Slide title: {title}\n\n"
            f"Extracted text (may be noisy):\n{mechanical_text}"
        )
        try:
            return llm_client.generate_text_with_image(
                prompt=prompt,
                image_path=image_path,
                system_prompt=REVERSE_SYSTEM_PROMPT,
                max_tokens=1000,
                temperature=0.2,
            )
        except Exception as exc:
            logger.warning(
                "LLM image call failed for slide %d: %s — falling back to text-only",
                slide_number, exc,
            )
            # Fall through to text-only below

    # Text-only LLM path
    prompt = (
        f"Convert this slide content to a clean markdown outline.\n\n"
        f"Slide title: {title}\n\n"
        f"Extracted text:\n{mechanical_text}"
    )
    try:
        return llm_client.generate_text(
            prompt=prompt,
            system_prompt=REVERSE_TEXT_ONLY_SYSTEM_PROMPT,
            max_tokens=1000,
            temperature=0.2,
        )
    except Exception as exc:
        logger.warning(
            "LLM text call failed for slide %d: %s — falling back to mechanical extraction",
            slide_number, exc,
        )
        return None


def convert_pptx_to_outline(
    pptx_file: str,
    output_file: str,
    include_notes: bool = True,
    enhance: bool = False,
    llm_client=None,
    images_dir: str | None = None,
) -> bool:
    """Convert PowerPoint file to markdown outline.

    Args:
        pptx_file: Path to the input PowerPoint file
        output_file: Path for the output markdown file
        include_notes: Whether to include slide notes in output
        enhance: Use LLM to generate high-quality outline per slide
        llm_client: LLMClient instance (required when enhance=True)
        images_dir: Directory with slide images (Slide1.PNG, Slide2.PNG, ...)

    Returns:
        True if conversion succeeded, False otherwise
    """
    try:
        presentation = Presentation(pptx_file)

        # Read sections from PowerPoint
        from outline2ppt.sections import read_sections
        ppt_sections = read_sections(presentation)

        # Build slide_id → section_name map
        slide_to_section = {}
        for section in ppt_sections:
            for slide_id in section.slide_ids:
                slide_to_section[slide_id] = section.name

        current_section = None

        with open(output_file, 'w', encoding='utf-8') as f:
            for i, slide in enumerate(presentation.slides, 1):
                # Check if we're entering a new section
                section_name = slide_to_section.get(slide.slide_id)
                if section_name and section_name != current_section:
                    current_section = section_name
                    # Write section header as H1
                    f.write(f"# {section_name}\n\n")

                # Extract slide title
                title = "Untitled Slide"
                if slide.shapes.title and slide.shapes.title.text:
                    title = slide.shapes.title.text.strip()

                # Extract mechanical text content (used as context for LLM
                # or as fallback output)
                content = []
                for shape in slide.shapes:
                    if shape == slide.shapes.title:
                        continue
                    text = extract_text_from_shape(shape)
                    if text:
                        content.append(text)
                mechanical_text = "\n".join(content)

                # --- Enhanced path (LLM) ---
                llm_output = None
                if enhance and llm_client is not None:
                    image_path = _resolve_slide_image(i, images_dir)
                    print(f"  Enhancing slide {i}: {title}")
                    llm_output = _enhance_slide_with_llm(
                        llm_client, i, title, mechanical_text, image_path,
                    )

                if llm_output:
                    # Write LLM-generated outline directly
                    f.write(llm_output.rstrip() + "\n")
                else:
                    # --- Mechanical extraction (original behavior) ---
                    header_level = "##" if ppt_sections else "#"
                    f.write(f"{header_level} {title}\n\n")

                    for text in content:
                        for line in text.split('\n'):
                            if line.strip():
                                if not line.strip().startswith(
                                    ('-', '*', '•', '1.', '2.', '3.')
                                ):
                                    f.write(f"- {line}\n")
                                else:
                                    f.write(f"{line}\n")

                # Include slide notes if requested
                if include_notes and slide.has_notes_slide:
                    notes_text = slide.notes_slide.notes_text_frame.text.strip()
                    if notes_text:
                        f.write("\n*Notes:*\n")
                        for line in notes_text.split('\n'):
                            if line.strip():
                                f.write(f"- {line}\n")

                # Add space between slides
                f.write("\n\n")

        logger.info(f"Successfully converted {pptx_file} to {output_file}")
        return True

    except Exception as e:
        logger.error(f"Error converting {pptx_file}: {str(e)}")
        return False
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_ppt2outline.py -v`
Expected: ALL tests pass (both old and new)

**Step 5: Commit**

```bash
git add outline2ppt/ppt2outline.py tests/test_ppt2outline.py
git commit -m "feat(reverse): implement LLM-enhanced outline generation with graceful fallback"
```

---

### Task 4: Run full test suite and fix any regressions

**Files:**
- All test files

**Step 1: Run full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

**Step 2: If any test fails, fix the issue**

Common things to check:
- `VALID_OPERATIONS` change may affect existing config tests that assert the exact set
- `convert_pptx_to_outline` signature change is backward-compatible (new params have defaults)
- `str | None` type hints require Python 3.10+ — if tests fail on older Python, use `Optional[str]` from typing instead

**Step 3: Commit any fixes**

```bash
git add -u
git commit -m "fix: resolve test regressions from enhanced reverse"
```

---

### Task 5: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add changelog entries**

Under `## [Unreleased]` → `### Added`, append:

```markdown
- Reverse: `--enhance` flag for LLM-powered outline generation using multimodal AI
- Reverse: `--model`, `--gateway-config`, `--images-dir` options for enhanced mode
- Enhanced reverse describes diagrams and visual elements as structured bullet points instead of listing shape labels
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add changelog entries for enhanced reverse feature"
```

---

## Verification Checklist

After all tasks are complete:

1. `venv/bin/python -m pytest tests/ -v` — all tests pass
2. `venv/bin/python outline2ppt.py reverse --help` — shows `--enhance`, `--model`, `--gateway-config`, `--images-dir`
3. `venv/bin/python outline2ppt.py reverse test.pptx output.md` — works unchanged (no regression)
4. Config: `venv/bin/python -c "from outline2ppt.config import VALID_OPERATIONS; print('reverse' in VALID_OPERATIONS)"` — prints `True`
