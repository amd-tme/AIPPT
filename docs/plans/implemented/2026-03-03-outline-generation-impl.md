# Outline Generation Web UI — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable web UI users to create PowerPoint presentations from markdown outlines, with optional LLM enhancement, and auto-ingest into the catalog.

**Architecture:** Extract `create_deck()` from `cmd_create()` as a reusable function with progress callbacks. Add template config (`templates.yaml`) mirroring the model config pattern. Add SSE endpoint and UI panel following the upload-stream pattern.

**Tech Stack:** Python/FastAPI (backend), htmx + Pico CSS (frontend), SQLite (catalog), python-pptx (PPTX generation)

---

### Task 1: Add template config helpers to `config.py`

**Files:**
- Modify: `outline2ppt/config.py`
- Test: `tests/test_config.py`

**Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
from outline2ppt.config import (
    load_template_config,
    get_template_default,
    set_template_default,
    TemplateConfigError,
)


class TestLoadTemplateConfig:
    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(TemplateConfigError, match="not found"):
            load_template_config(str(tmp_path / "nope.yaml"))

    def test_raises_on_invalid_yaml(self, tmp_path):
        p = tmp_path / "templates.yaml"
        p.write_text("{{bad")
        with pytest.raises(TemplateConfigError, match="parse"):
            load_template_config(str(p))

    def test_raises_when_default_template_missing(self, tmp_path):
        p = tmp_path / "templates.yaml"
        p.write_text("foo: bar\n")
        with pytest.raises(TemplateConfigError, match="default_template"):
            load_template_config(str(p))

    def test_loads_valid_config(self, tmp_path):
        p = tmp_path / "templates.yaml"
        p.write_text("default_template: templates/corp.pptx\n")
        result = load_template_config(str(p))
        assert result["default_template"] == "templates/corp.pptx"
        assert result["source"] == str(p)


class TestGetTemplateDefault:
    def test_returns_configured_value(self, tmp_path):
        p = tmp_path / "templates.yaml"
        p.write_text("default_template: my/template.pptx\n")
        assert get_template_default(str(p)) == "my/template.pptx"

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(TemplateConfigError):
            get_template_default(str(tmp_path / "nope.yaml"))


class TestSetTemplateDefault:
    def test_creates_file_if_missing(self, tmp_path):
        p = tmp_path / "templates.yaml"
        set_template_default("new/path.pptx", str(p))
        assert p.exists()
        result = load_template_config(str(p))
        assert result["default_template"] == "new/path.pptx"

    def test_updates_existing_file(self, tmp_path):
        p = tmp_path / "templates.yaml"
        p.write_text("default_template: old.pptx\n")
        set_template_default("new.pptx", str(p))
        result = load_template_config(str(p))
        assert result["default_template"] == "new.pptx"

    def test_raises_on_empty_path(self, tmp_path):
        with pytest.raises(ValueError, match="non-empty"):
            set_template_default("", str(tmp_path / "templates.yaml"))
```

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_config.py::TestLoadTemplateConfig tests/test_config.py::TestGetTemplateDefault tests/test_config.py::TestSetTemplateDefault -v`
Expected: FAIL — `ImportError: cannot import name 'load_template_config'`

**Step 3: Implement template config helpers**

Add to end of `outline2ppt/config.py`:

