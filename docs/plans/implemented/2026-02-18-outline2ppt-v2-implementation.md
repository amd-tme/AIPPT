# Outline2PPT v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor Outline2PPT into a modular Python package with catalog, remix, multimodal analysis, and web UI capabilities.

**Architecture:** Modular monolith — a single Python package (`outline2ppt/`) with distinct modules for each concern. SQLite for the slide catalog. FastAPI + htmx for the web UI. Corporate LLM gateway support via YAML config with custom auth headers.

**Tech Stack:** Python 3.10+, python-pptx, SQLite (stdlib), FastAPI, htmx, Pico CSS, PyYAML, pytest

---

## Progress Tracker

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 1. Package structure + parser | DONE | `6f3a798` | Reviewed, approved. 20 tests passing. |
| 2. LLM client + gateway | DONE | `610136b` | All issues resolved, gateway tested. |
| 3. Layouts, enhancer, images | DONE | `454a742` | 41 new tests, all passing. |
| 4. ppt2outline + unified CLI | DONE | `38ddfe3` | CLI with 8 subcommands, legacy compat. 27 new tests. |
| 5. SQLite schema + catalog | DONE | `eb90fe9` | schema.sql + catalog.py, 26 tests. |
| 6. Catalog CLI command | DONE | `eb90fe9` | Wired up in same commit. |
| 7. Analyze module | DONE | `33c0802` | feedback, notes, tags modes. 23 tests. |
| 8. Analyze CLI command | DONE | `33c0802` | Wired up in same commit. |
| 9. Export module | DONE | — | CSV export with tags, 6 tests. |
| 10. Export CLI command | DONE | — | Wired up in same session. |
| 11. Remix module | DONE | — | Manifest gen/load, slide copy, deck assembly. 13 tests. |
| 12. Search + remix CLI | DONE | — | Wired up in same session. |
| 13. FastAPI web UI | DONE | — | FastAPI + htmx + Pico CSS. Dashboard, slide browser, search, tagging. |
| 14. Requirements + pyproject | DONE | — | Added fastapi, uvicorn, python-multipart. pyproject.toml created. |
| 15. Update CLAUDE.md | DONE | — | Full v2 architecture, all CLI commands documented. |
| 16. Integration test | DONE | — | 5 end-to-end tests covering catalog-search-tag-export-remix. |

### Task 2 Issues (RESOLVED in commit `610136b`)

1. ✅ **`api_key` env-var auto-resolution** — Added `resolve_api_key()` helper, `api_key` now optional
2. ✅ **Configurable image model** — Added `image_model` parameter to constructor and `generate_image()`
3. ✅ **FileNotFoundError guard** — Added explicit check in `generate_text_with_image()`
4. ✅ **Gateway testing** — Validated with AMD LLM Gateway (gpt-4o, claude-sonnet-4)

### Gateway Configuration

Created `gateway.yaml` for AMD LLM Gateway:
- Base URL: `https://llm-api.amd.com`
- Auth header: `Ocp-Apim-Subscription-Key`
- Env var: `AMD_LLM_KEY`
- Providers: OpenAI (`/OpenAI`), Anthropic (`/Anthropic`), Google (`/VertexAI`)

---

## Phase 1: Package Scaffold & Code Extraction

### Task 1: Create package structure and move parsing logic [DONE]

**Files:**
- Create: `outline2ppt/__init__.py`
- Create: `outline2ppt/parser.py`
- Create: `tests/__init__.py`
- Create: `tests/test_parser.py`

**Step 1: Create the package directory and `__init__.py`**

```bash
mkdir -p outline2ppt tests
```

```python
# outline2ppt/__init__.py
"""Outline2PPT — Convert markdown outlines to PowerPoint presentations."""
__version__ = "2.0.0"
```

**Step 2: Extract `parser.py` from `outline2ppt.py`**

Move these functions into `outline2ppt/parser.py`:
- `parse_outline()` (lines 315-331)
- `markdown_to_plain()` (lines 370-401)
- `parse_llm_suggestions()` (lines 403-428)

