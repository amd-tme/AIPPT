# Pipeline Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the create/enhance pipeline from `cli.py` into `pipeline.py` + `builder.py`, add audience selector to web UI.

**Architecture:** `PipelineConfig` dataclass holds all configuration. `run_pipeline()` orchestrates parse→plan→enhance→build→save. `build_slide()` handles per-slide creation with a `BuildContext` dataclass. CLI and web UI both construct a `PipelineConfig` and call `run_pipeline()`.

**Tech Stack:** Python 3, python-pptx, FastAPI, dataclasses, pytest

**Spec:** `docs/plans/2026-03-09-pipeline-refactor.md`

---

## Chunk 1: Create pipeline.py and builder.py with Tests

### Task 1: Create `aippt/pipeline.py` with PipelineConfig and PipelineResult

**Files:**
- Create: `aippt/pipeline.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write test for PipelineConfig defaults**

```python
# tests/test_pipeline.py
"""Tests for aippt.pipeline module."""

import pytest
from aippt.pipeline import PipelineConfig, PipelineResult


class TestPipelineConfig:
    def test_required_fields(self):
        config = PipelineConfig(
            outline_text="# Test\n## Slide 1\n- Bullet",
            template_path="template.pptx",
            output_path="output.pptx",
        )
        assert config.outline_text == "# Test\n## Slide 1\n- Bullet"
        assert config.template_path == "template.pptx"
        assert config.output_path == "output.pptx"

    def test_defaults(self):
        config = PipelineConfig(
            outline_text="x", template_path="t.pptx", output_path="o.pptx"
        )
        assert config.enhance is False
        assert config.model is None
        assert config.audience is None
        assert config.show_plan is False
        assert config.no_plan is False
        assert config.gateway_config is None
        assert config.api_key is None
        assert config.api_base is None
        assert config.image_gen == "none"
        assert config.mcp_config == "mcp_servers.json"
        assert config.mcp_server == "txt2img"
        assert config.classification == "internal"
        assert config.outline_path is None
        assert config.progress_callback is None

    def test_all_fields(self):
        cb = lambda step, detail: None
        config = PipelineConfig(
            outline_text="x",
            template_path="t.pptx",
            output_path="o.pptx",
            enhance=True,
            model="claude-sonnet-4-6",
            audience="engineers",
            show_plan=True,
            no_plan=False,
            gateway_config="gateway.yaml",
            api_key="sk-test",
            api_base="https://api.example.com",
            image_gen="mcp",
            mcp_config="mcp.json",
            mcp_server="imgserver",
            classification="external",
            outline_path="outline.md",
            progress_callback=cb,
        )
        assert config.enhance is True
        assert config.model == "claude-sonnet-4-6"
        assert config.audience == "engineers"
        assert config.progress_callback is cb


class TestPipelineResult:
    def test_fields(self):
        result = PipelineResult(
            output_path="out.pptx", slide_count=5, title="Test"
        )
        assert result.output_path == "out.pptx"
        assert result.slide_count == 5
        assert result.title == "Test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aippt.pipeline'`

- [ ] **Step 3: Write PipelineConfig and PipelineResult dataclasses**

```python
# aippt/pipeline.py
"""Presentation creation pipeline — shared by CLI and web UI."""

from dataclasses import dataclass, field
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the presentation creation pipeline."""

    # Required
    outline_text: str
    template_path: str
    output_path: str

    # Enhancement
    enhance: bool = False
    model: Optional[str] = None
    audience: Optional[str] = None
    show_plan: bool = False
    no_plan: bool = False

    # LLM connection
    gateway_config: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None

    # Image generation
    image_gen: str = "none"
    mcp_config: str = "mcp_servers.json"
    mcp_server: str = "txt2img"
    classification: str = "internal"

    # File context
    outline_path: Optional[str] = None

    # Callbacks
    progress_callback: Optional[Callable] = field(default=None, repr=False)


@dataclass
class PipelineResult:
    """Result from a completed pipeline run."""

    output_path: str
    slide_count: int
    title: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: PASS — all 4 tests

- [ ] **Step 5: Commit**

```bash
git add aippt/pipeline.py tests/test_pipeline.py
git commit -m "feat: add PipelineConfig and PipelineResult dataclasses"
```

---

### Task 2: Create `aippt/builder.py` with BuildContext and build_slide

**Files:**
- Create: `aippt/builder.py`
- Create: `tests/test_builder.py`
- Read: `aippt/cli.py:428-614` (source of `_add_slide`)

- [ ] **Step 1: Write tests for BuildContext and build_slide**

```python
# tests/test_builder.py
"""Tests for aippt.builder module."""

import pytest
from unittest.mock import MagicMock, patch
from pptx import Presentation

from aippt.builder import BuildContext, build_slide


class TestBuildContext:
    def test_defaults(self):
        ctx = BuildContext()
        assert ctx.client is None
        assert ctx.image_gen == "none"
        assert ctx.image_dir is None
        assert ctx.model is None
        assert ctx.mcp_manager is None
        assert ctx.mcp_server == "txt2img"
        assert ctx.classification == "internal"
        assert ctx.audience == "mixed"
        assert ctx.audience_source == "default"


