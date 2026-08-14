"""Generate a Python script using pptx_helpers AMD templates from a markdown outline.

The LLM reads the outline and decides which AMD branded helper to use for each
slide — including which title slide variant (rocm vs default), whether to add
an agenda, when to use stat callouts vs two-column vs section dividers, etc.

The generated script is executed by the existing Renderer (which already handles
.py files via _VENV_PYTHON), producing a .pptx in the render output directory.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Public error type
# ---------------------------------------------------------------------------


class ScriptGenerationError(Exception):
    """Raised when the LLM cannot produce a valid script."""


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert AMD presentation builder. Your job is to read a markdown
presentation outline and produce a complete, runnable Python script that uses
the AIPPT pptx_helpers library to build a branded AMD PowerPoint deck.

## Available functions (import from pptx_helpers)

```python
open_title_deck(title, subtitle='', variant='default') -> prs
    # ALWAYS the first call. Returns a Presentation with the title slide as slide 0.
    # variant='rocm'    — full-bleed photo bg + AMD Instinct graphic
    #                     USE FOR: GPU compute, ROCm, MI300X, Instinct, AI infrastructure,
    #                              machine learning, HPC, data center topics
    # variant='default' — dot/pattern background, AMD wordmark
    #                     USE FOR: general software, business, overview, product, partner decks
    # variant='corp'    — plain corporate template (no photo)
    #                     USE FOR: internal/legal/finance decks only

add_agenda_slide(prs, section_title, items, variant='full') -> prs
    # Appends a numbered agenda slide. MUST reassign: prs = add_agenda_slide(...)
    # section_title: label on left panel (e.g. "Agenda", "What's New", "Overview")
    # items: list of strings, up to 6. Each becomes a numbered row (01, 02…)
    # variant='full'      — standard agenda with photo background
    # variant='whats-new' — alternate bg, suited for release/update decks
    # USE WHEN: outline has 4+ content slides OR user mentions "agenda"

add_section_divider_slide(prs, section_title, subtitle='') -> slide
    # Full-bleed photo + dark overlay + large white title. Use to transition
    # between major topic blocks (every 2-3 content slides).
    # Keep section_title to 2-5 words.

add_stat_callout_slide(prs, title, body, bg_image=None,
                       title_color='FFFFFF', body_color='E5E5E5') -> slide
    # Left panel: large punchy title (2-5 words, e.g. "3.7× Better TCO")
    # Right panel: supporting body text. Use \\n to separate paragraphs.
    # Bold lead-in syntax: **Bold text** rest of sentence
    # bg_image: optional path override (default: themes/assets/title-bg.jpeg)
    # USE WHEN: slide has a prominent number, stat, metric, or bold claim

add_performance_image_slide(prs, title, image_path, subtitle='') -> slide
    # Dark left panel with title + subtitle, full-bleed image on right.
    # USE WHEN: slide has a chart, benchmark screenshot, or architecture diagram.
    # Available assets in themes/assets/:
    #   perf-comparison-1.png  — benchmark comparison full-bleed
    #   perf-comparison-2.jpeg — benchmark comparison variant
    #   rocm-software-stack.png — ROCm layer diagram
    #   mi300x-die.png         — MI300X chip render
    #   mi355x-die.png         — MI355X chip render
    #   mi-product-1.png       — MI product render
    #   mi-product-2.png       — MI product render variant
    #   roadmap-1.png          — GPU generation roadmap
    #   roadmap-2.png          — GPU roadmap variant
    #   chart-frame.jpeg       — benchmark frame/border

add_two_column_slide(prs, title, left_header, left_items,
                     right_header, right_items, notes='') -> slide
    # Two-column layout with teal column headers and bullet items.
    # left_items / right_items: list of strings. **bold** lead-in supported.
    # Use empty string '' for left_header/right_header to omit headers.
    # USE WHEN: comparison, vs, before/after, two contrasting topics (4-8 bullets total)

add_closing_slide(prs) -> slide
    # AMD branded closing slide. ALWAYS the last slide.

set_notes(slide, text)
    # Set speaker notes on any slide (optional).

save_deck(prs, output_path)
    # Save the presentation. ALWAYS use:
    #   out_dir = os.environ.get('AIPPT_PREVIEW_OUT', 'output')
    #   save_deck(prs, os.path.join(out_dir, '<deck-name>.pptx'))
```

## Script skeleton

```python
import sys, os
sys.path.insert(0, 'lib')
from pptx_helpers import (
    open_title_deck, add_agenda_slide, add_stat_callout_slide,
    add_section_divider_slide, add_performance_image_slide,
    add_two_column_slide, add_closing_slide, set_notes, save_deck,
)

# Slide 1 — Title
prs = open_title_deck("Deck Title", "Subtitle / Date", variant='rocm')

# Slide 2 — Agenda (when 4+ content slides)
prs = add_agenda_slide(prs, "Agenda", [
    "Topic One", "Topic Two", "Topic Three",
], variant='full')

# Slide 3 — Section divider
add_section_divider_slide(prs, "Topic One", "Optional subtitle")

# Slide 4 — Stat callout
add_stat_callout_slide(prs,
    "3.7×\\nBetter TCO",
    "**192 GB HBM3** — largest GPU memory\\n\\n**Open ROCm** — no lock-in",
)

# Slide 5 — Performance image
add_performance_image_slide(prs,
    "Inference Performance",
    "themes/assets/perf-comparison-1.png",
    "Llama 3 70B · FP8",
)

# Slide 6 — Two column
add_two_column_slide(prs, "ROCm vs CUDA",
    "ROCm (AMD)", ["**Open source** — Apache 2.0", "PyTorch native"],
    "CUDA (NVIDIA)", ["Proprietary", "Vendor lock-in"],
)

# Final slide — Closing
add_closing_slide(prs)

out_dir = os.environ.get('AIPPT_PREVIEW_OUT', 'output')
save_deck(prs, os.path.join(out_dir, 'deck-name.pptx'))
```

## Decision guide

| Outline signal | Use |
|---|---|
| GPU / ROCm / MI300X / Instinct / HPC / AI compute | open_title_deck variant='rocm' |
| Software / business / product / general | open_title_deck variant='default' |
| 4+ sections or "agenda" mentioned | add_agenda_slide after title |
| Release / update / "What's New" deck | add_agenda_slide variant='whats-new' |
| Major topic transition (every 2-3 slides) | add_section_divider_slide |
| Prominent number, stat, metric, bold claim | add_stat_callout_slide |
| Chart, benchmark, architecture diagram, product image | add_performance_image_slide |
| Comparison / vs / before-after / two topics | add_two_column_slide |
| Final slide | add_closing_slide (always last) |

## Rules — violating these breaks the output

- ALWAYS start with open_title_deck (slide 1)
- ALWAYS end with add_closing_slide
- ALWAYS reassign prs after add_agenda_slide: prs = add_agenda_slide(...)
- ALWAYS use AIPPT_PREVIEW_OUT env var for output path
- NEVER import anything except: sys, os, pptx_helpers functions
- NEVER use open(), file I/O, subprocess, requests, or any network calls
- NEVER hardcode the output path — always use os.environ.get('AIPPT_PREVIEW_OUT', 'output')
- Only use image paths under themes/assets/ — do NOT fabricate image paths

## Output format

Respond with ONLY the Python script inside a ```python code fence.
No explanation, preamble, or text outside the fence.
"""