```python
# --- Template configuration ---

DEFAULT_TEMPLATE_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates.yaml")


class TemplateConfigError(Exception):
    """Raised when templates.yaml is missing, invalid, or fails validation."""


def load_template_config(config_path: Optional[str] = None) -> Dict:
    """Load template configuration from templates.yaml.

    Returns a dict with:
      ``default_template`` -- path to the default PPTX template
      ``source``           -- path to the loaded file

    Raises:
      TemplateConfigError -- if file is missing, unparseable, or invalid
    """
    if not HAS_YAML:
        raise TemplateConfigError(
            "PyYAML is not installed. Install it with: pip install pyyaml"
        )

    path = config_path or DEFAULT_TEMPLATE_CONFIG_PATH
    p = Path(path)

    if not p.exists():
        raise TemplateConfigError(f"templates.yaml not found at '{path}'.")

    try:
        with p.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:
        raise TemplateConfigError(f"Failed to parse {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise TemplateConfigError(f"{path} is not a valid YAML mapping.")

    if "default_template" not in data:
        raise TemplateConfigError(
            f"{path} is missing the 'default_template' key."
        )

    value = data["default_template"]
    if not isinstance(value, str) or not value.strip():
        raise TemplateConfigError(
            f"{path} 'default_template' must be a non-empty string."
        )

    return {"default_template": value, "source": str(p)}


def get_template_default(config_path: Optional[str] = None) -> str:
    """Return the configured default template path.

    Raises TemplateConfigError if templates.yaml is missing or invalid.
    """
    return load_template_config(config_path)["default_template"]


def set_template_default(template_path: str, config_path: Optional[str] = None) -> None:
    """Write the default template path to templates.yaml.

    Creates the file if it doesn't exist.

    Raises ValueError if template_path is empty.
    """
    if not HAS_YAML:
        raise RuntimeError("PyYAML is required to save template configuration.")

    if not template_path or not template_path.strip():
        raise ValueError("Template path must be a non-empty string.")

    path = config_path or DEFAULT_TEMPLATE_CONFIG_PATH
    p = Path(path)

    data = {}
    if p.exists():
        try:
            with p.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            data = {}

    data["default_template"] = template_path

    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False)

    logger.info("Template configuration saved to %s", path)
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_config.py::TestLoadTemplateConfig tests/test_config.py::TestGetTemplateDefault tests/test_config.py::TestSetTemplateDefault -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add outline2ppt/config.py tests/test_config.py
git commit -m "feat: add template config helpers (templates.yaml)"
```

---

### Task 2: Extract `create_deck()` from `cmd_create()`

**Files:**
- Modify: `outline2ppt/cli.py`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
from unittest.mock import patch, MagicMock
from outline2ppt.cli import create_deck