class TestBuildSlideContent:
    """Tests for build_slide() CONTENT: extraction and fallback.

    Mirrors existing TestAddSlideEnhancedContent from test_cli.py.
    """

    def _make_prs(self):
        return Presentation()

    def test_uses_enhanced_content_from_suggestions(self):
        """When LLM response contains CONTENT:, slide body uses enhanced text."""
        prs = self._make_prs()
        slide_data = {
            'title': 'Test Title',
            'content': (
                "CONTENT:\n"
                "- Enhanced point one with more detail\n"
                "- Enhanced point two with added context\n"
                "NARRATIVE: This slide covers important points.\n"
                "LAYOUT: bullet\n"
                "VISUALS: Emphasize first point\n"
                "TALKING_POINTS: Additional details"
            ),
            'original_content': ["- Terse point one", "- Terse point two"],
        }
        layout = build_slide(prs, slide_data, BuildContext())
        slide = prs.slides[0]
        body_texts = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip() != "Test Title":
                body_texts.append(shape.text_frame.text)
        body = '\n'.join(body_texts)
        assert 'Enhanced point one' in body
        assert 'Terse point one' not in body

    def test_falls_back_to_original_when_no_content(self):
        """When LLM response lacks CONTENT:, slide body uses original_content."""
        prs = self._make_prs()
        slide_data = {
            'title': 'Test Title',
            'content': (
                "NARRATIVE: This slide covers important points.\n"
                "LAYOUT: bullet\n"
                "VISUALS: Emphasize first point\n"
                "TALKING_POINTS: Additional details"
            ),
            'original_content': ["- Original point one", "- Original point two"],
        }
        layout = build_slide(prs, slide_data, BuildContext())
        slide = prs.slides[0]
        body_texts = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip() != "Test Title":
                body_texts.append(shape.text_frame.text)
        body = '\n'.join(body_texts)
        assert 'Original point one' in body

    def test_non_enhanced_path_uses_content_lines(self):
        """Without original_content (non-enhanced path), slide body uses content_lines."""
        prs = self._make_prs()
        slide_data = {
            'title': 'Test Title',
            'content': "- Plain bullet one\n- Plain bullet two",
        }
        layout = build_slide(prs, slide_data, BuildContext())
        slide = prs.slides[0]
        body_texts = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip() != "Test Title":
                body_texts.append(shape.text_frame.text)
        body = '\n'.join(body_texts)
        assert 'Plain bullet one' in body

    def test_returns_layout_type(self):
        """build_slide returns the layout type string."""
        prs = self._make_prs()
        slide_data = {
            'title': 'Test Title',
            'content': "LAYOUT: bullet\nCONTENT:\n- Bullet",
        }
        layout = build_slide(prs, slide_data, BuildContext())
        assert layout == 'bullet'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_builder.py -v`
Expected: FAIL — `ImportError: cannot import name 'BuildContext' from 'aippt.builder'`

- [ ] **Step 3: Write BuildContext dataclass and build_slide function**

Create `aippt/builder.py` by extracting `_add_slide()` from `aippt/cli.py:428-614`. The function signature changes from 17 positional/keyword args to 3 arguments:

```python
# aippt/builder.py
"""Slide builder — creates individual slides in a presentation."""

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BuildContext:
    """Shared state for slide building across all slides in a deck."""

    client: Optional[object] = None
    image_gen: str = "none"
    image_dir: Optional[str] = None
    model: Optional[str] = None
    mcp_manager: Optional[object] = None
    mcp_server: str = "txt2img"
    classification: str = "internal"
    audience: str = "mixed"
    audience_source: str = "default"


