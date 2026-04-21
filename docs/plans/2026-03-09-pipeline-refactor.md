# Pipeline Refactor: Shared Create Pipeline & Web UI Parity

**Date:** 2026-03-09
**Status:** Draft

## Problem

`cli.py` is 2079 lines and serves as both CLI entry point and the core create/enhance pipeline. The `create_deck()` function (300 lines, 15+ parameters) and `_add_slide()` (190 lines, 17 parameters) handle parsing, LLM orchestration, layout application, image generation, metadata, and speaker notes all in one file. The web UI in `routes.py` imports `create_deck` from `cli.py` and wraps it in SSE streaming.

While both CLI and web UI share the same core functions today, the coupling to `cli.py` makes it awkward to evolve. The web UI also lacks feature parity — it doesn't expose the `audience` parameter that significantly affects enhancement quality.

## Goals

1. **Extract a pipeline module** — Move the create/enhance flow out of `cli.py` into `pipeline.py` with a typed `PipelineConfig` dataclass
2. **Extract a builder module** — Move `_add_slide()` into `builder.py` with a clean interface
3. **Add audience selector to web UI** — Bring the first and highest-impact CLI option to the web
4. **Update tests** — Adjust imports, add unit tests for new modules

## Non-Goals

- Refactoring `cmd_*` functions (analyze, improve, ingest, etc.) — they stay in `cli.py`
- Adding image-gen, show-plan, or test-mode to the web UI (future work)
- Behavioral parity investigation (shared code path makes this moot)

## Design

### New Module: `aippt/pipeline.py`

Contains the `PipelineConfig` dataclass and `run_pipeline()` function.

```python
from dataclasses import dataclass, field
from typing import Callable, Optional

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
    progress_callback: Optional[Callable] = None


@dataclass
class PipelineResult:
    """Result from a completed pipeline run."""
    output_path: str
    slide_count: int
    title: str
```

**`run_pipeline(config: PipelineConfig) -> PipelineResult`**

This is the extracted `create_deck()`. Orchestrates:

1. Parse frontmatter and outline
2. Resolve image paths
3. Load template, create LLM client, setup image/MCP
4. Deck-level narrative planning (if enhance and not no_plan)
5. Per-slide LLM enhancement loop (if enhance)
6. Per-slide building via `builder.build_slide()`
7. Apply sections, finalize, save

The `_notify()` helper stays internal to `run_pipeline()`.

### New Module: `aippt/builder.py`

Extracts `_add_slide()` from `cli.py`.

```python
@dataclass
class BuildContext:
    """Shared state for slide building."""
    client: Optional[object] = None       # LLMClient instance
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
        prs: python-pptx Presentation object
        slide_data: Parsed slide dict with keys: title, content,
            original_content, layout, image, _deck_context, _narrative_arc
        context: Shared build configuration

    Returns:
        Layout type string used, or None on failure.
    """
```

This replaces the 17-parameter `_add_slide()` with 3 clean arguments. The function body is the same logic — parse suggestions, resolve layout, generate images, apply content, add notes, record metadata.

### Changes to `aippt/cli.py`

- **Remove:** `create_deck()` and `_add_slide()` (moved to pipeline.py and builder.py)
- **Update `cmd_create()`:** Construct `PipelineConfig` from argparse args, call `run_pipeline()`
- **Net reduction:** ~500 lines removed (from 2079 to ~1580)

```python
def cmd_create(args):
    """Create a presentation from a markdown outline."""
    from aippt.pipeline import PipelineConfig, run_pipeline

    # ... validate files, read outline, handle --test ...

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

    result = run_pipeline(config)
    logger.info(f"PowerPoint presentation completed: {result.output_path}")
    return 0
```

### Changes to `aippt/web/routes.py`

- **Update import:** `from aippt.pipeline import PipelineConfig, run_pipeline` (was `from aippt.cli import create_deck`)
- **Add `audience` form parameter** to `create_deck_stream()`
- **Worker constructs `PipelineConfig`** instead of calling `create_deck()` with kwargs

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
    # ... validation ...

    def _worker():
        config = PipelineConfig(
            outline_text=md_text,
            template_path=template_path,
            output_path=output_path,
            enhance=enhance,
            model=model,
            audience=audience,              # NEW
            gateway_config=gateway_config,
            progress_callback=create_progress,
            outline_path=outline_save_path,
        )
        result = run_pipeline(config)
        # ... ingest ...
```

### Changes to `aippt/web/static/index.html`

Add an audience dropdown to the create deck form, next to the existing model selector:

```html
<label for="create-audience">Audience</label>
<select id="create-audience" name="audience">
    <option value="mixed" selected>Mixed / General</option>
    <option value="engineers">Engineers</option>
    <option value="executives">Executives</option>
    <option value="product">Product</option>
</select>
```

The `createDeck()` JS function appends `audience` to the FormData.

### Test Updates

**Import changes (no logic changes):**
- Tests importing `create_deck` from `aippt.cli` → import from `aippt.pipeline`
- Tests calling `_add_slide` → import `build_slide` from `aippt.builder`

**New test files:**
- `tests/test_pipeline.py` — Test `PipelineConfig` construction, `run_pipeline()` orchestration with mocked LLM
- `tests/test_builder.py` — Test `build_slide()` with various slide data and contexts

## File Summary

| File | Action | Description |
|------|--------|-------------|
| `aippt/pipeline.py` | **New** | PipelineConfig, PipelineResult, run_pipeline() |
| `aippt/builder.py` | **New** | BuildContext, build_slide() |
| `aippt/cli.py` | **Edit** | Remove create_deck + _add_slide, update cmd_create |
| `aippt/web/routes.py` | **Edit** | Update imports, add audience param |
| `aippt/web/static/index.html` | **Edit** | Add audience dropdown to create form |
| `tests/test_pipeline.py` | **New** | Pipeline orchestration tests |
| `tests/test_builder.py` | **New** | Slide builder tests |
| `tests/` (existing) | **Edit** | Update imports where needed |

## Risk Assessment

- **Low risk:** This is a structural refactor — no behavioral changes to the pipeline logic itself
- **Test coverage:** 406 existing tests verify behavior; import updates keep them working
- **Rollback:** Single feature branch, easy to revert
- **Migration:** Clean break (no deprecated wrappers), but only one consumer to update (routes.py)