class TestCreateDeck:
    """Tests for the reusable create_deck() function."""

    def test_returns_result_dict_without_enhance(self, tmp_path):
        """create_deck with enhance=False should parse and build slides."""
        # Write a small outline
        outline = "# Test Deck\n## Slide 1: Intro\n- Point one\n- Point two\n"
        template_path = str(tmp_path / "template.pptx")
        output_path = str(tmp_path / "output.pptx")

        # Create a minimal template
        from pptx import Presentation
        prs = Presentation()
        prs.save(template_path)

        result = create_deck(
            outline_text=outline,
            template_path=template_path,
            output_path=output_path,
            enhance=False,
        )

        assert result["slide_count"] >= 1
        assert result["output_path"] == output_path
        assert os.path.exists(output_path)

    def test_calls_progress_callback(self, tmp_path):
        """create_deck should report progress via callback."""
        outline = "# Test\n## Slide 1: Hello\n- World\n"
        template_path = str(tmp_path / "template.pptx")
        output_path = str(tmp_path / "output.pptx")

        from pptx import Presentation
        prs = Presentation()
        prs.save(template_path)

        steps = []
        def on_progress(step, detail=""):
            steps.append(step)

        create_deck(
            outline_text=outline,
            template_path=template_path,
            output_path=output_path,
            enhance=False,
            progress_callback=on_progress,
        )

        assert "parse" in steps
        assert "build" in steps

    def test_raises_on_missing_template(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            create_deck(
                outline_text="# Test\n## S1\n- x",
                template_path=str(tmp_path / "nope.pptx"),
                output_path=str(tmp_path / "out.pptx"),
            )
```

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_cli.py::TestCreateDeck -v`
Expected: FAIL — `ImportError: cannot import name 'create_deck'`

**Step 3: Extract `create_deck()` function**

Add this function to `outline2ppt/cli.py` *before* `cmd_create`. The function extracts the core logic from `cmd_create`, accepting outline text instead of a file path:

```python
def create_deck(
    outline_text,
    template_path,
    output_path,
    enhance=False,
    model=None,
    gateway_config=None,
    api_key=None,
    api_base=None,
    image_gen="none",
    progress_callback=None,
):
    """Create a PPTX from markdown outline text.

    Args:
        outline_text: Raw markdown outline string.
        template_path: Path to the PPTX template file.
        output_path: Where to save the generated PPTX.
        enhance: Enable LLM-powered layout and notes enhancement.
        model: Override model name (defaults to models.yaml enhance default).
        gateway_config: Path to gateway YAML config.
        api_key: API key for LLM provider.
        api_base: Base URL for LLM API.
        image_gen: Image generation mode ('none', 'svg', 'dalle').
        progress_callback: Optional fn(step: str, detail: str) called at each stage.

    Returns:
        dict with keys: output_path, slide_count, title

    Raises:
        FileNotFoundError: If template_path does not exist.
        RuntimeError: If generation fails fatally.
    """
    from pptx import Presentation as PresentationClass

    from outline2ppt.parser import parse_outline, parse_llm_suggestions
    from outline2ppt.llm import LLMClient, load_gateway_config
    from outline2ppt.enhancer import enhance_with_llm
    from outline2ppt.images import setup_image_directory
    from outline2ppt.layouts import (
        select_slide_layout,
        parse_layout_suggestion,
        apply_layout_content,
        inspect_template,
        remove_all_slides,
    )

    def _progress(step, detail=""):
        if progress_callback:
            progress_callback(step, detail)

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template file not found: {template_path}")

    # Parse outline
    _progress("parse", "Parsing outline...")
    parsed = parse_outline(outline_text)
    slides = parsed["slides"]
    sections = parsed["sections"]
    total_slides = len(slides)
    _progress("parse", f"Parsed {total_slides} slides from outline")

    # Derive title from first H1 or first slide title
    title = slides[0]["title"] if slides else "Untitled"

    # Load template
    prs = PresentationClass(template_path)
    slide_count_before = len(prs.slides)
    remove_all_slides(prs)
    if slide_count_before > 0:
        logger.info(f"Removed {slide_count_before} template placeholder slide(s)")

    # Image directory
    image_dir = None
    if image_gen != "none":
        image_dir = setup_image_directory(output_path)

    # Setup LLM client if needed
    client = None
    if enhance or image_gen != "none":
        from outline2ppt.config import get_model_default, ConfigError
        try:
            resolved_model = model or get_model_default("enhance")
        except ConfigError as exc:
            raise RuntimeError(str(exc)) from exc

        gateway = None
        if gateway_config and os.path.exists(gateway_config):
            gateway = load_gateway_config(gateway_config)

        try:
            client = LLMClient(
                model=resolved_model,
                api_key=api_key,
                api_base=api_base,
                gateway=gateway,
            )
        except (ConfigError, ValueError) as exc:
            raise RuntimeError(str(exc)) from exc

    # Enhance slides
    if enhance:
        for i, slide in enumerate(slides, 1):
            try:
                _progress("enhance", f"Enhancing slide {i}/{len(slides)}: {slide['title']}")
                slide["original_content"] = list(slide["content"])
                enhanced_content = enhance_with_llm(slide, client, image_gen=image_gen)
                slide["content"] = enhanced_content.split("\n")
            except Exception as e:
                logger.error(f"Error enhancing slide {i}: {e}")
            # Save progress after each enhancement
            try:
                prs.save(output_path)
            except Exception:
                pass
        _progress("enhance", f"All {len(slides)} slides enhanced")

    # Build slides
    layout_counts = {}
    for i, slide in enumerate(slides, 1):
        try:
            _progress("build", f"Building slide {i}/{len(slides)}: {slide['title']}")
            layout_type = _add_slide(
                prs=prs,
                title=slide["title"],
                content=slide["content"],
                original_content=slide.get("original_content"),
                debug=False,
                image_dir=image_dir,
                slide_num=i,
                client=client,
                image_gen=image_gen,
            )
            if layout_type:
                layout_counts[layout_type] = layout_counts.get(layout_type, 0) + 1
            try:
                prs.save(output_path)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error creating slide {i}: {e}")
            continue
    _progress("build", f"Built {len(slides)} slides")

    # Apply sections
    if sections:
        try:
            from outline2ppt.sections import write_sections, Section
            sections_to_write = []
            for section_data in sections:
                slide_ids = [prs.slides[i].slide_id for i in section_data["slide_indices"]]
                sections_to_write.append(Section(name=section_data["name"], slide_ids=slide_ids))
            write_sections(prs, sections_to_write)
        except Exception as e:
            logger.error(f"Error applying sections: {e}")

    # Final save
    prs.save(output_path)

    return {
        "output_path": output_path,
        "slide_count": len(prs.slides),
        "title": title,
    }
```

Then refactor `cmd_create` to call `create_deck`:

In `cmd_create`, after the existing validation and outline reading, replace the body (lines ~49–209) with a call to `create_deck`. Keep file-reading, `--test` slicing, `--analyze-template`, and exit code logic in `cmd_create` as CLI-specific concerns. The key change: `cmd_create` reads the file, then calls `create_deck(outline_text=outline, ...)`.

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_cli.py::TestCreateDeck -v`
Expected: all PASS

**Step 5: Run full test suite to check for regressions**

Run: `venv/bin/python -m pytest tests/ -v --tb=short`
Expected: all existing tests still pass

**Step 6: Commit**

```bash
git add outline2ppt/cli.py tests/test_cli.py
git commit -m "refactor: extract create_deck() from cmd_create for reuse"
```

---

### Task 3: Add template API endpoints to `routes.py`

**Files:**
- Modify: `outline2ppt/web/routes.py`
- Test: `tests/test_web_routes.py`

**Step 1: Write the failing tests**

Add to `tests/test_web_routes.py`:

```python
class TestTemplateEndpoints:
    """GET/PUT /api/templates"""

    def test_get_templates_returns_config(self, client, tmp_path):
        """GET /api/templates returns current template config."""
        # Create a templates.yaml the app can find
        from outline2ppt.config import set_template_default, DEFAULT_TEMPLATE_CONFIG_PATH
        import os
        set_template_default("templates/corp.pptx")
        resp = client.get("/api/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "default_template" in data
        # Clean up
        if os.path.exists(DEFAULT_TEMPLATE_CONFIG_PATH):
            os.unlink(DEFAULT_TEMPLATE_CONFIG_PATH)

    def test_get_templates_returns_503_when_missing(self, client, tmp_path, monkeypatch):
        """GET /api/templates returns 503 when templates.yaml is missing."""
        monkeypatch.setattr(
            "outline2ppt.config.DEFAULT_TEMPLATE_CONFIG_PATH",
            str(tmp_path / "nonexistent.yaml"),
        )
        resp = client.get("/api/templates")
        assert resp.status_code == 503

    def test_put_templates_updates_config(self, client, tmp_path, monkeypatch):
        """PUT /api/templates updates the default template path."""
        config_path = str(tmp_path / "templates.yaml")
        (tmp_path / "templates.yaml").write_text("default_template: old.pptx\n")
        monkeypatch.setattr(
            "outline2ppt.config.DEFAULT_TEMPLATE_CONFIG_PATH", config_path
        )
        resp = client.put(
            "/api/templates",
            json={"default_template": "new/template.pptx"},
        )
        assert resp.status_code == 200
        assert resp.json()["default_template"] == "new/template.pptx"

    def test_put_templates_rejects_empty(self, client):
        """PUT /api/templates rejects empty template path."""
        resp = client.put("/api/templates", json={"default_template": ""})
        assert resp.status_code == 400
```

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_web_routes.py::TestTemplateEndpoints -v`
Expected: FAIL — 404 (endpoints don't exist)

**Step 3: Add template endpoints to `routes.py`**

Add to `outline2ppt/web/routes.py`, after the models endpoints:

```python
# ---------------------------------------------------------------------------
# Template configuration endpoints
# ---------------------------------------------------------------------------


@router.get("/api/templates")
async def get_templates():
    """API: Get current template configuration."""
    from outline2ppt.config import load_template_config, TemplateConfigError
    try:
        config = load_template_config()
        return {
            "default_template": config["default_template"],
            "source": config["source"],
        }
    except TemplateConfigError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)


@router.put("/api/templates")
async def update_templates(request: Request):
    """API: Update the default template path."""
    from outline2ppt.config import set_template_default, load_template_config, TemplateConfigError

    body = await request.json()
    template_path = body.get("default_template", "").strip()

    if not template_path:
        return JSONResponse({"error": "default_template must be a non-empty string"}, status_code=400)

    try:
        set_template_default(template_path)
        config = load_template_config()
        return {
            "default_template": config["default_template"],
            "source": config["source"],
        }
    except (TemplateConfigError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_web_routes.py::TestTemplateEndpoints -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add outline2ppt/web/routes.py tests/test_web_routes.py
git commit -m "feat: add GET/PUT /api/templates endpoints"
```

---

### Task 4: Add `POST /api/decks/create` SSE endpoint

**Files:**
- Modify: `outline2ppt/web/routes.py`
- Test: `tests/test_web_routes.py`

**Step 1: Write the failing test**

Add to `tests/test_web_routes.py`:

```python
class TestCreateDeckEndpoint:
    """POST /api/decks/create SSE endpoint."""

    def test_create_with_outline_text_no_enhance(self, client, tmp_path, monkeypatch):
        """Submit outline text with enhance=false, expect SSE stream ending in complete."""
        # Set up a template
        from pptx import Presentation
        template_path = str(tmp_path / "template.pptx")
        prs = Presentation()
        prs.save(template_path)

        config_path = str(tmp_path / "templates.yaml")
        (tmp_path / "templates.yaml").write_text(f"default_template: {template_path}\n")
        monkeypatch.setattr(
            "outline2ppt.config.DEFAULT_TEMPLATE_CONFIG_PATH", config_path
        )

        resp = client.post(
            "/api/decks/create",
            data={
                "outline_text": "# Test\n## Slide 1: Hello\n- World\n",
                "enhance": "false",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        # Parse SSE events from response body
        body = resp.text
        assert "event: complete" in body

    def test_create_rejects_empty_input(self, client):
        """No outline text and no file should return 400."""
        resp = client.post("/api/decks/create", data={})
        assert resp.status_code == 400

    def test_create_with_md_file_upload(self, client, tmp_path, monkeypatch):
        """Upload a .md file instead of pasting text."""
        from pptx import Presentation
        template_path = str(tmp_path / "template.pptx")
        prs = Presentation()
        prs.save(template_path)

        config_path = str(tmp_path / "templates.yaml")
        (tmp_path / "templates.yaml").write_text(f"default_template: {template_path}\n")
        monkeypatch.setattr(
            "outline2ppt.config.DEFAULT_TEMPLATE_CONFIG_PATH", config_path
        )

        md_content = "# File Test\n## Slide 1: From File\n- Content\n"

        resp = client.post(
            "/api/decks/create",
            data={"enhance": "false"},
            files={"outline_file": ("outline.md", md_content, "text/markdown")},
        )
        assert resp.status_code == 200
        body = resp.text
        assert "event: complete" in body
```

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_web_routes.py::TestCreateDeckEndpoint -v`
Expected: FAIL — 404 or 405

**Step 3: Implement the create endpoint**

Add to `outline2ppt/web/routes.py`:

```python
@router.post('/api/decks/create')
async def create_deck_stream(
    request: Request,
    outline_text: str = Form(None),
    outline_file: UploadFile = File(None),
    enhance: bool = Form(True),
    model: str = Form(None),
    title: str = Form(None),
):
    """API: Create a deck from markdown outline, streaming progress as SSE.

    Accepts either outline_text (pasted markdown) or outline_file (.md upload).
    The generated PPTX is automatically ingested into the catalog.
    """
    import asyncio
    import json
    import queue as _queue

    from outline2ppt.cli import create_deck
    from outline2ppt.ingest import ingest_deck
    from outline2ppt.config import get_template_default, TemplateConfigError

    # --- Validate inputs before entering SSE mode ---
    # Resolve outline text
    md_text = None
    if outline_text and outline_text.strip():
        md_text = outline_text
    elif outline_file and outline_file.filename:
        content = await outline_file.read()
        md_text = content.decode("utf-8")

    if not md_text or not md_text.strip():
        return JSONResponse(
            {"error": "Provide outline text or upload a .md file"},
            status_code=400,
        )

    # Resolve template
    try:
        template_path = get_template_default()
    except TemplateConfigError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)

    if not os.path.exists(template_path):
        return JSONResponse(
            {"error": f"Template not found: {template_path}. Update the path in Settings."},
            status_code=404,
        )

    db_path = request.app.state.db_path
    uploads_dir = request.app.state.uploads_dir
    gateway_config = request.app.state.gateway_config

    # Generate output path
    unique_prefix = uuid.uuid4().hex
    output_path = os.path.join(uploads_dir, f"{unique_prefix}_generated.pptx")

    # Step mapping for SSE
    _STEP_MAP = {
        "parse":    ("parse",   "done"),
        "enhance":  ("enhance", "running"),
        "build":    ("build",   "running"),
    }

    event_q: _queue.Queue = _queue.Queue()

    def progress_callback(step, detail=""):
        if step in _STEP_MAP:
            mapped_step, status = _STEP_MAP[step]
            # If detail says "All" or "Built" or "Parsed", mark done
            if any(detail.startswith(w) for w in ("Parsed", "All", "Built")):
                status = "done"
            event_q.put(("progress", {"step": mapped_step, "status": status, "detail": detail}))

    def ingest_progress(step, detail=""):
        """Progress callback for the ingest phase."""
        ingest_map = {
            "export_images": ("ingest", "running"),
            "export_images_done": ("ingest", "running"),
            "export_images_skipped": ("ingest", "running"),
            "catalog": ("ingest", "running"),
            "catalog_done": ("ingest", "running"),
            "complete": ("ingest", "done"),
        }
        if step in ingest_map:
            mapped_step, status = ingest_map[step]
            event_q.put(("progress", {"step": mapped_step, "status": status, "detail": detail}))

    async def _event_generator():
        loop = asyncio.get_running_loop()

        def _worker():
            # Create deck
            result = create_deck(
                outline_text=md_text,
                template_path=template_path,
                output_path=output_path,
                enhance=enhance,
                model=model,
                gateway_config=gateway_config,
                progress_callback=progress_callback,
            )
            # Ingest into catalog
            event_q.put(("progress", {"step": "ingest", "status": "running", "detail": "Cataloging generated deck..."}))
            ingest_result = ingest_deck(
                deck_path=output_path,
                db_path=db_path,
                gateway_config=gateway_config,
                require_images=False,
                progress_callback=ingest_progress,
            )
            return {**result, **ingest_result}

        future = loop.run_in_executor(None, _worker)

        def _format_sse(event_name, payload):
            return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"

        while not future.done():
            await asyncio.sleep(0)
            while True:
                try:
                    event_name, payload = event_q.get_nowait()
                    yield _format_sse(event_name, payload)
                except _queue.Empty:
                    break

        # Drain remaining
        while True:
            try:
                event_name, payload = event_q.get_nowait()
                yield _format_sse(event_name, payload)
            except _queue.Empty:
                break

        try:
            result = await future
        except Exception as exc:
            yield _format_sse("error", {"detail": str(exc)})
            return

        yield _format_sse("complete", {
            "deck_id": result["deck_id"],
            "deck_name": result["deck_name"],
            "slide_count": result["slide_count"],
            "output_path": result["output_path"],
        })

    return StreamingResponse(_event_generator(), media_type="text/event-stream")
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_web_routes.py::TestCreateDeckEndpoint -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add outline2ppt/web/routes.py tests/test_web_routes.py
git commit -m "feat: add POST /api/decks/create SSE endpoint"
```

---

### Task 5: Add "Create Deck" UI panel to `index.html`

**Files:**
- Modify: `outline2ppt/web/static/index.html`

**Step 1: Add CSS for the create panel**

Add before the closing `</style>` tag (after `.hidden` rule, line 261):

```css
.create-panel {
    border: 1px solid var(--pico-muted-border-color);
    border-radius: var(--pico-border-radius);
    margin-bottom: 1.5rem;
}
.create-panel summary {
    padding: 0.75rem 1rem;
    cursor: pointer;
    font-weight: 600;
    font-size: 0.95rem;
}
.create-panel .panel-body {
    padding: 0 1rem 1rem 1rem;
}
.create-panel textarea {
    font-family: monospace;
    font-size: 0.85rem;
    min-height: 150px;
    resize: vertical;
}
.create-options {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex-wrap: wrap;
    margin: 0.75rem 0;
}
.create-options label {
    margin: 0;
    font-size: 0.85rem;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    cursor: pointer;
}
.create-options select {
    margin: 0;
    padding: 0.3rem 0.5rem;
    font-size: 0.85rem;
    width: auto;
}
```

**Step 2: Add HTML for the create panel**

Insert inside `<section id="deck-list">`, right after the header div (after line 290, before the upload progress div):

```html
<details class="create-panel" id="create-panel">
    <summary>Create Deck from Outline</summary>
    <div class="panel-body">
        <p style="margin-bottom:0.5rem; font-size:0.85rem; color:var(--pico-muted-color);">
            Paste a markdown outline or upload a .md file:
        </p>
        <textarea id="create-outline-text" placeholder="# My Presentation&#10;## Slide 1: Introduction&#10;- Key point one&#10;- Key point two"></textarea>
        <div class="create-options">
            <button class="outline" onclick="document.getElementById('create-md-file').click()" style="width:auto; padding:0.3rem 0.7rem; font-size:0.85rem;">Upload .md</button>
            <input type="file" id="create-md-file" accept=".md,.txt" style="display:none;" onchange="loadMdFile(this)">
            <label>
                <input type="checkbox" id="create-enhance" checked style="margin:0;">
                Enhanced mode
            </label>
            <label>
                Model:
                <select id="create-model-select"></select>
            </label>
            <button id="create-btn" onclick="createDeck()" style="width:auto; margin-left:auto;">Create Presentation</button>
        </div>
        <div id="create-progress" style="display:none;" class="upload-progress">
            <div class="progress-title">Generating presentation...</div>
            <div class="step waiting" id="create-step-parse">
                <span class="step-icon">○</span>
                <span class="step-label">Parse outline</span>
                <span class="step-detail"></span>
            </div>
            <div class="step waiting" id="create-step-enhance" style="display:none;">
                <span class="step-icon">○</span>
                <span class="step-label">Enhance slides</span>
                <span class="step-detail"></span>
            </div>
            <div class="step waiting" id="create-step-build">
                <span class="step-icon">○</span>
                <span class="step-label">Build slides</span>
                <span class="step-detail"></span>
            </div>
            <div class="step waiting" id="create-step-ingest">
                <span class="step-icon">○</span>
                <span class="step-label">Catalog deck</span>
                <span class="step-detail"></span>
            </div>
        </div>
    </div>
</details>
```

**Step 3: Add JavaScript for the create workflow**

Add before the closing `</script>` tag:

```javascript
// --- Create deck from outline ---

async function loadCreateModels() {
    try {
        const resp = await fetch('/api/models/available');
        if (!resp.ok) return;
        const models = await resp.json();
        const select = document.getElementById('create-model-select');
        // Try to get the default enhance model
        let defaultModel = '';
        try {
            const configResp = await fetch('/api/models');
            if (configResp.ok) {
                const config = await configResp.json();
                defaultModel = config.defaults?.enhance || '';
            }
        } catch {}
        select.innerHTML = models.map(m =>
            `<option value="${esc(m.name)}" ${m.name === defaultModel ? 'selected' : ''}>${esc(m.name)}</option>`
        ).join('');
    } catch {}
}

function loadMdFile(input) {
    if (!input.files.length) return;
    const reader = new FileReader();
    reader.onload = function(e) {
        document.getElementById('create-outline-text').value = e.target.result;
        toast('Loaded: ' + input.files[0].name);
    };
    reader.readAsText(input.files[0]);
    input.value = '';
}

async function createDeck() {
    const outlineText = document.getElementById('create-outline-text').value.trim();
    if (!outlineText) {
        toast('Please enter a markdown outline or upload a .md file');
        return;
    }

    const enhance = document.getElementById('create-enhance').checked;
    const model = document.getElementById('create-model-select').value;

    // Disable controls
    const createBtn = document.getElementById('create-btn');
    createBtn.disabled = true;

    // Show progress
    const progressEl = document.getElementById('create-progress');
    const enhanceStep = document.getElementById('create-step-enhance');
    enhanceStep.style.display = enhance ? 'flex' : 'none';
    for (const step of progressEl.querySelectorAll('.step')) {
        step.className = 'step waiting';
        step.querySelector('.step-icon').textContent = '○';
        step.querySelector('.step-detail').textContent = '';
    }
    progressEl.style.display = 'block';

    const formData = new FormData();
    formData.append('outline_text', outlineText);
    formData.append('enhance', enhance.toString());
    if (model) formData.append('model', model);

    try {
        const resp = await fetch('/api/decks/create', {method: 'POST', body: formData});

        if (!resp.ok) {
            let msg = resp.statusText;
            try { const data = await resp.json(); msg = data.error || msg; } catch {}
            toast('Create failed: ' + msg);
            progressEl.style.display = 'none';
            createBtn.disabled = false;
            return;
        }

        // Read SSE stream
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, {stream: true});

            const parts = buffer.split('\n\n');
            buffer = parts.pop();
            for (const part of parts) {
                if (!part.trim()) continue;
                let eventType = 'message';
                let eventData = '';
                for (const line of part.split('\n')) {
                    if (line.startsWith('event: ')) eventType = line.slice(7).trim();
                    else if (line.startsWith('data: ')) eventData = line.slice(6).trim();
                }
                if (!eventData) continue;
                let data;
                try { data = JSON.parse(eventData); } catch { continue; }
                handleCreateEvent(eventType, data);
            }
        }
    } catch (e) {
        toast('Create failed: network error');
    }

    progressEl.style.display = 'none';
    createBtn.disabled = false;
    await showDecks();
}