# ---------------------------------------------------------------------------
# Code-block extractor
# ---------------------------------------------------------------------------

_CODE_FENCE_RE = re.compile(
    r"```(?:python|py)?\s*\n(.*?)```",
    re.DOTALL,
)


def _extract_code_block(text: str) -> str:
    m = _CODE_FENCE_RE.search(text)
    return m.group(1).strip() if m else text.strip()


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

_REQUIRED_PATTERNS = [
    (re.compile(r'\bopen_title_deck\s*\('), "missing open_title_deck() call"),
    (re.compile(r'\badd_closing_slide\s*\('), "missing add_closing_slide() call"),
    (re.compile(r'AIPPT_PREVIEW_OUT'), "output path must use AIPPT_PREVIEW_OUT env var"),
    (re.compile(r'\bsave_deck\s*\('), "missing save_deck() call"),
]

_FORBIDDEN_PATTERNS = [
    (re.compile(r'\bimport\s+requests\b'), "requests import not allowed"),
    (re.compile(r'\bsubprocess\b'), "subprocess not allowed"),
    (re.compile(r'\bopen\s*\('), "file open() not allowed"),
    (re.compile(r'(?<!\.)os\.system\b'), "os.system not allowed"),
]

_KNOWN_HELPERS = {
    'open_title_deck', 'add_agenda_slide', 'add_stat_callout_slide',
    'add_section_divider_slide', 'add_performance_image_slide',
    'add_two_column_slide', 'add_closing_slide', 'set_notes', 'save_deck',
}