```python
# outline2ppt/parser.py
"""Markdown outline parsing and text processing."""
import re
from typing import List, Dict


def parse_outline(outline: str) -> List[Dict[str, any]]:
    """Parse a markdown outline into a list of slide dicts.
    Each slide: {'title': str, 'content': [str]}
    H1 headers create slide boundaries.
    """
    slides = []
    current_slide = None
    for line in outline.split('\n'):
        if line.startswith('# '):
            if current_slide:
                slides.append(current_slide)
            current_slide = {'title': line[2:].strip(), 'content': []}
        elif current_slide is not None:
            current_slide['content'].append(line)
    if current_slide:
        slides.append(current_slide)
    return slides


def markdown_to_plain(md_text: str) -> str:
    """Convert markdown to plain text, preserving structure."""
    def replace_bold_italic(match):
        return match.group(2).upper()

    lines = md_text.split('\n')
    plain_lines = []

    for line in lines:
        indent = re.match(r'^\s*', line).group(0)
        content = line.strip()
        content = re.sub(r'^#+\s*(.*)$', r'\1', content)
        content = re.sub(r'(\*\*|__)(.*?)\1', replace_bold_italic, content)
        content = re.sub(r'(\*|_)(.*?)\1', r'\2', content)
        content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)
        content = re.sub(r'`([^`]+)`', r'\1', content)
        content = re.sub(r'^[-*+]\s*', '\u2022 ', content)
        content = re.sub(r'^\d+\.\s*', lambda m: f"{m.group(0).strip()} ", content)
        plain_lines.append(indent + content)

    plain_text = '\n'.join(plain_lines)
    plain_text = re.sub(r'```[\s\S]*?```', lambda m: m.group(0).replace('```', '').strip(), plain_text)
    return plain_text.strip()


def parse_llm_suggestions(content: List[str]) -> Dict[str, str]:
    """Parse LLM enhancement response into sections."""
    sections = {
        'NARRATIVE': '',
        'LAYOUT': '',
        'VISUALS': '',
        'TALKING_POINTS': '',
        'ORIGINAL_CONTENT': ''
    }

    current_section = None
    for line in content:
        for section in sections.keys():
            if line.startswith(f"{section}:"):
                current_section = section
                line = line[len(f"{section}:"):].strip()
                break

        if current_section:
            if line and not any(line.startswith(f"{s}:") for s in sections.keys()):
                sections[current_section] += line + '\n'

    return {k: v.strip() for k, v in sections.items()}
```

**Step 3: Write tests for parser**

```python
# tests/test_parser.py
import pytest
from outline2ppt.parser import parse_outline, markdown_to_plain, parse_llm_suggestions


class TestParseOutline:
    def test_single_slide(self):
        outline = "# Title\n- Point 1\n- Point 2"
        result = parse_outline(outline)
        assert len(result) == 1
        assert result[0]['title'] == 'Title'
        assert '- Point 1' in result[0]['content']

    def test_multiple_slides(self):
        outline = "# Slide 1\nContent 1\n# Slide 2\nContent 2"
        result = parse_outline(outline)
        assert len(result) == 2
        assert result[0]['title'] == 'Slide 1'
        assert result[1]['title'] == 'Slide 2'

    def test_empty_outline(self):
        result = parse_outline("")
        assert result == []

    def test_preserves_indentation(self):
        outline = "# Title\n  - Indented\n    - Nested"
        result = parse_outline(outline)
        assert '  - Indented' in result[0]['content']

    def test_no_headers(self):
        result = parse_outline("Just some text\nNo headers here")
        assert result == []


class TestMarkdownToPlain:
    def test_strips_bold(self):
        result = markdown_to_plain("**bold text**")
        assert result == "BOLD TEXT"

    def test_strips_links(self):
        result = markdown_to_plain("[link](http://example.com)")
        assert result == "link"

    def test_strips_inline_code(self):
        result = markdown_to_plain("`code`")
        assert result == "code"

    def test_converts_bullets(self):
        result = markdown_to_plain("- item")
        assert result.startswith("\u2022")


class TestParseLlmSuggestions:
    def test_parses_sections(self):
        content = [
            "NARRATIVE: A brief story",
            "LAYOUT: bullet",
            "VISUALS: Use icons",
            "TALKING_POINTS: Extra info",
            "ORIGINAL_CONTENT: Original stuff"
        ]
        result = parse_llm_suggestions(content)
        assert result['NARRATIVE'] == 'A brief story'
        assert result['LAYOUT'] == 'bullet'

    def test_empty_content(self):
        result = parse_llm_suggestions([])
        assert result['NARRATIVE'] == ''
        assert result['LAYOUT'] == ''
```

**Step 4: Run tests**

Run: `pytest tests/test_parser.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add outline2ppt/__init__.py outline2ppt/parser.py tests/__init__.py tests/test_parser.py
git commit -m "feat: extract parser module from outline2ppt.py"
```

---

### Task 2: Extract LLM client module [DONE — needs fixes, see outstanding items above]

**Files:**
- Create: `outline2ppt/llm.py`
- Create: `tests/test_llm.py`

**Step 1: Extract `llm.py`**

Move from `outline2ppt.py`:
- `ModelConfig` dataclass (lines 28-35)
- `MODEL_CONFIGS` dict (lines 38-99) — **trimmed down** to models likely available through a corporate gateway
- `LLMClient` class (lines 101-202)

```python
# outline2ppt/llm.py
"""LLM client abstraction for multiple providers and gateway support."""
import logging
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

import anthropic
import openai

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    name: str
    provider: str
    max_tokens: int
    max_input_tokens: int
    supports_vision: bool = False
    supports_images: bool = False


# Trimmed model registry — common models available via corporate gateways
MODEL_CONFIGS = {
    # OpenAI
    "gpt-4o": ModelConfig("gpt-4o", "openai", 128000, 128000, True, True),
    "gpt-4o-mini": ModelConfig("gpt-4o-mini", "openai", 128000, 128000, True, True),
    "gpt-4.1": ModelConfig("gpt-4.1", "openai", 128000, 128000, True, True),
    "o3-mini": ModelConfig("o3-mini", "openai", 128000, 128000, True, False),
    # Anthropic
    "claude-3.5-sonnet": ModelConfig("claude-3.5-sonnet", "anthropic", 200000, 200000, True),
    "claude-3.5-haiku": ModelConfig("claude-3.5-haiku", "anthropic", 200000, 200000, True),
    "claude-3.7-sonnet": ModelConfig("claude-3.7-sonnet", "anthropic", 200000, 200000, True),
    # Google
    "gemini-2.0-flash": ModelConfig("gemini-2.0-flash", "google", 1000000, 1000000, True, True),
    "gemini-2.5-pro": ModelConfig("gemini-2.5-pro", "google", 1000000, 1000000, True, True),
}


@dataclass
class GatewayConfig:
    """Corporate LLM gateway configuration."""
    base_url: str
    auth_header: str
    auth_value: str
    provider_paths: Dict[str, str] = field(default_factory=dict)


def load_gateway_config(config_path: str = "gateway.yaml") -> Optional[GatewayConfig]:
    """Load gateway config from YAML file. Returns None if file doesn't exist."""
    if not os.path.exists(config_path):
        return None

    import yaml
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)

    gw = data.get('gateway', {})
    auth_value_env = gw.get('auth_value_env', '')
    auth_value = os.getenv(auth_value_env, '') if auth_value_env else gw.get('auth_value', '')

    provider_paths = {}
    for name, info in data.get('providers', {}).items():
        provider_paths[name] = info.get('path', '')

    return GatewayConfig(
        base_url=gw.get('base_url', ''),
        auth_header=gw.get('auth_header', ''),
        auth_value=auth_value,
        provider_paths=provider_paths,
    )


def infer_provider(model: str) -> str:
    """Infer provider from model name."""
    if model in MODEL_CONFIGS:
        return MODEL_CONFIGS[model].provider
    m = model.lower()
    if "gpt" in m or "o1" in m or "o3" in m:
        return "openai"
    if "claude" in m:
        return "anthropic"
    if "gemini" in m:
        return "google"
    return "openai"  # default to OpenAI-compatible


class LLMClient:
    """Unified client interface for different LLM providers."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        gateway: Optional[GatewayConfig] = None,
    ):
        self.model = model
        self.model_config = MODEL_CONFIGS.get(model, None)
        self.provider = infer_provider(model)

        if not self.model_config:
            self.model_config = ModelConfig(model, self.provider, 4096, 4096)

        # Build base URL and auth from gateway config if present
        extra_headers = {}
        if gateway:
            provider_path = gateway.provider_paths.get(self.provider, '')
            api_base = f"{gateway.base_url.rstrip('/')}{provider_path}"
            api_key = api_key or gateway.auth_value
            extra_headers = {gateway.auth_header: gateway.auth_value}

        if not api_key:
            env_var = 'ANTHROPIC_API_KEY' if self.provider == 'anthropic' else 'OPENAI_API_KEY'
            api_key = os.getenv(env_var, '')

        self.api_key = api_key

        if self.provider == "anthropic":
            kwargs = {"api_key": api_key}
            if api_base:
                kwargs["base_url"] = api_base
            if extra_headers:
                kwargs["default_headers"] = extra_headers
            self.client = anthropic.Client(**kwargs)
        else:
            kwargs = {"api_key": api_key}
            if api_base:
                kwargs["base_url"] = api_base
            if extra_headers:
                kwargs["default_headers"] = extra_headers
            self.client = openai.Client(**kwargs)

    def generate_text(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Generate text using the appropriate API."""
        try:
            if self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                )
                return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating text: {e}")
            raise

    def generate_text_with_image(
        self,
        prompt: str,
        image_path: str,
        system_prompt: str = "You are a helpful assistant.",
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Generate text from a prompt + image (multimodal)."""
        import base64

        if not self.model_config.supports_vision:
            raise ValueError(f"Model {self.model} does not support vision")

        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        mime = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"

        try:
            if self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": image_data}},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                )
                return response.content[0].text
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": [
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_data}"}},
                            {"type": "text", "text": prompt},
                        ]},
                    ],
                )
                return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating text with image: {e}")
            raise

    def generate_image(self, prompt: str, size: str = "1024x1024") -> str:
        """Generate image using DALL-E or compatible API. Returns image URL."""
        if not self.model_config.supports_images:
            raise ValueError(f"Model {self.model} does not support image generation")

        try:
            response = self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                quality="hd",
                style="natural",
                n=1,
            )
            return response.data[0].url
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            raise
```

**Step 2: Write tests for LLM module**

```python
# tests/test_llm.py
import pytest
from unittest.mock import patch, MagicMock
from outline2ppt.llm import (
    ModelConfig, MODEL_CONFIGS, GatewayConfig,
    load_gateway_config, infer_provider, LLMClient,
)


class TestInferProvider:
    def test_known_model(self):
        assert infer_provider("gpt-4o") == "openai"
        assert infer_provider("claude-3.5-sonnet") == "anthropic"
        assert infer_provider("gemini-2.5-pro") == "google"

    def test_unknown_gpt_model(self):
        assert infer_provider("gpt-5-turbo") == "openai"

    def test_unknown_claude_model(self):
        assert infer_provider("claude-4-opus") == "anthropic"

    def test_default_fallback(self):
        assert infer_provider("some-random-model") == "openai"


class TestGatewayConfig:
    def test_load_missing_file(self):
        result = load_gateway_config("/nonexistent/path.yaml")
        assert result is None

    def test_load_valid_config(self, tmp_path):
        config_file = tmp_path / "gateway.yaml"
        config_file.write_text("""
gateway:
  base_url: "https://gateway.example.com"
  auth_header: "X-Api-Key"
  auth_value: "test-key"
providers:
  openai:
    path: "/openai/v1"
  anthropic:
    path: "/anthropic/v1"
""")
        result = load_gateway_config(str(config_file))
        assert result.base_url == "https://gateway.example.com"
        assert result.auth_header == "X-Api-Key"
        assert result.provider_paths["openai"] == "/openai/v1"


class TestLLMClientInit:
    @patch("outline2ppt.llm.anthropic.Client")
    def test_anthropic_client(self, mock_client):
        client = LLMClient(model="claude-3.5-sonnet", api_key="test-key")
        assert client.provider == "anthropic"
        mock_client.assert_called_once()

    @patch("outline2ppt.llm.openai.Client")
    def test_openai_client(self, mock_client):
        client = LLMClient(model="gpt-4o", api_key="test-key")
        assert client.provider == "openai"
        mock_client.assert_called_once()

    @patch("outline2ppt.llm.openai.Client")
    def test_gateway_sets_base_url_and_headers(self, mock_client):
        gw = GatewayConfig(
            base_url="https://gw.example.com",
            auth_header="X-Key",
            auth_value="secret",
            provider_paths={"openai": "/openai/v1"},
        )
        client = LLMClient(model="gpt-4o", gateway=gw)
        call_kwargs = mock_client.call_args[1]
        assert call_kwargs["base_url"] == "https://gw.example.com/openai/v1"
        assert call_kwargs["default_headers"] == {"X-Key": "secret"}
```

**Step 3: Run tests**

Run: `pytest tests/test_llm.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add outline2ppt/llm.py tests/test_llm.py
git commit -m "feat: extract LLM client with gateway support"
```

---

### Task 3: Extract layout, enhancer, and image modules [BLOCKED — waiting on Task 2 fixes + gateway testing]

**Files:**
- Create: `outline2ppt/layouts.py`
- Create: `outline2ppt/enhancer.py`
- Create: `outline2ppt/images.py`

**Step 1: Extract `layouts.py`**

Move from `outline2ppt.py`:
- `SLIDE_LAYOUTS` dict (lines 204-226)
- `get_layout_index()` (lines 228-233)
- `select_slide_layout()` (lines 235-251)
- `parse_layout_suggestion()` (lines 253-269)
- `split_content_for_columns()` (lines 271-285)
- `apply_layout_content()` (lines 287-313)
- `apply_bullet_layout()` (lines 494-528)
- `apply_two_column_layout()` (lines 478-492)
- `apply_basic_layout()` (lines 649-683)
- `apply_comparison_layout()` (lines 685-724)
- `apply_diagram_layout()` (lines 784-832)
- Helper layout creators (lines 557-611)

Keep all function signatures and behavior identical. Import `LLMClient` from `outline2ppt.llm`.

**Step 2: Extract `enhancer.py`**

Move from `outline2ppt.py`:
- `enhance_with_llm()` (lines 333-368)
- `format_slide_notes()` (lines 869-886)

```python
# outline2ppt/enhancer.py
"""AI enhancement pipeline for slides."""
from typing import Dict
from outline2ppt.llm import LLMClient


SYSTEM_PROMPT = "You are a professional technical marketing expert and writer helping to enhance PowerPoint slides."


def enhance_with_llm(slide: Dict[str, any], client: LLMClient) -> str:
    """Use LLM to enhance slide content and suggest layout."""
    prompt = f"""You are a professional presentation designer. For this slide, please provide:

1. A brief narrative (2-3 sentences)
2. A layout suggestion using ONLY these types:
   - bullet (for lists and key points)
   - two_column (for comparisons or side-by-side content)
   - diagram (for visual representations)
   - basic (for simple content)
3. Key visual elements or organization suggestions
4. Additional talking points

Slide Title: {slide['title']}
Content:
{chr(10).join(slide['content'])}

Format your response exactly as:
NARRATIVE: [2-3 sentences]
LAYOUT: [one of: bullet, two_column, diagram, basic]
VISUALS: [specific visual suggestions]
TALKING_POINTS: [additional points]
ORIGINAL_CONTENT: [original slide content]
"""

    response = client.generate_text(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        max_tokens=1000,
        temperature=0.7,
    )

    original_content = '\n'.join(slide['content'])
    return f"{response}\n\nORIGINAL CONTENT:\n{original_content}"


def format_slide_notes(suggestions: Dict[str, str]) -> str:
    """Format slide notes from suggestions dict."""
    return f"""
NARRATIVE:
{suggestions.get('NARRATIVE', '')}

LAYOUT:
{suggestions.get('LAYOUT', '')}

VISUALS:
{suggestions.get('VISUALS', '')}

TALKING POINTS:
{suggestions.get('TALKING_POINTS', '')}

ORIGINAL CONTENT:
{suggestions.get('ORIGINAL_CONTENT', '')}
""".strip()
```

**Step 3: Extract `images.py`**

Move from `outline2ppt.py`:
- `setup_image_directory()` (lines 756-770)
- `save_diagram()` (lines 772-782)
- `generate_diagram_svg()` (lines 726-754)
- `generate_dalle_image()` (lines 834-867)
- `convert_svg_to_png()` (lines 888-912)

Keep signatures identical.

**Step 4: Commit**

```bash
git add outline2ppt/layouts.py outline2ppt/enhancer.py outline2ppt/images.py
git commit -m "feat: extract layouts, enhancer, and images modules"
```

---

### Task 4: Extract ppt2outline and create unified CLI

**Files:**
- Create: `outline2ppt/ppt2outline.py`
- Create: `outline2ppt/cli.py`
- Modify: top-level `outline2ppt.py` (becomes thin wrapper)
- Modify: top-level `ppt2outline.py` (becomes thin wrapper)

**Step 1: Move `ppt2outline.py` into package**

Copy `ppt2outline.py` → `outline2ppt/ppt2outline.py`. Keep the `extract_text_from_shape()` and `convert_pptx_to_outline()` functions. Remove the `main()` and CLI handling.

**Step 2: Create `cli.py` with subcommands**

```python
# outline2ppt/cli.py
"""CLI entry point with subcommands."""
import argparse
import logging
import os
import sys

logger = logging.getLogger(__name__)


def cmd_create(args):
    """Create a presentation from a markdown outline."""
    from outline2ppt.parser import parse_outline
    from outline2ppt.llm import LLMClient, load_gateway_config
    from outline2ppt.enhancer import enhance_with_llm
    from outline2ppt.images import setup_image_directory
    from outline2ppt.layouts import add_slide
    from pptx import Presentation

    # (Preserve existing main() logic from outline2ppt.py lines 914-1089,
    #  but use imported modules instead of local functions.)
    # ... full implementation follows existing patterns ...
    pass  # Placeholder — full code extracted from original main()


def cmd_reverse(args):
    """Convert a PowerPoint back to markdown outline."""
    from outline2ppt.ppt2outline import convert_pptx_to_outline
    output = args.output or os.path.splitext(args.input)[0] + '.md'
    success = convert_pptx_to_outline(args.input, output, not args.no_notes)
    return 0 if success else 1


def cmd_catalog(args):
    """Catalog a deck into the slide database."""
    pass  # Implemented in Task 7


def cmd_search(args):
    """Search cataloged slides by tags or title."""
    pass  # Implemented in Task 12


def cmd_remix(args):
    """Assemble a new deck from a manifest file."""
    pass  # Implemented in Task 13


def cmd_analyze(args):
    """Run multimodal analysis on slide images."""
    pass  # Implemented in Task 10


def cmd_export(args):
    """Export slide metadata to CSV."""
    pass  # Implemented in Task 11


def cmd_serve(args):
    """Launch the web UI."""
    pass  # Implemented in Task 14


def build_parser():
    parser = argparse.ArgumentParser(
        prog="outline2ppt",
        description="Convert markdown outlines to PowerPoint presentations.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    sub = parser.add_subparsers(dest="command")

    # create
    p_create = sub.add_parser("create", help="Create presentation from outline")
    p_create.add_argument("outline", help="Markdown outline file")
    p_create.add_argument("template", help="PowerPoint template file")
    p_create.add_argument("output", help="Output .pptx file")
    p_create.add_argument("--enhance", action="store_true")
    p_create.add_argument("--api-key", help="API key")
    p_create.add_argument("--model", default="claude-3.5-sonnet")
    p_create.add_argument("--api-base", help="Base URL for API endpoint")
    p_create.add_argument("--api-provider", choices=["anthropic", "openai", "compatible"])
    p_create.add_argument("--gateway-config", default="gateway.yaml", help="Gateway YAML config path")
    p_create.add_argument("--test", type=int, help="Process only first N slides")
    p_create.add_argument("--analyze-template", action="store_true")
    p_create.add_argument("--image-gen", choices=["claude", "dalle", "openai", "none"], default="none")

    # reverse
    p_reverse = sub.add_parser("reverse", help="Convert PowerPoint to markdown")
    p_reverse.add_argument("input", help="Input .pptx file")
    p_reverse.add_argument("output", nargs="?", help="Output .md file")
    p_reverse.add_argument("--no-notes", action="store_true")

    # catalog
    p_catalog = sub.add_parser("catalog", help="Catalog a deck")
    p_catalog.add_argument("deck", help="PowerPoint file to catalog")
    p_catalog.add_argument("--images-dir", help="Directory with exported slide images")
    p_catalog.add_argument("--db", default="slides.db", help="Database file path")

    # search
    p_search = sub.add_parser("search", help="Search cataloged slides")
    p_search.add_argument("--tags", help="Comma-separated tags to filter by")
    p_search.add_argument("--title-contains", help="Filter by title substring")
    p_search.add_argument("--export-manifest", help="Export results as remix manifest YAML")
    p_search.add_argument("--db", default="slides.db")

    # remix
    p_remix = sub.add_parser("remix", help="Assemble deck from manifest")
    p_remix.add_argument("manifest", help="YAML manifest file")
    p_remix.add_argument("output", help="Output .pptx file")
    p_remix.add_argument("--db", default="slides.db")

    # analyze
    p_analyze = sub.add_parser("analyze", help="AI analysis of slides")
    p_analyze.add_argument("deck", help="PowerPoint file")
    p_analyze.add_argument("--mode", choices=["feedback", "notes", "tags"], required=True)
    p_analyze.add_argument("--taxonomy", help="CSV file with pre-defined tags")
    p_analyze.add_argument("--model", default="gpt-4o")
    p_analyze.add_argument("--api-key")
    p_analyze.add_argument("--gateway-config", default="gateway.yaml")
    p_analyze.add_argument("--images-dir", help="Directory with slide images")
    p_analyze.add_argument("--db", default="slides.db")

    # export
    p_export = sub.add_parser("export", help="Export metadata to CSV")
    p_export.add_argument("deck", nargs="?", help="Specific deck to export")
    p_export.add_argument("--all", action="store_true", help="Export all cataloged decks")
    p_export.add_argument("--output", default="slides.csv")
    p_export.add_argument("--db", default="slides.db")

    # serve
    p_serve = sub.add_parser("serve", help="Launch web UI")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--db", default="slides.db")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    commands = {
        "create": cmd_create,
        "reverse": cmd_reverse,
        "catalog": cmd_catalog,
        "search": cmd_search,
        "remix": cmd_remix,
        "analyze": cmd_analyze,
        "export": cmd_export,
        "serve": cmd_serve,
    }

    if not args.command:
        parser.print_help()
        return 1

    return commands[args.command](args)
```

**Step 3: Update top-level wrapper scripts**

```python
# outline2ppt.py (top-level, becomes thin wrapper)
#!/usr/bin/env python3
"""Thin wrapper — delegates to outline2ppt.cli."""
import sys
from outline2ppt.cli import main

if __name__ == "__main__":
    sys.exit(main() or 0)
```

```python
# ppt2outline.py (top-level, becomes thin wrapper)
#!/usr/bin/env python3
"""Thin wrapper — delegates to outline2ppt reverse command."""
import sys
from outline2ppt.cli import cmd_reverse
import argparse

def main():
    parser = argparse.ArgumentParser(description="Convert PowerPoint to markdown outline")
    parser.add_argument("input", help="Input .pptx file")
    parser.add_argument("output", nargs="?", help="Output .md file")
    parser.add_argument("--no-notes", action="store_true")
    args = parser.parse_args()
    return cmd_reverse(args)

if __name__ == "__main__":
    sys.exit(main() or 0)
```

**Step 4: Fully implement `cmd_create`** by porting the logic from `outline2ppt.py` `main()` (lines 914-1089) into `cmd_create()`, replacing all function calls with imports from the new modules.

**Step 5: Run smoke test**

Create a minimal test outline and verify existing functionality works:
```bash
python outline2ppt.py create test-outline.md template.pptx test-output.pptx
python ppt2outline.py test-output.pptx test-roundtrip.md
```

**Step 6: Commit**

```bash
git add outline2ppt/ppt2outline.py outline2ppt/cli.py outline2ppt.py ppt2outline.py
git commit -m "feat: create unified CLI with subcommands, preserve backward compat"
```

---

## Phase 2: Catalog & Versioning

### Task 5: Create SQLite schema and database module

**Files:**
- Create: `outline2ppt/schema.sql`
- Create: `outline2ppt/catalog.py`
- Create: `tests/test_catalog.py`

**Step 1: Write the schema**

```sql
-- outline2ppt/schema.sql
CREATE TABLE IF NOT EXISTS decks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    slide_count INTEGER NOT NULL DEFAULT 0,
    cataloged_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS slides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    content_text TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    image_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL CHECK(source IN ('ai', 'taxonomy', 'manual'))
);

CREATE TABLE IF NOT EXISTS slide_tags (
    slide_id INTEGER NOT NULL REFERENCES slides(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (slide_id, tag_id)
);

CREATE TABLE IF NOT EXISTS taxonomy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_slides_deck ON slides(deck_id);
CREATE INDEX IF NOT EXISTS idx_slides_hash ON slides(content_hash);
CREATE INDEX IF NOT EXISTS idx_slides_title ON slides(title);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
```

**Step 2: Write catalog module**

```python
# outline2ppt/catalog.py
"""SQLite slide catalog with content hashing and versioning."""
import hashlib
import logging
import os
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional

from pptx import Presentation

from outline2ppt.ppt2outline import extract_text_from_shape

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_db(db_path: str = "slides.db") -> sqlite3.Connection:
    """Open database connection, create schema if needed."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    return conn


def content_hash(title: str, text: str) -> str:
    """SHA-256 hash of normalized title + content text."""
    normalized = f"{title.strip().lower()}\n{text.strip().lower()}"
    return hashlib.sha256(normalized.encode()).hexdigest()


def file_hash(file_path: str) -> str:
    """SHA-256 hash of file contents."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def catalog_deck(
    deck_path: str,
    db_path: str = "slides.db",
    images_dir: Optional[str] = None,
) -> int:
    """Catalog a PowerPoint deck into the database.
    Returns the deck ID.
    """
    conn = get_db(db_path)
    deck_path = os.path.abspath(deck_path)
    deck_name = os.path.splitext(os.path.basename(deck_path))[0]
    fhash = file_hash(deck_path)

    # Check if this exact file is already cataloged
    existing = conn.execute(
        "SELECT id FROM decks WHERE file_path = ? AND file_hash = ?",
        (deck_path, fhash),
    ).fetchone()
    if existing:
        logger.info(f"Deck already cataloged with same hash: {deck_name}")
        return existing["id"]

    prs = Presentation(deck_path)

    # Upsert deck record
    existing_deck = conn.execute(
        "SELECT id FROM decks WHERE file_path = ?", (deck_path,)
    ).fetchone()

    if existing_deck:
        deck_id = existing_deck["id"]
        conn.execute(
            "UPDATE decks SET file_hash = ?, slide_count = ?, updated_at = datetime('now') WHERE id = ?",
            (fhash, len(prs.slides), deck_id),
        )
        # Remove old slides for re-catalog
        conn.execute("DELETE FROM slides WHERE deck_id = ?", (deck_id,))
    else:
        cur = conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
            (deck_name, deck_path, fhash, len(prs.slides)),
        )
        deck_id = cur.lastrowid

    # Catalog each slide
    for i, slide in enumerate(prs.slides, 1):
        title = ""
        if slide.shapes.title and slide.shapes.title.text:
            title = slide.shapes.title.text.strip()

        # Extract text from all non-title shapes
        texts = []
        for shape in slide.shapes:
            if shape == slide.shapes.title:
                continue
            text = extract_text_from_shape(shape)
            if text:
                texts.append(text)
        content_text = "\n".join(texts)

        chash = content_hash(title, content_text)

        # Notes
        notes = ""
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()

        # Image path
        image_path = None
        if images_dir:
            for ext in (".png", ".jpg", ".jpeg"):
                candidate = os.path.join(images_dir, f"Slide{i}{ext}")
                if os.path.exists(candidate):
                    image_path = os.path.abspath(candidate)
                    break

        conn.execute(
            """INSERT INTO slides (deck_id, position, title, content_text, content_hash,
               notes, image_path)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (deck_id, i, title, content_text, chash, notes, image_path),
        )

    conn.commit()
    logger.info(f"Cataloged {len(prs.slides)} slides from {deck_name}")
    conn.close()
    return deck_id