def build_slide(prs, slide_data: dict, context: BuildContext) -> Optional[str]:
    """Build a single slide and add it to the presentation.

    Args:
        prs: python-pptx Presentation object.
        slide_data: Dict with keys:
            - title (str): Slide title.
            - content (str or list): Slide content (may contain LLM sections).
            - original_content (list, optional): Pre-enhancement content for fallback.
            - layout (str, optional): Author LAYOUT: directive override.
            - image (str, optional): Author IMAGE: directive path.
            - slide_num (int, optional): 1-based slide number.
            - _deck_context (dict, optional): Deck plan context for this slide.
            - _narrative_arc (str, optional): Deck narrative arc.
        context: BuildContext with shared configuration.

    Returns:
        The layout type string used (e.g. 'bullet', 'two_column'), or None on failure.
    """
    from aippt.parser import parse_llm_suggestions
    from aippt.layouts import (
        select_slide_layout,
        parse_layout_suggestion,
        apply_layout_content,
    )
    from aippt.enhancer import format_slide_notes

    title = slide_data['title']
    content = slide_data['content']
    original_content = slide_data.get('original_content')
    layout_override = slide_data.get('layout')
    image_path = slide_data.get('image')
    slide_num = slide_data.get('slide_num')
    deck_context = slide_data.get('_deck_context')
    narrative_arc = slide_data.get('_narrative_arc')

    try:
        # Handle content as list or string
        if isinstance(content, str):
            content_lines = content.split('\n')
        else:
            content_lines = content

        # Parse LLM suggestions
        suggestions = parse_llm_suggestions(content_lines)

        # MCP image generation: if LLM emitted IMAGE_PROMPT, generate image
        ai_generated_image = False
        if (context.image_gen == 'mcp'
                and suggestions.get('IMAGE_PROMPT', '').strip()
                and context.mcp_manager):
            import asyncio
            import aippt.images
            coro = aippt.images.generate_mcp_image(
                prompt=suggestions['IMAGE_PROMPT'],
                output_dir=context.image_dir or '.',
                slide_num=slide_num or 0,
                mcp_manager=context.mcp_manager,
                classification=context.classification,
                cache_dir=os.path.expanduser("~/.cache/aippt/mcp-images"),
            )
            try:
                gen_path = asyncio.run(coro)
            except RuntimeError:
                loop = asyncio.get_event_loop()
                gen_path = loop.run_until_complete(coro)
            if gen_path:
                image_path = gen_path
                ai_generated_image = True

        # Author LAYOUT: directive wins over LLM suggestion
        if layout_override:
            layout_info = parse_layout_suggestion(layout_override)
            suggestions['LAYOUT'] = layout_override
        else:
            layout_info = parse_layout_suggestion(suggestions.get('LAYOUT', ''))

        # Remap diagram to bullet when image generation is not available
        if layout_info['type'] == 'diagram' and context.image_gen == 'none' and not image_path:
            logger.info("Diagram layout requested but image gen disabled — adding placeholder")
            layout_info['type'] = 'bullet'
            layout_info['_add_placeholder'] = True
            layout_info['_placeholder_desc'] = suggestions.get('VISUALS', 'Diagram')

        # Select layout — image+text co-display when IMAGE: set without diagram/two_column
        if image_path and layout_info['type'] not in ('diagram', 'two_column'):
            slide_layout = select_slide_layout(prs, 'image_text')
        else:
            slide_layout = select_slide_layout(prs, layout_info['type'])
        slide = prs.slides.add_slide(slide_layout)

        # Set the slide title
        if slide.shapes.title:
            slide.shapes.title.text = title

        # Prefer enhanced CONTENT from LLM suggestions, fall back to original
        enhanced_content = suggestions.get('CONTENT', '').strip()
        if enhanced_content:
            slide_content = enhanced_content
        elif original_content:
            slide_content = '\n'.join(original_content) if isinstance(original_content, list) else original_content
        else:
            slide_content = '\n'.join(content_lines)

        # Apply content based on layout type
        apply_layout_content(
            slide=slide,
            content=slide_content,
            layout_type=layout_info['type'],
            suggestions=suggestions,
            image_dir=context.image_dir,
            slide_num=slide_num,
            client=context.client,
            image_gen=context.image_gen,
            image_path=image_path,
        )

        # Add placeholder image if diagram was requested without image gen
        if layout_info.get('_add_placeholder'):
            from aippt.layouts import apply_placeholder_image
            apply_placeholder_image(slide, layout_info['_placeholder_desc'])

        # Add speaker notes
        full_image_mode = image_path and layout_info['type'] in ('diagram', 'two_column')
        notes_slide = slide.notes_slide
        existing_notes = notes_slide.notes_text_frame.text
        llm_notes = format_slide_notes(suggestions)
        if full_image_mode and existing_notes and existing_notes.strip():
            if llm_notes.strip():
                notes_slide.notes_text_frame.text = llm_notes + "\n\n" + existing_notes
        else:
            notes_slide.notes_text_frame.text = llm_notes

        # Add disclaimer for AI-generated images
        if ai_generated_image:
            from aippt.layouts import add_disclaimer_textbox
            add_disclaimer_textbox(slide)
            disclaimer_note = "[AI-GENERATED] This slide contains AI-generated imagery not approved for external distribution."
            current_notes = notes_slide.notes_text_frame.text
            notes_slide.notes_text_frame.text = disclaimer_note + "\n\n" + current_notes

        # Append image-gen metadata
        if ai_generated_image:
            from aippt.metadata import append_metadata
            append_metadata(
                slide, "image-gen",
                image_prompt=suggestions.get('IMAGE_PROMPT', ''),
                classification=context.classification,
            )

        # Append enhance metadata if model was used
        if context.model:
            from aippt.metadata import append_metadata, content_hash
            original_text = '\n'.join(original_content) if original_content else ''
            directives = {
                'LAYOUT': layout_override,
                'IMAGE': image_path,
            }
            meta_kwargs = dict(
                model=context.model,
                layout_selected=layout_info['type'],
                original_content_hash=content_hash(original_text) if original_text else None,
                directives=directives,
                audience=context.audience,
                audience_source=context.audience_source,
            )
            if deck_context:
                meta_kwargs['deck_plan_role'] = deck_context.get('role', '')
                meta_kwargs['deck_plan_layout'] = deck_context.get('suggested_layout', '')
                meta_kwargs['deck_plan_context'] = deck_context.get('context_hint', '')
            if narrative_arc:
                meta_kwargs['narrative_arc'] = narrative_arc
            append_metadata(slide, "enhance", **meta_kwargs)

        return layout_info['type']

    except Exception as e:
        logger.error(f"Error creating slide: {str(e)}")
        raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_builder.py -v`
Expected: PASS — all 5 tests

- [ ] **Step 5: Commit**

```bash
git add aippt/builder.py tests/test_builder.py
git commit -m "feat: add builder module with BuildContext and build_slide"
```

---

### Task 3: Add run_pipeline to pipeline.py

**Files:**
- Modify: `aippt/pipeline.py`
- Modify: `tests/test_pipeline.py`
- Read: `aippt/cli.py:10-344` (source of `create_deck`)

- [ ] **Step 1: Write test for run_pipeline with mocked LLM**

Add to `tests/test_pipeline.py`:

```python
import os
import tempfile
from unittest.mock import MagicMock, patch
from pptx import Presentation