function handleCreateEvent(eventType, data) {
    if (eventType === 'progress') {
        const stepEl = document.getElementById('create-step-' + data.step);
        if (!stepEl) return;
        stepEl.className = 'step ' + data.status;
        const icon = stepEl.querySelector('.step-icon');
        const detail = stepEl.querySelector('.step-detail');
        if (data.status === 'running') {
            icon.innerHTML = '<div class="spinner-icon"></div>';
        } else if (data.status === 'done') {
            icon.textContent = '✓';
        } else if (data.status === 'error' || data.status === 'skipped') {
            icon.textContent = '✗';
        }
        detail.textContent = data.detail || '';
    } else if (eventType === 'complete') {
        toast(`Created "${data.deck_name}" — ${data.slide_count} slide${data.slide_count !== 1 ? 's' : ''}`);
    } else if (eventType === 'error') {
        toast('Create failed: ' + data.detail);
    }
}
```

**Step 4: Load model list on page init**

In the existing `showDecks()` function at the end, add a call to populate the model selector. Find the line `const resp = await fetch('/api/decks');` (line ~471) and add before it:

```javascript
loadCreateModels();
```

**Step 5: Manual test**

1. Run `venv/bin/python outline2ppt.py serve --port 8000`
2. Open browser → see "Create Deck from Outline" collapsible panel
3. Paste a small outline, click "Create Presentation" with enhance=off
4. Verify progress steps animate and deck appears in list

**Step 6: Commit**

```bash
git add outline2ppt/web/static/index.html
git commit -m "feat: add Create Deck UI panel with SSE progress"
```

---

### Task 6: Add template settings section to Settings view

**Files:**
- Modify: `outline2ppt/web/static/index.html`

**Step 1: Add HTML for template settings**

Insert in the settings-view section, after the model defaults table and before the "Reset All" button (after line ~366). Add right before `<button class="outline" onclick="resetModels()">`:

```html
<hr style="margin-top:2rem;">
<h2>Default Template</h2>
<p id="template-source" style="color:var(--pico-muted-color);"></p>
<div class="grid" style="grid-template-columns: 1fr auto; align-items:end;">
    <label>
        Template path
        <input type="text" id="template-path-input" placeholder="templates/default.pptx" style="margin-bottom:0;">
    </label>
    <button onclick="saveTemplatePath()" style="margin-bottom:0;">Save</button>