def search_slides(
    db_path: str = "slides.db",
    tags: Optional[List[str]] = None,
    title_contains: Optional[str] = None,
) -> List[Dict]:
    """Search slides by tags and/or title substring."""
    conn = get_db(db_path)
    query = """
        SELECT s.id, s.position, s.title, s.content_hash, s.image_path,
               d.name as deck_name, d.file_path as deck_path,
               s.updated_at
        FROM slides s
        JOIN decks d ON s.deck_id = d.id
        WHERE 1=1
    """
    params = []

    if title_contains:
        query += " AND s.title LIKE ?"
        params.append(f"%{title_contains}%")

    if tags:
        placeholders = ",".join("?" * len(tags))
        query += f"""
            AND s.id IN (
                SELECT st.slide_id FROM slide_tags st
                JOIN tags t ON st.tag_id = t.id
                WHERE t.name IN ({placeholders})
            )
        """
        params.extend(tags)

    query += " ORDER BY d.name, s.position"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def check_newer_versions(
    slides: List[Dict],
    db_path: str = "slides.db",
) -> List[Dict]:
    """Check if any slides have newer versions in other decks.
    Returns list of warnings.
    """
    conn = get_db(db_path)
    warnings = []

    for slide in slides:
        # Find slides with same title but different hash, newer timestamp
        rows = conn.execute(
            """SELECT s.title, s.content_hash, s.updated_at, d.name as deck_name
               FROM slides s JOIN decks d ON s.deck_id = d.id
               WHERE s.title = ? AND s.content_hash != ? AND s.updated_at > ?
               ORDER BY s.updated_at DESC LIMIT 1""",
            (slide["title"], slide["content_hash"], slide.get("updated_at", "")),
        ).fetchall()

        for row in rows:
            warnings.append({
                "slide_title": slide["title"],
                "current_deck": slide.get("deck_name", ""),
                "newer_deck": row["deck_name"],
                "newer_updated": row["updated_at"],
            })

    conn.close()
    return warnings