_IMPORT_RE = re.compile(r'from pptx_helpers import\s*\(([^)]+)\)', re.DOTALL)


def _validate_script(source: str):
    """Return (ok, reasons). Pure function."""
    reasons = []

    for pattern, msg in _REQUIRED_PATTERNS:
        if not pattern.search(source):
            reasons.append(msg)

    for pattern, msg in _FORBIDDEN_PATTERNS:
        if pattern.search(source):
            reasons.append(msg)

    # Check that add_agenda_slide result is reassigned
    if 'add_agenda_slide' in source:
        if not re.search(r'prs\s*=\s*add_agenda_slide', source):
            reasons.append("add_agenda_slide() result must be reassigned: prs = add_agenda_slide(...)")

    # Check imported names are all known helpers
    m = _IMPORT_RE.search(source)
    if m:
        imported = {n.strip() for n in m.group(1).split(',') if n.strip()}
        unknown = imported - _KNOWN_HELPERS - {'sys', 'os'}
        for u in unknown:
            reasons.append(f"unknown import '{u}' from pptx_helpers")

    return len(reasons) == 0, reasons


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_script(
    outline_text: str,
    output_script_path: str,
    llm_client,
    theme: str = "amd",
    max_retries: int = 3,
    progress_callback: Optional[Callable[[str, str], None]] = None,
) -> str:
    """Generate a pptx_helpers Python script from *outline_text* via LLM.

    Interface mirrors pptxgenjs_gen.generate_script for drop-in use in routes.

    Parameters
    ----------
    outline_text : str
    output_script_path : str
        Where the validated .py script will be written.
    llm_client : aippt.llm.LLMClient
    theme : str
        Passed as context hint; currently informational only.
    max_retries : int
    progress_callback : callable, optional

    Returns
    -------
    str  — validated script content

    Raises
    ------
    ScriptGenerationError
    """
    base_prompt = (
        f"Generate a Python pptx_helpers script for this presentation outline.\n\n"
        f"---\n{outline_text.strip()}\n---\n\n"
        "Output ONLY the script inside a ```python code fence."
    )

    user_prompt = base_prompt
    last_reasons: list[str] = []

    for attempt in range(max_retries):
        if progress_callback:
            if attempt == 0:
                progress_callback("generate", "Generating AMD template script…")
            else:
                progress_callback(
                    "generate",
                    f"Retry {attempt}/{max_retries - 1}: {last_reasons[0] if last_reasons else 'validation failed'}",
                )

        raw = llm_client.generate_text(
            prompt=user_prompt,
            system_prompt=_SYSTEM_PROMPT,
            max_tokens=8000,
        )

        script = _extract_code_block(raw)
        ok, last_reasons = _validate_script(script)

        if ok:
            Path(output_script_path).write_text(script, encoding="utf-8")
            if progress_callback:
                progress_callback("generate", f"Script validated ({len(script)} chars)")
            return script

        user_prompt = (
            base_prompt
            + "\n\nYour previous attempt failed these checks — fix each one:\n"
            + "\n".join(f"- {r}" for r in last_reasons)
        )

    raise ScriptGenerationError(
        f"Script failed validation after {max_retries} attempt(s): "
        + "; ".join(last_reasons[:3])
    )