</div>
<hr style="margin-top:2rem;">
```

**Step 2: Add JavaScript for template settings**

Add before the closing `</script>` tag:

```javascript
// --- Template settings ---

async function loadTemplateSettings() {
    try {
        const resp = await fetch('/api/templates');
        if (resp.ok) {
            const data = await resp.json();
            document.getElementById('template-path-input').value = data.default_template || '';
            document.getElementById('template-source').textContent = 'Source: ' + (data.source || 'templates.yaml');
        } else {
            document.getElementById('template-path-input').value = '';
            document.getElementById('template-source').textContent = 'templates.yaml not configured';
        }
    } catch {
        document.getElementById('template-source').textContent = 'Error loading template config';
    }
}

async function saveTemplatePath() {
    const path = document.getElementById('template-path-input').value.trim();
    if (!path) { toast('Template path cannot be empty'); return; }
    const resp = await fetch('/api/templates', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({default_template: path}),
    });
    if (resp.ok) {
        toast('Template path saved');
        await loadTemplateSettings();
    } else {
        const data = await resp.json().catch(() => ({}));
        toast('Error: ' + (data.error || 'Failed to save'));
    }
}
```

**Step 3: Load template settings when settings view opens**

In `showSettings()` (line ~678), update the `Promise.all` call to include template loading:

```javascript
await Promise.all([loadSettings(), loadTaxonomyView(), loadTemplateSettings()]);
```

**Step 4: Manual test**

1. Open Settings → see "Default Template" section
2. Enter a template path, click Save
3. Verify path persists on reload

**Step 5: Commit**

```bash
git add outline2ppt/web/static/index.html
git commit -m "feat: add template path settings section in web UI"
```

---

### Task 7: Run full test suite and fix any issues

**Step 1: Run all tests**

Run: `venv/bin/python -m pytest tests/ -v --tb=short`
Expected: all tests pass

**Step 2: Fix any failures**

Address any test failures or regressions.

**Step 3: Commit if any fixes were needed**

```bash
git add -u
git commit -m "fix: address test regressions from outline generation feature"
```

---

### Task 8: Update changelog

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add changelog entry**

Add under the latest `## [Unreleased]` section (or create one):

```markdown
### Added
- Create presentations from markdown outlines in the web UI (paste text or upload .md file)
- Enhanced mode toggle for LLM-powered layout and speaker notes generation
- Default template configuration via `templates.yaml`
- Template path configurable in Settings view
- Model selector for enhanced mode
- SSE progress streaming during deck generation
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for outline generation feature"
```