def add_tags(
    slide_id: int,
    tag_names: List[str],
    source: str = "ai",
    db_path: str = "slides.db",
):
    """Add tags to a slide. Creates tag records if they don't exist."""
    conn = get_db(db_path)
    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        # Upsert tag
        conn.execute(
            "INSERT OR IGNORE INTO tags (name, source) VALUES (?, ?)",
            (name, source),
        )
        tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        if tag_row:
            conn.execute(
                "INSERT OR IGNORE INTO slide_tags (slide_id, tag_id) VALUES (?, ?)",
                (slide_id, tag_row["id"]),
            )
    conn.commit()
    conn.close()


def get_slide_tags(slide_id: int, db_path: str = "slides.db") -> List[str]:
    """Get all tags for a slide."""
    conn = get_db(db_path)
    rows = conn.execute(
        """SELECT t.name FROM tags t
           JOIN slide_tags st ON t.id = st.tag_id
           WHERE st.slide_id = ?
           ORDER BY t.name""",
        (slide_id,),
    ).fetchall()
    conn.close()
    return [r["name"] for r in rows]
```

**Step 3: Write tests**

```python
# tests/test_catalog.py
import pytest
import os
from outline2ppt.catalog import (
    get_db, content_hash, catalog_deck, search_slides,
    add_tags, get_slide_tags, check_newer_versions,
)