class TestRunPipeline:
    def _make_template(self, tmp_path):
        path = str(tmp_path / "template.pptx")
        Presentation().save(path)
        return path

    def test_basic_pipeline_no_enhance(self, tmp_path):
        """Non-enhanced pipeline produces slides from markdown."""
        from aippt.pipeline import PipelineConfig, run_pipeline

        template = self._make_template(tmp_path)
        output = str(tmp_path / "output.pptx")

        config = PipelineConfig(
            outline_text="## Slide One\n- Point A\n- Point B\n\n## Slide Two\n- Point C\n",
            template_path=template,
            output_path=output,
        )
        result = run_pipeline(config)

        assert result.slide_count == 2
        assert result.output_path == output
        assert os.path.exists(output)

    def test_pipeline_calls_progress_callback(self, tmp_path):
        """Progress callback is invoked during pipeline execution."""
        from aippt.pipeline import PipelineConfig, run_pipeline

        template = self._make_template(tmp_path)
        output = str(tmp_path / "output.pptx")
        steps = []

        config = PipelineConfig(
            outline_text="## Slide\n- Bullet\n",
            template_path=template,
            output_path=output,
            progress_callback=lambda step, detail: steps.append(step),
        )
        run_pipeline(config)

        assert "parse" in steps
        assert "build" in steps

    def test_pipeline_raises_on_missing_template(self, tmp_path):
        """Pipeline raises FileNotFoundError for missing template."""
        from aippt.pipeline import PipelineConfig, run_pipeline

        config = PipelineConfig(
            outline_text="## Slide\n- Bullet\n",
            template_path=str(tmp_path / "nonexistent.pptx"),
            output_path=str(tmp_path / "output.pptx"),
        )
        with pytest.raises(FileNotFoundError):
            run_pipeline(config)

    def test_pipeline_result_title(self, tmp_path):
        """Pipeline result contains the first slide title."""
        from aippt.pipeline import PipelineConfig, run_pipeline

        template = self._make_template(tmp_path)
        output = str(tmp_path / "output.pptx")

        config = PipelineConfig(
            outline_text="## My Great Slide\n- Content\n",
            template_path=template,
            output_path=output,
        )
        result = run_pipeline(config)
        assert result.title == "My Great Slide"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_pipeline.py::TestRunPipeline -v`
Expected: FAIL — `ImportError: cannot import name 'run_pipeline'`

- [ ] **Step 3: Implement run_pipeline**

Add `run_pipeline()` to `aippt/pipeline.py`. This is the extracted logic from `cli.py:create_deck()` (lines 57-344), refactored to use `PipelineConfig` and `builder.build_slide()`:

```python
def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Run the full presentation creation pipeline.

    Orchestrates: parse → plan → enhance → build → save.

    Args:
        config: PipelineConfig with all pipeline parameters.

    Returns:
        PipelineResult with output path, slide count, and title.

    Raises:
        FileNotFoundError: If template_path does not exist.
        RuntimeError: If generation fails fatally.
    """
    import os
    from pptx import Presentation

    from aippt.parser import parse_outline, parse_frontmatter
    from aippt.llm import LLMClient, load_gateway_config
    from aippt.enhancer import enhance_with_llm
    from aippt.images import setup_image_directory
    from aippt.layouts import (
        select_slide_layout,
        remove_all_slides,
    )
    from aippt.builder import BuildContext, build_slide

    def _notify(step, detail=""):
        logger.info(detail or step)
        if config.progress_callback:
            config.progress_callback(step, detail)

    # Validate template
    if not os.path.exists(config.template_path):
        raise FileNotFoundError(f"Template file not found: {config.template_path}")

    # Extract frontmatter metadata
    frontmatter, outline_text = parse_frontmatter(config.outline_text)

    # Resolve audience: config arg > frontmatter > default
    audience = config.audience
    if audience is not None:
        audience_source = "cli"
    else:
        fm_audience = frontmatter.get('audience', '').lower()
        valid_audiences = {'engineers', 'executives', 'product', 'mixed'}
        if fm_audience in valid_audiences:
            audience = fm_audience
            audience_source = "frontmatter"
        else:
            audience = "mixed"
            audience_source = "default"
    logger.info(f"Target audience: {audience} (source: {audience_source})")

    # Parse the outline text
    _notify("parse", f"Parsing outline ({len(outline_text)} chars)")
    parsed = parse_outline(outline_text)
    slides = parsed['slides']
    sections = parsed['sections']
    total_slides = len(slides)
    logger.info(f"Loaded outline with {total_slides} slides")

    # Resolve IMAGE: directive paths relative to the outline file
    has_images = any('image' in s for s in slides)
    if has_images and not config.outline_path:
        logger.warning(
            "IMAGE: directives found but no outline file path provided; "
            "image resolution skipped"
        )
        for slide_item in slides:
            slide_item.pop('image', None)
    elif config.outline_path:
        from aippt.parser import resolve_image_path
        outline_dir = os.path.dirname(os.path.abspath(config.outline_path))
        for slide_item in slides:
            if 'image' in slide_item:
                resolved = resolve_image_path(slide_item['image'], outline_dir)
                if resolved:
                    slide_item['image'] = resolved
                else:
                    del slide_item['image']

    if sections:
        logger.info(f"Found {len(sections)} sections in outline")

    _notify("parse", f"Parsed outline with {total_slides} slides")

    # Load template
    prs = Presentation(config.template_path)
    slide_count_before = len(prs.slides)
    remove_all_slides(prs)
    if slide_count_before > 0:
        logger.info(f"Removed {slide_count_before} template placeholder slide(s)")
    logger.info(f"Loaded template: {config.template_path}")

    # Create image directory if using image generation
    image_dir = None
    if config.image_gen != 'none':
        image_dir = setup_image_directory(config.output_path)
        logger.info(f"Created image directory: {image_dir}")

    # Create MCP manager for image generation
    mcp_manager = None
    if config.image_gen == 'mcp':
        from aippt.mcp import MCPManager
        try:
            mcp_manager = MCPManager(config.mcp_config)
            if config.mcp_server not in mcp_manager.servers:
                logger.warning(
                    f"MCP server '{config.mcp_server}' not found in config; "
                    "image generation disabled"
                )
                mcp_manager = None
            else:
                logger.info(f"MCP image generation enabled via server: {config.mcp_server}")
        except Exception as e:
            logger.warning(f"Failed to initialize MCP manager: {e}; image generation disabled")
            mcp_manager = None

    # Setup LLM client if needed
    client = None
    resolved_model = config.model
    if config.enhance or config.image_gen != 'none':
        from aippt.config import get_model_default, ConfigError
        try:
            resolved_model = config.model or get_model_default("enhance")
        except ConfigError as exc:
            raise RuntimeError(str(exc)) from exc

        gateway = None
        if config.gateway_config and os.path.exists(config.gateway_config):
            gateway = load_gateway_config(config.gateway_config)
            if gateway:
                logger.info(f"Using gateway config: {config.gateway_config}")

        try:
            client = LLMClient(
                model=resolved_model,
                api_key=config.api_key,
                api_base=config.api_base,
                gateway=gateway,
            )
        except (ConfigError, ValueError) as exc:
            raise RuntimeError(str(exc)) from exc
        logger.info(f"Using model: {resolved_model} via {client.model_config.provider} API")

    # Deck-level narrative planning
    if config.show_plan and config.no_plan:
        logger.warning("--show-plan ignored because --no-plan was specified")
    deck_plan = None
    if config.enhance and not config.no_plan:
        from aippt.enhancer import plan_deck
        _notify("plan", "Planning deck narrative structure...")
        deck_plan = plan_deck(slides, client, audience=audience, image_gen=config.image_gen)
        if deck_plan['slides']:
            logger.info(
                f"Deck plan: {deck_plan['narrative_arc']} arc, "
                f"{len(deck_plan['slides'])} slides planned"
            )
        else:
            logger.warning("Deck planning returned empty plan; enhancing without deck context")
        if config.show_plan and deck_plan['slides']:
            print("\n=== Deck Narrative Plan ===")
            print(f"Narrative arc: {deck_plan['narrative_arc']}")
            print(f"Assessment: {deck_plan['arc_assessment']}")
            print()
            for entry in deck_plan['slides']:
                print(
                    f"  Slide {entry['index'] + 1}: [{entry['role']}] "
                    f"{entry['title']} -> {entry['suggested_layout']}"
                )
                if entry.get('context_hint'):
                    print(f"    Context: {entry['context_hint']}")
                if entry.get('transition_to_next'):
                    print(f"    Transition: {entry['transition_to_next']}")
            print("===========================\n")

    # Enhance slides with LLM if requested
    if config.enhance:
        for i, slide_item in enumerate(slides, 1):
            _notify("enhance", f"Enhancing slide {i}/{len(slides)}: {slide_item['title']}")
            try:
                slide_item['original_content'] = list(slide_item['content'])
                slide_deck_context = None
                if deck_plan and deck_plan.get('slides'):
                    plan_entries = deck_plan['slides']
                    if i - 1 < len(plan_entries):
                        entry = plan_entries[i - 1]
                        slide_deck_context = {
                            'role': entry.get('role', ''),
                            'suggested_layout': entry.get('suggested_layout', ''),
                            'transition_to_next': entry.get('transition_to_next', ''),
                            'context_hint': entry.get('context_hint', ''),
                        }
                enhanced_content = enhance_with_llm(
                    slide_item, client, image_gen=config.image_gen,
                    has_image='image' in slide_item,
                    audience=audience,
                    deck_context=slide_deck_context,
                )
                slide_item['content'] = enhanced_content.split('\n')
                if slide_deck_context:
                    slide_item['_deck_context'] = slide_deck_context
                if deck_plan:
                    slide_item['_narrative_arc'] = deck_plan.get('narrative_arc', '')
            except Exception as e:
                logger.error(f"Error enhancing slide {i}: {str(e)}")
                logger.info("Continuing with original content for this slide")

            # Save after each enhancement
            try:
                prs.save(config.output_path)
                logger.info(f"Progress saved after enhancing slide {i}")
            except Exception as e:
                logger.error(f"Error saving progress after slide {i}: {str(e)}")
        _notify("enhance", f"All {len(slides)} slides enhanced")

    # Build slides
    build_ctx = BuildContext(
        client=client,
        image_gen=config.image_gen,
        image_dir=image_dir,
        model=resolved_model if config.enhance else None,
        mcp_manager=mcp_manager,
        mcp_server=config.mcp_server,
        classification=config.classification,
        audience=audience,
        audience_source=audience_source,
    )

    layout_counts = {}
    for i, slide_item in enumerate(slides, 1):
        _notify("build", f"Creating slide {i}/{len(slides)}: {slide_item['title']}")
        try:
            slide_item['slide_num'] = i
            layout_type = build_slide(prs, slide_item, build_ctx)
            if layout_type:
                layout_counts[layout_type] = layout_counts.get(layout_type, 0) + 1

            try:
                prs.save(config.output_path)
                logger.info(f"Progress saved after creating slide {i}")
            except Exception as e:
                logger.error(f"Error saving progress after slide {i}: {str(e)}")

        except Exception as e:
            logger.error(f"Error creating slide {i}: {str(e)}")
            try:
                prs.save(config.output_path)
                logger.info("Progress saved despite error")
            except Exception as save_error:
                logger.error(f"Error saving progress: {str(save_error)}")
            continue

    _notify("build", f"Built {len(prs.slides)} slides")

    # Log layout distribution
    if layout_counts:
        summary = ", ".join(f"{count} {ltype}" for ltype, count in sorted(layout_counts.items()))
        logger.info(f"Layout mix: {summary}")

    # Add image directory info to presentation notes
    if image_dir and len(prs.slides) > 0:
        try:
            notes_slide = prs.slides[0].notes_slide
            current_notes = notes_slide.notes_text_frame.text
            notes_slide.notes_text_frame.text = f"Image Directory: {image_dir}\n\n{current_notes}"
        except Exception as e:
            logger.error(f"Error adding image directory to notes: {str(e)}")

    # Apply sections from outline structure
    if sections:
        try:
            from aippt.sections import write_sections, Section
            sections_to_write = []
            for section_data in sections:
                slide_ids = [prs.slides[i].slide_id for i in section_data["slide_indices"]]
                sections_to_write.append(Section(name=section_data["name"], slide_ids=slide_ids))
            write_sections(prs, sections_to_write)
            logger.info(f"Applied {len(sections_to_write)} sections to presentation")
        except Exception as e:
            logger.error(f"Error applying sections: {str(e)}")

    # Final save
    try:
        prs.save(config.output_path)
        logger.info(f"PowerPoint presentation completed: {config.output_path}")
    except Exception as e:
        raise RuntimeError(f"Error saving final presentation: {str(e)}") from e

    # Derive title from first slide
    title = slides[0]['title'] if slides else ""

    return PipelineResult(
        output_path=config.output_path,
        slide_count=len(prs.slides),
        title=title,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: PASS — all 8 tests (4 config + 4 pipeline)

- [ ] **Step 5: Commit**

```bash
git add aippt/pipeline.py tests/test_pipeline.py
git commit -m "feat: add run_pipeline orchestrator to pipeline module"
```

---

## Chunk 2: Wire Up CLI and Web UI, Update Existing Tests

### Task 4: Update cli.py to use pipeline module

**Files:**
- Modify: `aippt/cli.py` — Remove `create_deck()` and `_add_slide()`, update `cmd_create()` to use `PipelineConfig`

- [ ] **Step 1: Update `cmd_create()` to use PipelineConfig**

In `aippt/cli.py`, replace the `create_deck()` import and call in `cmd_create()` (lines 398-416):

```python
def cmd_create(args):
    """Create a presentation from a markdown outline."""
    from aippt.layouts import inspect_template
    from aippt.pipeline import PipelineConfig, run_pipeline

    # Validate input files
    if not os.path.exists(args.outline):
        logger.error(f"Outline file not found: {args.outline}")
        return 1

    if not os.path.exists(args.template):
        logger.error(f"Template file not found: {args.template}")
        return 1

    # Analyze template if requested
    if args.analyze_template:
        try:
            template_info = inspect_template(args.template)
            logger.info("Template analysis:")
            logger.info(f"Available layouts: {[l['name'] for l in template_info['layouts']]}")
            logger.info(f"Slide size: {template_info['slide_size']}")
        except Exception as e:
            logger.error(f"Error analyzing template: {str(e)}")

    # Read outline
    with open(args.outline, 'r', encoding='utf-8') as file:
        outline_text = file.read()

    # Apply --test slicing
    if args.test:
        from aippt.parser import parse_outline
        parsed = parse_outline(outline_text)
        all_slides = parsed['slides']
        total_slides = len(all_slides)
        test_slides = min(args.test, total_slides)
        logger.info(f"Test mode: Processing first {test_slides} of {total_slides} slides")

        sliced = all_slides[:test_slides]
        lines = []
        for slide in sliced:
            lines.append(f"## {slide['title']}")
            if 'layout' in slide:
                lines.append(f"LAYOUT: {slide['layout']}")
            if 'image' in slide:
                lines.append(f"IMAGE: {slide['image']}")
            for line in slide['content']:
                lines.append(line)
            lines.append("")
        outline_text = "\n".join(lines)

    try:
        config = PipelineConfig(
            outline_text=outline_text,
            template_path=args.template,
            output_path=args.output,
            enhance=args.enhance,
            model=args.model,
            gateway_config=args.gateway_config,
            api_key=args.api_key,
            api_base=args.api_base,
            image_gen=args.image_gen,
            outline_path=args.outline,
            mcp_config=args.mcp_config,
            classification=args.classification,
            mcp_server=args.mcp_server,
            audience=getattr(args, 'audience', None),
            show_plan=getattr(args, 'show_plan', False),
            no_plan=getattr(args, 'no_plan', False),
        )
        run_pipeline(config)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except RuntimeError as e:
        logger.error(str(e))
        return 1

    logger.info(f"PowerPoint presentation completed: {args.output}")
    return 0
```

- [ ] **Step 2: Remove `create_deck()` function from cli.py (lines 10-344)**

Delete the entire `create_deck()` function. It has been fully replaced by `run_pipeline()` in `pipeline.py`.

- [ ] **Step 3: Remove `_add_slide()` function from cli.py (lines 428-614)**

Delete the entire `_add_slide()` function. It has been fully replaced by `build_slide()` in `builder.py`.

- [ ] **Step 4: Run existing CLI tests to verify nothing is broken**

Run: `venv/bin/python -m pytest tests/test_cli.py -v -k "not TestAddSlide and not test_create_deck"`
Expected: PASS — all non-removed-function tests should still pass (build_parser, cmd_reverse, cmd_ingest, _extract_slide_text, etc.)

- [ ] **Step 5: Commit**

```bash
git add aippt/cli.py
git commit -m "refactor: remove create_deck and _add_slide from cli.py, use pipeline"
```

---

### Task 5: Update test imports across all test files

**Files:**
- Modify: `tests/test_cli.py` — Update `_add_slide` imports and `create_deck` references
- Modify: `tests/test_cli_mcp_image.py` — Update `_add_slide` import
- Modify: `tests/test_enhancer.py` — Update `create_deck` imports
- Modify: `tests/test_integration.py` — Update `create_deck` imports
- Modify: `tests/test_web_routes.py` — Update `create_deck` spy

- [ ] **Step 1: Update `tests/test_cli.py`**

Change the import at line 8-14:
```python
# Old:
from aippt.cli import (
    build_parser,
    cmd_reverse,
    cmd_ingest,
    _add_slide,
    _extract_slide_text,
)

# New:
from aippt.cli import (
    build_parser,
    cmd_reverse,
    cmd_ingest,
    _extract_slide_text,
)
from aippt.builder import build_slide
```

Update `TestAddSlideEnhancedContent` class (line 583+) — change all `_add_slide(prs, "Test Title", content, ...)` calls to `build_slide(prs, slide_data, BuildContext())` pattern:

```python
from aippt.builder import build_slide, BuildContext

class TestAddSlideEnhancedContent:
    """Tests for build_slide() CONTENT: extraction and fallback."""

    def _make_prs(self):
        from pptx import Presentation
        return Presentation()

    def test_uses_enhanced_content_from_suggestions(self):
        prs = self._make_prs()
        slide_data = {
            'title': 'Test Title',
            'content': (
                "CONTENT:\n"
                "- Enhanced point one with more detail\n"
                "- Enhanced point two with added context\n"
                "NARRATIVE: This slide covers important points.\n"
                "LAYOUT: bullet\n"
                "VISUALS: Emphasize first point\n"
                "TALKING_POINTS: Additional details"
            ),
            'original_content': ["- Terse point one", "- Terse point two"],
        }
        layout = build_slide(prs, slide_data, BuildContext())
        slide = prs.slides[0]
        body_texts = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip() != "Test Title":
                body_texts.append(shape.text_frame.text)
        body = '\n'.join(body_texts)
        assert 'Enhanced point one' in body
        assert 'Terse point one' not in body

    def test_falls_back_to_original_when_no_content(self):
        prs = self._make_prs()
        slide_data = {
            'title': 'Test Title',
            'content': (
                "NARRATIVE: This slide covers important points.\n"
                "LAYOUT: bullet\n"
                "VISUALS: Emphasize first point\n"
                "TALKING_POINTS: Additional details"
            ),
            'original_content': ["- Original point one", "- Original point two"],
        }
        layout = build_slide(prs, slide_data, BuildContext())
        slide = prs.slides[0]
        body_texts = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip() != "Test Title":
                body_texts.append(shape.text_frame.text)
        body = '\n'.join(body_texts)
        assert 'Original point one' in body

    def test_non_enhanced_path_uses_content_lines(self):
        prs = self._make_prs()
        slide_data = {
            'title': 'Test Title',
            'content': "- Plain bullet one\n- Plain bullet two",
        }
        layout = build_slide(prs, slide_data, BuildContext())
        slide = prs.slides[0]
        body_texts = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip() != "Test Title":
                body_texts.append(shape.text_frame.text)
        body = '\n'.join(body_texts)
        assert 'Plain bullet one' in body
```

Also update any inline `from aippt.cli import create_deck` calls (lines 539, 562, 574) to `from aippt.pipeline import run_pipeline, PipelineConfig` and adjust the test to construct a PipelineConfig + call run_pipeline.

- [ ] **Step 2: Update `tests/test_cli_mcp_image.py`**

Change line 13:
```python
# Old:
from aippt.cli import _add_slide, build_parser

# New:
from aippt.cli import build_parser
from aippt.builder import build_slide, BuildContext
```

Then update all `_add_slide(prs, ...)` calls in the file to use `build_slide(prs, slide_data, context)` pattern. Each call needs to be converted from keyword args to a `slide_data` dict + `BuildContext`.

For example, a call like:
```python
_add_slide(
    prs, title="Test Slide", content=content,
    image_gen='mcp', mcp_manager=mock_manager,
    image_dir=str(tmp_path), slide_num=1,
    classification="internal",
)
```
becomes:
```python
slide_data = {
    'title': 'Test Slide',
    'content': content,
    'slide_num': 1,
}
ctx = BuildContext(
    image_gen='mcp',
    mcp_manager=mock_manager,
    image_dir=str(tmp_path),
    classification="internal",
)
build_slide(prs, slide_data, ctx)
```

- [ ] **Step 3: Update `tests/test_enhancer.py`**

Change lines 574, 612, 677 from `from aippt.cli import create_deck` to `from aippt.pipeline import run_pipeline, PipelineConfig`.

Each test that calls `create_deck(outline_text=..., template_path=..., output_path=..., enhance=True, ...)` gets updated to construct a `PipelineConfig` and call `run_pipeline(config)`.

- [ ] **Step 4: Update `tests/test_integration.py`**

Change lines 798, 816, 844, 880, 918, 968 from `from aippt.cli import create_deck` to `from aippt.pipeline import run_pipeline, PipelineConfig`.

Each test constructs a `PipelineConfig` and calls `run_pipeline(config)`.

- [ ] **Step 5: Update `tests/test_web_routes.py`**

Change lines 403-411 to spy on `pipeline.run_pipeline` instead of `cli.create_deck`:
```python
# Old:
from aippt import cli as cli_module
original_create = cli_module.create_deck

# New:
from aippt import pipeline as pipeline_module
original_run = pipeline_module.run_pipeline
```

And adjust the spy function to accept a `PipelineConfig` argument.

- [ ] **Step 6: Run full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: PASS — all 406+ tests pass

- [ ] **Step 7: Commit**

```bash
git add tests/
git commit -m "refactor: update all tests to import from pipeline and builder modules"
```

---

### Task 6: Update web routes to use pipeline module + add audience parameter

**Files:**
- Modify: `aippt/web/routes.py:744-895` — Update import and add audience form parameter
- Modify: `aippt/web/static/index.html` — Add audience dropdown

- [ ] **Step 1: Update routes.py**

In `create_deck_stream()` (line 744+):

1. Add `audience` form parameter to the function signature:
```python
async def create_deck_stream(
    request: Request,
    outline_text: str = Form(None),
    outline_file: UploadFile = File(None),
    enhance: bool = Form(True),
    model: str = Form(None),
    audience: str = Form("mixed"),          # NEW
    title: str = Form(None),
    image_files: List[UploadFile] = File(default=[]),
):
```

2. Update the import (line 760):
```python
# Old:
from aippt.cli import create_deck

# New:
from aippt.pipeline import PipelineConfig, run_pipeline
```

3. Update the `_worker()` function (lines 839-858):
```python
def _worker():
    config = PipelineConfig(
        outline_text=md_text,
        template_path=template_path,
        output_path=output_path,
        enhance=enhance,
        model=model,
        audience=audience,
        gateway_config=gateway_config,
        progress_callback=create_progress,
        outline_path=outline_save_path,
    )
    result = run_pipeline(config)
    event_q.put(("progress", {"step": "ingest", "status": "running", "detail": "Cataloging generated deck..."}))
    ingest_result = ingest_deck(
        deck_path=output_path,
        db_path=db_path,
        gateway_config=gateway_config,
        require_images=False,
        progress_callback=ingest_progress,
    )
    return {
        "output_path": result.output_path,
        "slide_count": result.slide_count,
        "title": result.title,
        **ingest_result,
    }
```

- [ ] **Step 2: Add audience dropdown to index.html**

After the model `<select>` at line 485, add an audience selector within the `.create-options` div:

```html
<label>
    Audience:
    <select id="create-audience">
        <option value="mixed" selected>Mixed / General</option>
        <option value="engineers">Engineers</option>
        <option value="executives">Executives</option>
        <option value="product">Product</option>
    </select>
</label>
```

- [ ] **Step 3: Update createDeck() JS to include audience**

After line 1610 (`const model = ...`), add:
```javascript
const audience = document.getElementById('create-audience').value;
```

After line 1628 (`if (model) formData.append('model', model);`), add:
```javascript
if (audience && audience !== 'mixed') formData.append('audience', audience);
```

- [ ] **Step 4: Add audience select to view-only disabled controls**

After line 737 (`document.getElementById('create-model-select').disabled = true;`), add:
```javascript
document.getElementById('create-audience').disabled = true;
```

- [ ] **Step 5: Run web route tests**

Run: `venv/bin/python -m pytest tests/test_web_routes.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: PASS — all tests pass

- [ ] **Step 7: Commit**

```bash
git add aippt/web/routes.py aippt/web/static/index.html
git commit -m "feat: add audience selector to web UI, wire routes to pipeline module"
```

---

## Chunk 3: Final Verification and Cleanup

### Task 7: Full verification pass

**Files:**
- Read: all modified files for consistency check

- [ ] **Step 1: Run full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: PASS — all tests pass, no regressions

- [ ] **Step 2: Verify cli.py no longer contains create_deck or _add_slide**

Run: `grep -n "def create_deck\|def _add_slide" aippt/cli.py`
Expected: No output (functions are gone)

- [ ] **Step 3: Verify pipeline.py and builder.py have no circular imports**

Run: `venv/bin/python -c "from aippt.pipeline import PipelineConfig, run_pipeline; from aippt.builder import BuildContext, build_slide; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Verify web UI works end-to-end (manual)**

Run: `venv/bin/python aippt.py serve --port 8000`
- Open http://localhost:8000
- Verify audience dropdown is visible
- Verify create deck form submits with audience parameter

- [ ] **Step 5: Verify CLI works end-to-end (manual)**

Run: `venv/bin/python aippt.py create --help`
Expected: Should show all create options including `--audience`

- [ ] **Step 6: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final verification and cleanup for pipeline refactor"
```