class TestContentHash:
    def test_consistent(self):
        h1 = content_hash("Title", "Content")
        h2 = content_hash("Title", "Content")
        assert h1 == h2

    def test_case_insensitive(self):
        h1 = content_hash("Title", "Content")
        h2 = content_hash("TITLE", "CONTENT")
        assert h1 == h2

    def test_different_content(self):
        h1 = content_hash("Title", "Content A")
        h2 = content_hash("Title", "Content B")
        assert h1 != h2


class TestDatabase:
    @pytest.fixture
    def db_path(self, tmp_path):
        return str(tmp_path / "test.db")

    def test_create_schema(self, db_path):
        conn = get_db(db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {r["name"] for r in tables}
        assert "decks" in table_names
        assert "slides" in table_names
        assert "tags" in table_names
        conn.close()


class TestTags:
    @pytest.fixture
    def db_with_slide(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = get_db(db_path)
        conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
            ("test", "/test.pptx", "abc", 1),
        )
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash) VALUES (?, ?, ?, ?, ?)",
            (1, 1, "Test Slide", "content", "hash123"),
        )
        conn.commit()
        conn.close()
        return db_path

    def test_add_and_get_tags(self, db_with_slide):
        add_tags(1, ["security", "architecture"], "ai", db_with_slide)
        tags = get_slide_tags(1, db_with_slide)
        assert "security" in tags
        assert "architecture" in tags

    def test_duplicate_tags_ignored(self, db_with_slide):
        add_tags(1, ["security"], "ai", db_with_slide)
        add_tags(1, ["security"], "ai", db_with_slide)
        tags = get_slide_tags(1, db_with_slide)
        assert tags.count("security") == 1
```

**Step 4: Run tests**

Run: `pytest tests/test_catalog.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add outline2ppt/schema.sql outline2ppt/catalog.py tests/test_catalog.py
git commit -m "feat: SQLite catalog with hashing, tagging, and versioning"
```

---

### Task 6: Wire up `catalog` CLI command

**Files:**
- Modify: `outline2ppt/cli.py`

**Step 1: Implement `cmd_catalog`**

```python
def cmd_catalog(args):
    """Catalog a deck into the slide database."""
    from outline2ppt.catalog import catalog_deck
    if not os.path.exists(args.deck):
        logger.error(f"File not found: {args.deck}")
        return 1
    deck_id = catalog_deck(args.deck, db_path=args.db, images_dir=args.images_dir)
    print(f"Cataloged deck (id={deck_id}): {args.deck}")
    return 0
```

**Step 2: Test manually**

```bash
python -m outline2ppt.cli catalog some-deck.pptx --images-dir images/some-deck/
```

**Step 3: Commit**

```bash
git add outline2ppt/cli.py
git commit -m "feat: wire up catalog CLI command"
```

---

## Phase 3: Multimodal Analysis

### Task 7: Create analyze module

**Files:**
- Create: `outline2ppt/analyze.py`
- Create: `tests/test_analyze.py`

**Step 1: Write analyze module**

```python
# outline2ppt/analyze.py
"""Multimodal slide analysis — feedback, notes generation, and tagging."""
import csv
import logging
from typing import Dict, List, Optional

from outline2ppt.llm import LLMClient

logger = logging.getLogger(__name__)

FEEDBACK_SYSTEM_PROMPT = """You are a presentation design expert reviewing slides for a technical audience.
Provide constructive feedback on: visual clarity, content density, layout effectiveness, and suggestions for improvement.
Be specific and actionable. Keep feedback concise (3-5 bullet points)."""

NOTES_SYSTEM_PROMPT = """You are a technical presenter generating speaker notes for a slide.
Based on the slide image and title, write clear, concise speaker notes that:
- Explain the key points on the slide
- Add context not visible on the slide
- Suggest transition phrases
Keep notes to 3-5 sentences."""

TAGS_SYSTEM_PROMPT_FREEFORM = """You are a content classifier for technical presentations.
Given a slide image, suggest 3-7 descriptive tags that categorize the slide's topic, technology area, and content type.
Return ONLY a comma-separated list of lowercase tags. Example: security, architecture, cloud, aws, diagram"""

TAGS_SYSTEM_PROMPT_TAXONOMY = """You are a content classifier for technical presentations.
Given a slide image and a list of allowed tags, select the most relevant tags from the allowed list.
Return ONLY a comma-separated list of selected tags. Do not invent new tags."""


def analyze_slide(
    client: LLMClient,
    image_path: str,
    mode: str,
    title: str = "",
    taxonomy: Optional[List[str]] = None,
) -> str:
    """Run analysis on a single slide image.

    Args:
        client: LLM client with vision support
        image_path: Path to slide image (PNG/JPG)
        mode: One of 'feedback', 'notes', 'tags'
        title: Slide title for context
        taxonomy: Pre-defined tag list (for tags mode with taxonomy)

    Returns:
        Analysis result as text
    """
    if mode == "feedback":
        system = FEEDBACK_SYSTEM_PROMPT
        prompt = f"Review this slide titled '{title}'. Provide design and content feedback."
    elif mode == "notes":
        system = NOTES_SYSTEM_PROMPT
        prompt = f"Generate speaker notes for this slide titled '{title}'."
    elif mode == "tags":
        if taxonomy:
            system = TAGS_SYSTEM_PROMPT_TAXONOMY
            tag_list = ", ".join(taxonomy)
            prompt = f"Classify this slide titled '{title}'. Allowed tags: {tag_list}"
        else:
            system = TAGS_SYSTEM_PROMPT_FREEFORM
            prompt = f"Suggest tags for this slide titled '{title}'."
    else:
        raise ValueError(f"Unknown analysis mode: {mode}")

    return client.generate_text_with_image(
        prompt=prompt,
        image_path=image_path,
        system_prompt=system,
        max_tokens=500,
        temperature=0.3,
    )


def parse_tags_response(response: str) -> List[str]:
    """Parse comma-separated tag response from LLM."""
    return [t.strip().lower() for t in response.split(",") if t.strip()]


def load_taxonomy(csv_path: str) -> List[str]:
    """Load pre-defined tags from a CSV file.
    Expects a column named 'name' or uses the first column.
    """
    tags = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        field = "name" if "name" in (reader.fieldnames or []) else (reader.fieldnames or [""])[0]
        for row in reader:
            if row.get(field, "").strip():
                tags.append(row[field].strip().lower())
    return tags
```

**Step 2: Write tests**

```python
# tests/test_analyze.py
import pytest
from outline2ppt.analyze import parse_tags_response, load_taxonomy


class TestParseTagsResponse:
    def test_basic(self):
        result = parse_tags_response("security, architecture, cloud")
        assert result == ["security", "architecture", "cloud"]

    def test_handles_whitespace(self):
        result = parse_tags_response("  security ,  cloud  , aws ")
        assert result == ["security", "cloud", "aws"]

    def test_empty_string(self):
        result = parse_tags_response("")
        assert result == []


class TestLoadTaxonomy:
    def test_load_csv(self, tmp_path):
        csv_file = tmp_path / "tags.csv"
        csv_file.write_text("name,category\nsecurity,topic\ncloud,topic\n")
        result = load_taxonomy(str(csv_file))
        assert result == ["security", "cloud"]
```

**Step 3: Run tests**

Run: `pytest tests/test_analyze.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add outline2ppt/analyze.py tests/test_analyze.py
git commit -m "feat: multimodal slide analysis (feedback, notes, tags)"
```

---

### Task 8: Wire up `analyze` CLI command

**Files:**
- Modify: `outline2ppt/cli.py`

**Step 1: Implement `cmd_analyze`**

```python
def cmd_analyze(args):
    """Run multimodal analysis on slide images."""
    from pptx import Presentation
    from outline2ppt.llm import LLMClient, load_gateway_config
    from outline2ppt.analyze import analyze_slide, parse_tags_response, load_taxonomy
    from outline2ppt.catalog import get_db, add_tags, catalog_deck

    if not os.path.exists(args.deck):
        logger.error(f"File not found: {args.deck}")
        return 1

    # Setup LLM client
    gateway = load_gateway_config(args.gateway_config)
    client = LLMClient(model=args.model, api_key=args.api_key, gateway=gateway)

    # Determine images directory
    images_dir = args.images_dir
    if not images_dir:
        deck_name = os.path.splitext(os.path.basename(args.deck))[0]
        images_dir = os.path.join("images", deck_name)

    if not os.path.isdir(images_dir):
        logger.error(f"Images directory not found: {images_dir}")
        logger.info("Export slides as images from PowerPoint, then place in the images directory.")
        return 1

    # Ensure deck is cataloged
    deck_id = catalog_deck(args.deck, db_path=args.db, images_dir=images_dir)

    # Load taxonomy if provided
    taxonomy = None
    if args.taxonomy:
        taxonomy = load_taxonomy(args.taxonomy)

    # Get slides from catalog
    conn = get_db(args.db)
    slides = conn.execute(
        "SELECT id, position, title, image_path FROM slides WHERE deck_id = ? ORDER BY position",
        (deck_id,),
    ).fetchall()

    prs = Presentation(args.deck)

    for slide_row in slides:
        if not slide_row["image_path"] or not os.path.exists(slide_row["image_path"]):
            logger.warning(f"No image for slide {slide_row['position']}: {slide_row['title']}, skipping")
            continue

        logger.info(f"Analyzing slide {slide_row['position']}: {slide_row['title']}")

        try:
            result = analyze_slide(
                client=client,
                image_path=slide_row["image_path"],
                mode=args.mode,
                title=slide_row["title"],
                taxonomy=taxonomy,
            )

            if args.mode == "feedback":
                print(f"\n--- Slide {slide_row['position']}: {slide_row['title']} ---")
                print(result)

            elif args.mode == "notes":
                # Write notes back into PPTX
                pptx_slide = prs.slides[slide_row["position"] - 1]
                notes_slide = pptx_slide.notes_slide
                notes_slide.notes_text_frame.text = result
                print(f"Slide {slide_row['position']}: notes generated")

            elif args.mode == "tags":
                tags = parse_tags_response(result)
                source = "taxonomy" if taxonomy else "ai"
                add_tags(slide_row["id"], tags, source=source, db_path=args.db)
                print(f"Slide {slide_row['position']}: tagged with {tags}")

        except Exception as e:
            logger.error(f"Error analyzing slide {slide_row['position']}: {e}")
            continue

    if args.mode == "notes":
        prs.save(args.deck)
        logger.info(f"Notes saved to {args.deck}")

    conn.close()
    return 0
```

**Step 2: Commit**

```bash
git add outline2ppt/cli.py
git commit -m "feat: wire up analyze CLI command"
```

---

## Phase 4: Export & Remix

### Task 9: Create export module

**Files:**
- Create: `outline2ppt/export.py`
- Create: `tests/test_export.py`

**Step 1: Write export module**

```python
# outline2ppt/export.py
"""Export slide metadata to CSV."""
import csv
import logging
from typing import Optional

from outline2ppt.catalog import get_db, get_slide_tags

logger = logging.getLogger(__name__)

COLUMNS = [
    "deck_name", "slide_number", "title", "notes",
    "tags", "content_hash", "image_path", "last_updated",
]


def export_csv(
    output_path: str,
    db_path: str = "slides.db",
    deck_path: Optional[str] = None,
    export_all: bool = False,
):
    """Export slide metadata to CSV.

    Args:
        output_path: CSV output file path
        db_path: SQLite database path
        deck_path: Specific deck to export (by file path)
        export_all: If True, export all decks
    """
    conn = get_db(db_path)

    if deck_path:
        import os
        deck_path = os.path.abspath(deck_path)
        query = """
            SELECT s.id, s.position, s.title, s.notes, s.content_hash,
                   s.image_path, s.updated_at, d.name as deck_name
            FROM slides s JOIN decks d ON s.deck_id = d.id
            WHERE d.file_path = ?
            ORDER BY d.name, s.position
        """
        rows = conn.execute(query, (deck_path,)).fetchall()
    elif export_all:
        query = """
            SELECT s.id, s.position, s.title, s.notes, s.content_hash,
                   s.image_path, s.updated_at, d.name as deck_name
            FROM slides s JOIN decks d ON s.deck_id = d.id
            ORDER BY d.name, s.position
        """
        rows = conn.execute(query).fetchall()
    else:
        logger.error("Specify a deck path or use --all")
        conn.close()
        return

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            tags = get_slide_tags(row["id"], db_path)
            writer.writerow({
                "deck_name": row["deck_name"],
                "slide_number": row["position"],
                "title": row["title"],
                "notes": row["notes"],
                "tags": "; ".join(tags),
                "content_hash": row["content_hash"],
                "image_path": row["image_path"] or "",
                "last_updated": row["updated_at"],
            })

    conn.close()
    logger.info(f"Exported {len(rows)} slides to {output_path}")
```

**Step 2: Write tests**

```python
# tests/test_export.py
import pytest
import csv
from outline2ppt.catalog import get_db
from outline2ppt.export import export_csv


@pytest.fixture
def db_with_data(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_db(db_path)
    conn.execute(
        "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
        ("deck1", "/deck1.pptx", "abc", 2),
    )
    conn.execute(
        "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (1, 1, "Intro", "intro content", "hash1", "speaker notes"),
    )
    conn.execute(
        "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (1, 2, "Summary", "summary content", "hash2", ""),
    )
    conn.commit()
    conn.close()
    return db_path


def test_export_all(tmp_path, db_with_data):
    output = str(tmp_path / "out.csv")
    export_csv(output, db_path=db_with_data, export_all=True)

    with open(output) as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 2
        assert reader[0]["title"] == "Intro"
        assert reader[0]["notes"] == "speaker notes"
```

**Step 3: Run tests, commit**

Run: `pytest tests/test_export.py -v`

```bash
git add outline2ppt/export.py tests/test_export.py
git commit -m "feat: CSV metadata export"
```

---

### Task 10: Wire up export CLI command

**Files:**
- Modify: `outline2ppt/cli.py`

**Step 1: Implement `cmd_export`**

```python
def cmd_export(args):
    """Export slide metadata to CSV."""
    from outline2ppt.export import export_csv
    export_csv(
        output_path=args.output,
        db_path=args.db,
        deck_path=args.deck,
        export_all=args.all,
    )
    print(f"Exported to {args.output}")
    return 0
```

**Step 2: Commit**

```bash
git add outline2ppt/cli.py
git commit -m "feat: wire up export CLI command"
```

---

### Task 11: Create remix module

**Files:**
- Create: `outline2ppt/remix.py`
- Create: `tests/test_remix.py`

**Step 1: Write remix module**

```python
# outline2ppt/remix.py
"""Slide remix — search, manifest, and deck assembly."""
import copy
import logging
import os
from typing import Dict, List, Optional

import yaml
from lxml import etree
from pptx import Presentation

from outline2ppt.catalog import search_slides, check_newer_versions

logger = logging.getLogger(__name__)


def generate_manifest(
    slides: List[Dict],
    title: str = "Remixed Presentation",
    template: str = "template.pptx",
) -> str:
    """Generate a YAML manifest from search results."""
    manifest = {
        "title": title,
        "template": template,
        "slides": [],
    }
    for s in slides:
        manifest["slides"].append({
            "deck": os.path.basename(s["deck_path"]),
            "deck_path": s["deck_path"],
            "position": s["position"],
            "title": s["title"],
        })
    return yaml.dump(manifest, default_flow_style=False, sort_keys=False)


def load_manifest(manifest_path: str) -> Dict:
    """Load and validate a remix manifest."""
    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    required = ["title", "slides"]
    for key in required:
        if key not in manifest:
            raise ValueError(f"Manifest missing required key: {key}")

    return manifest


def copy_slide(source_prs, source_index, target_prs):
    """Copy a slide from source presentation to target.

    Uses python-pptx XML manipulation to copy slide layout and content.
    This is the standard approach since python-pptx doesn't have a
    built-in slide copy method.
    """
    source_slide = source_prs.slides[source_index]

    # Find or use the first layout in target as base
    slide_layout = target_prs.slide_layouts[0]

    # Try to find matching layout by name
    source_layout_name = source_slide.slide_layout.name
    for layout in target_prs.slide_layouts:
        if layout.name == source_layout_name:
            slide_layout = layout
            break

    new_slide = target_prs.slides.add_slide(slide_layout)

    # Copy shapes from source to target
    for shape in source_slide.shapes:
        # Clone shape XML
        sp = copy.deepcopy(shape._element)
        new_slide.shapes._spTree.append(sp)

    # Remove default placeholder shapes that came with the layout
    # (they duplicate content from the copied shapes)
    for shape in list(new_slide.placeholders):
        sp = shape._element
        sp.getparent().remove(sp)

    # Copy notes if they exist
    if source_slide.has_notes_slide:
        notes_slide = new_slide.notes_slide
        notes_slide.notes_text_frame.text = source_slide.notes_slide.notes_text_frame.text

    return new_slide


def assemble_deck(
    manifest_path: str,
    output_path: str,
    db_path: str = "slides.db",
):
    """Assemble a new deck from a manifest file.

    Args:
        manifest_path: Path to YAML manifest
        output_path: Output .pptx path
        db_path: Catalog database path for version checking
    """
    manifest = load_manifest(manifest_path)

    # Use template if specified, otherwise use first source deck as base
    template = manifest.get("template")
    if template and os.path.exists(template):
        target_prs = Presentation(template)
    else:
        # Use the first source deck's template
        first_deck = manifest["slides"][0].get("deck_path", manifest["slides"][0]["deck"])
        target_prs = Presentation(first_deck)
        # Remove existing slides
        while len(target_prs.slides) > 0:
            rId = target_prs.slides._sldIdLst[0].get('r:id')
            target_prs.part.drop_rel(rId)
            target_prs.slides._sldIdLst.remove(target_prs.slides._sldIdLst[0])

    # Check for newer versions
    slide_dicts = []
    for entry in manifest["slides"]:
        slide_dicts.append({
            "title": entry["title"],
            "content_hash": entry.get("content_hash", ""),
            "deck_name": entry.get("deck", ""),
            "updated_at": entry.get("updated_at", ""),
        })

    warnings = check_newer_versions(slide_dicts, db_path)
    for w in warnings:
        logger.warning(
            f"Newer version of '{w['slide_title']}' found in {w['newer_deck']} "
            f"(updated {w['newer_updated']})"
        )

    # Cache opened presentations
    prs_cache = {}

    for entry in manifest["slides"]:
        deck_path = entry.get("deck_path", entry["deck"])
        position = entry["position"]

        if deck_path not in prs_cache:
            if not os.path.exists(deck_path):
                logger.error(f"Deck not found: {deck_path}")
                continue
            prs_cache[deck_path] = Presentation(deck_path)

        source_prs = prs_cache[deck_path]
        slide_index = position - 1  # 0-based

        if slide_index >= len(source_prs.slides):
            logger.error(f"Slide {position} not found in {deck_path} (only {len(source_prs.slides)} slides)")
            continue

        try:
            copy_slide(source_prs, slide_index, target_prs)
            logger.info(f"Copied slide {position} from {os.path.basename(deck_path)}: {entry['title']}")
        except Exception as e:
            logger.error(f"Error copying slide {position} from {deck_path}: {e}")
            continue

    target_prs.save(output_path)
    logger.info(f"Assembled {len(manifest['slides'])} slides into {output_path}")
```

**Step 2: Write tests**

```python
# tests/test_remix.py
import pytest
import yaml
from outline2ppt.remix import generate_manifest, load_manifest


class TestGenerateManifest:
    def test_basic(self):
        slides = [
            {"deck_path": "/path/deck.pptx", "position": 1, "title": "Intro"},
            {"deck_path": "/path/deck.pptx", "position": 5, "title": "Summary"},
        ]
        result = generate_manifest(slides, title="Test Deck")
        parsed = yaml.safe_load(result)
        assert parsed["title"] == "Test Deck"
        assert len(parsed["slides"]) == 2
        assert parsed["slides"][0]["position"] == 1


class TestLoadManifest:
    def test_valid(self, tmp_path):
        f = tmp_path / "manifest.yaml"
        f.write_text(yaml.dump({
            "title": "Test",
            "slides": [{"deck": "a.pptx", "position": 1, "title": "Slide 1"}],
        }))
        result = load_manifest(str(f))
        assert result["title"] == "Test"
        assert len(result["slides"]) == 1

    def test_missing_required_key(self, tmp_path):
        f = tmp_path / "manifest.yaml"
        f.write_text(yaml.dump({"title": "Test"}))
        with pytest.raises(ValueError, match="missing required key"):
            load_manifest(str(f))
```

**Step 3: Run tests, commit**

Run: `pytest tests/test_remix.py -v`

```bash
git add outline2ppt/remix.py tests/test_remix.py
git commit -m "feat: remix system (manifest, search, deck assembly)"
```

---

### Task 12: Wire up search and remix CLI commands

**Files:**
- Modify: `outline2ppt/cli.py`

**Step 1: Implement `cmd_search`**

```python
def cmd_search(args):
    """Search cataloged slides."""
    from outline2ppt.catalog import search_slides
    from outline2ppt.remix import generate_manifest

    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
    results = search_slides(db_path=args.db, tags=tags, title_contains=args.title_contains)

    if not results:
        print("No matching slides found.")
        return 0

    for r in results:
        print(f"  [{r['deck_name']}] Slide {r['position']}: {r['title']}")

    if args.export_manifest:
        manifest_yaml = generate_manifest(results)
        with open(args.export_manifest, "w") as f:
            f.write(manifest_yaml)
        print(f"\nManifest written to {args.export_manifest}")

    return 0
```

**Step 2: Implement `cmd_remix`**

```python
def cmd_remix(args):
    """Assemble a new deck from a manifest."""
    from outline2ppt.remix import assemble_deck
    assemble_deck(args.manifest, args.output, db_path=args.db)
    print(f"Remixed deck saved to {args.output}")
    return 0
```

**Step 3: Commit**

```bash
git add outline2ppt/cli.py
git commit -m "feat: wire up search and remix CLI commands"
```

---

## Phase 5: Web UI

### Task 13: Create FastAPI app with htmx frontend

**Files:**
- Create: `outline2ppt/web/app.py`
- Create: `outline2ppt/web/routes.py`
- Create: `outline2ppt/web/static/index.html`
- Create: `outline2ppt/web/static/style.css`

**Step 1: Create FastAPI app**

```python
# outline2ppt/web/app.py
"""FastAPI web application."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from outline2ppt.web.routes import router

STATIC_DIR = Path(__file__).parent / "static"


def create_app(db_path: str = "slides.db") -> FastAPI:
    app = FastAPI(title="Outline2PPT", version="2.0.0")
    app.state.db_path = db_path
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(router)
    return app
```

**Step 2: Create routes**

```python
# outline2ppt/web/routes.py
"""API routes for the web UI."""
from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path
import os

from outline2ppt.catalog import get_db, catalog_deck, search_slides, add_tags, get_slide_tags
from outline2ppt.export import export_csv

router = APIRouter()
TEMPLATE_DIR = Path(__file__).parent / "static"


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard — list decks."""
    db_path = request.app.state.db_path
    conn = get_db(db_path)
    decks = conn.execute(
        "SELECT id, name, slide_count, cataloged_at, updated_at FROM decks ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()

    # Return the index.html (htmx handles dynamic content)
    return (TEMPLATE_DIR / "index.html").read_text()


@router.get("/api/decks")
async def list_decks(request: Request):
    """API: List all cataloged decks."""
    db_path = request.app.state.db_path
    conn = get_db(db_path)
    decks = conn.execute(
        "SELECT id, name, slide_count, cataloged_at, updated_at FROM decks ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(d) for d in decks]


@router.get("/api/decks/{deck_id}/slides")
async def deck_slides(deck_id: int, request: Request):
    """API: List slides for a deck."""
    db_path = request.app.state.db_path
    conn = get_db(db_path)
    slides = conn.execute(
        "SELECT id, position, title, notes, image_path, content_hash FROM slides WHERE deck_id = ? ORDER BY position",
        (deck_id,),
    ).fetchall()
    result = []
    for s in slides:
        tags = get_slide_tags(s["id"], db_path)
        d = dict(s)
        d["tags"] = tags
        result.append(d)
    conn.close()
    return result


@router.get("/api/search")
async def search(request: Request, tags: str = "", title: str = ""):
    """API: Search slides."""
    db_path = request.app.state.db_path
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] or None
    title_contains = title if title else None
    results = search_slides(db_path=db_path, tags=tag_list, title_contains=title_contains)
    return results


@router.post("/api/slides/{slide_id}/tags")
async def tag_slide(slide_id: int, request: Request):
    """API: Add tags to a slide."""
    db_path = request.app.state.db_path
    body = await request.json()
    tag_names = body.get("tags", [])
    source = body.get("source", "manual")
    add_tags(slide_id, tag_names, source=source, db_path=db_path)
    return {"status": "ok", "tags": get_slide_tags(slide_id, db_path)}


@router.get("/api/export")
async def export(request: Request):
    """API: Export all cataloged slides to CSV and return file."""
    import tempfile
    db_path = request.app.state.db_path
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    export_csv(tmp.name, db_path=db_path, export_all=True)
    return FileResponse(tmp.name, filename="slides.csv", media_type="text/csv")


@router.get("/images/{path:path}")
async def serve_image(path: str):
    """Serve slide images from the images directory."""
    full_path = os.path.join("images", path)
    if os.path.exists(full_path):
        return FileResponse(full_path)
    return HTMLResponse("Not found", status_code=404)
```

**Step 3: Create index.html with htmx**

Create `outline2ppt/web/static/index.html` — a single-page app using htmx for dynamic content, Pico CSS for styling. Pages: deck list, slide browser with thumbnails, search, tag editing.

Key features:
- Deck list with slide counts
- Click a deck → see slides with thumbnails (from image_path)
- Search bar with tag and title filtering
- Click a slide → see details, edit tags
- Export CSV button

**Step 4: Wire up `cmd_serve`**

```python
def cmd_serve(args):
    """Launch the web UI."""
    import uvicorn
    from outline2ppt.web.app import create_app
    app = create_app(db_path=args.db)
    uvicorn.run(app, host="127.0.0.1", port=args.port)
```

**Step 5: Commit**

```bash
git add outline2ppt/web/
git commit -m "feat: FastAPI web UI with htmx"
```

---

## Phase 6: Integration & Polish

### Task 14: Update requirements.txt and package config

**Files:**
- Modify: `requirements.txt`
- Create: `pyproject.toml` (or `setup.py` — use pyproject.toml for modern packaging)

**Step 1: Update requirements.txt**

```
python-pptx>=0.6.21
anthropic>=0.8.0
cairosvg>=2.7.1
openai>=1.3.0
pillow>=10.0.0
requests>=2.31.0
pyyaml>=6.0
fastapi>=0.100.0
uvicorn>=0.23.0
python-multipart>=0.0.6
lxml>=4.9.0
```

**Step 2: Create pyproject.toml**

```toml
[project]
name = "outline2ppt"
version = "2.0.0"
description = "Convert markdown outlines to PowerPoint presentations with AI enhancement"
requires-python = ">=3.10"

[project.scripts]
outline2ppt = "outline2ppt.cli:main"

[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-cov"]
```

**Step 3: Commit**

```bash
git add requirements.txt pyproject.toml
git commit -m "chore: update dependencies and add pyproject.toml"
```

---

### Task 15: Update CLAUDE.md with new architecture

**Files:**
- Modify: `CLAUDE.md`

Update CLAUDE.md to document:
- New package structure
- New CLI commands (catalog, search, remix, analyze, export, serve)
- Gateway configuration
- Database location and schema
- Testing instructions (`pytest`)

**Step 1: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for v2 architecture"
```

---

### Task 16: End-to-end integration test

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

Test the full flow: create a minimal PPTX with python-pptx, catalog it, add tags, search, generate manifest, export CSV. Uses temporary directories, no real LLM calls.

```python
# tests/test_integration.py
import pytest
import os
from pptx import Presentation
from outline2ppt.catalog import catalog_deck, search_slides, add_tags, get_slide_tags
from outline2ppt.export import export_csv
from outline2ppt.remix import generate_manifest, load_manifest


@pytest.fixture
def sample_deck(tmp_path):
    """Create a minimal PPTX for testing."""
    prs = Presentation()
    layout = prs.slide_layouts[0]

    slide1 = prs.slides.add_slide(layout)
    slide1.shapes.title.text = "Introduction"

    slide2 = prs.slides.add_slide(layout)
    slide2.shapes.title.text = "Security Overview"

    path = str(tmp_path / "test.pptx")
    prs.save(path)
    return path


def test_catalog_search_tag_export_flow(tmp_path, sample_deck):
    db_path = str(tmp_path / "test.db")

    # Catalog
    deck_id = catalog_deck(sample_deck, db_path=db_path)
    assert deck_id > 0

    # Search by title
    results = search_slides(db_path=db_path, title_contains="Security")
    assert len(results) == 1
    assert results[0]["title"] == "Security Overview"

    # Tag
    slide_id = results[0]["id"]
    add_tags(slide_id, ["security", "overview"], source="manual", db_path=db_path)
    tags = get_slide_tags(slide_id, db_path)
    assert "security" in tags

    # Search by tag
    results = search_slides(db_path=db_path, tags=["security"])
    assert len(results) == 1

    # Export CSV
    csv_path = str(tmp_path / "export.csv")
    export_csv(csv_path, db_path=db_path, export_all=True)
    assert os.path.exists(csv_path)

    # Generate manifest
    manifest_yaml = generate_manifest(results, title="Security Deck")
    manifest_path = str(tmp_path / "manifest.yaml")
    with open(manifest_path, "w") as f:
        f.write(manifest_yaml)
    manifest = load_manifest(manifest_path)
    assert manifest["title"] == "Security Deck"
    assert len(manifest["slides"]) == 1
```

**Step 2: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end integration test for catalog-search-tag-export flow"
```

---

## Summary

| Phase | Tasks | What's Built | Status |
|-------|-------|-------------|--------|
| 1: Scaffold | 1-4 | Package structure, extracted modules, unified CLI | DONE |
| 2: Catalog | 5-6 | SQLite catalog, content hashing, versioning | DONE |
| 3: Analysis | 7-8 | Multimodal feedback, notes gen, tagging | DONE |
| 4: Export & Remix | 9-12 | CSV export, search, manifest, deck assembly | DONE |
| 5: Web UI | 13 | FastAPI + htmx dashboard | DONE |
| 6: Polish | 14-16 | Dependencies, docs, integration tests | DONE |

**Execution order is strict** — each phase depends on the previous. Within a phase, tasks are sequential.

**Dependencies added**: `pyyaml`, `fastapi`, `uvicorn`, `python-multipart`, `lxml`

**Not included (YAGNI)**: full PPTX rendering, authentication, containerization, async task queues, database migrations framework.

**Status**: All 16 tasks COMPLETE. 211 tests passing (3 skipped -- gateway live tests).
