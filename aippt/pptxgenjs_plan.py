"""Fast AI engine: the LLM picks a layout per slide, the deterministic engine emits it.

One short LLM call returns a JSON layout plan (``{"slides": [{"i": 0,
"layout": "hero_title"}, ...]}``). The plan is checked against the known
LAYOUT directives and handed to ``pptxgenjs_direct``, which writes every
helper call from the outline text unchanged. Invalid entries are dropped and
an unusable reply falls back to the rule-based layouts, so the engine never
fails because of the LLM.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Dict, List, Optional, Tuple

from aippt import recipes as _recipes
from aippt.pptxgenjs_direct import (
    _SHOWS_QUOTE,
    ScriptGenerationError,
    generate_script as _direct_generate_script,
    plan_slides,
)

__all__ = ['ScriptGenerationError', 'generate_script', 'build_prompt', 'parse_plan']

# LAYOUT directive → when to use it (shown to the LLM)
_LAYOUTS = {
    'title_alt': 'standard deck title (internal, technical or training decks)',
    'hero_title': 'brand hero title: exec pitch, keynote, customer-facing strategy',
    'product_title': 'brand product title: deck about one named product (Instinct, ROCm, EPYC, Radeon)',
    'agenda': 'agenda / contents list',
    'section_content': 'section divider (one short line)',
    'bullet': 'plain bullet list',
    'two_column': 'two-sided comparison; add headers as "two_column | Left | Right"',
    'numbered': 'ordered process or steps (3-6)',
    'two_col_numbered': '4-8 numbered points in two columns',
    'three_col_content': 'exactly three parallel groups',
    'table': 'rows x columns data (the outline has a markdown table)',
    'takeaway': 'bullets plus a one-line takeaway (the outline has a > quote line)',
    'quote': 'a single quote or testimonial',
    'roadmap': 'dated milestones or a timeline',
    'disclaimer': 'legal / notices text',
    'section_intro': 'BRAND ONLY: section opener with a short intro paragraph',
    'statement': 'BRAND ONLY: one bold claim, optional evidence bullets with sources',
    'proof_point': 'BRAND ONLY: before/after metric pair ("**A** — 100", "**B** — 60")',
    'feature_list': 'BRAND ONLY: 2-4 product features with short descriptions',
}
# Brand recipes (aippt/brand/recipes.json): "when; not for …; capacity"
_LAYOUTS.update({r['id']: f"{r['when']}; not for {r['when_not']} ({r['capacity']})"
                 for r in _recipes.recipes()})
_LAYOUTS['auto'] = 'let the engine decide (cards, stats, code and images are detected automatically)'
# Recipes that draw the "> " takeaway themselves
_TAKEAWAY_RECIPES = [r['id'] for r in _recipes.recipes() if r['helper'] in _SHOWS_QUOTE]
# Recipes that draw a markdown table — dropped on a slide without one
_NEEDS_TABLE = {'spec_table', 'check_matrix', 'competitive_chart'}
_BRAND_TITLES = ('hero_title', 'product_title')
_BRAND_ONLY = {'section_intro', 'statement', 'proof_point', 'feature_list'}
_TITLES = {'title_alt', *_BRAND_TITLES}

_SYSTEM_PROMPT = 'You plan slide layouts. Reply with one JSON object and nothing else.'
_MAX_LISTED_LINES = 12


def build_prompt(slides: List[dict]) -> str:
    """User prompt listing every slide (index, title, first lines) and the layouts."""
    table = '\n'.join(f'- {name}: {use}' for name, use in _LAYOUTS.items())
    listing = '\n\n'.join(
        f'[{i}] {s["title"]}\n' + '\n'.join(s.get('content', [])[:_MAX_LISTED_LINES])
        for i, s in enumerate(slides))
    return f"""Pick one layout per slide for this outline.

Layouts:
{table}

Rules:
- Slide 0 is the deck title: choose title_alt, hero_title or product_title.
- BRAND ONLY layouts are allowed only when slide 0 is hero_title or product_title.
- spec_table, check_matrix and competitive_chart need a markdown table on the slide.
- {', '.join(_TAKEAWAY_RECIPES)} also show the > takeaway line; prefer one of them over takeaway when the content fits it.
- Use "auto" when unsure; the engine detects cards, stats, code and images itself.
- You only choose layouts; the slide text is used exactly as written.

Slides:
{listing}

Reply exactly as: {{"slides": [{{"i": 0, "layout": "..."}}, ...]}}"""


def _has_table(slide: dict) -> bool:
    return any(line.strip().startswith('|') for line in slide.get('content', []))


def parse_plan(raw: str, slide_count: int,
               slides: Optional[List[dict]] = None) -> Tuple[Dict[int, str], List]:
    """Turn the LLM reply into ``{index: directive}``; return (plan, dropped entries).

    Unknown layouts, bad indexes, a non-title layout on slide 0 or a title
    layout elsewhere, brand-only layouts in a non-brand deck and (given
    *slides*) a table recipe on a slide without a table are dropped (those
    slides fall back to the rule-based choice).
    """
    match = re.search(r'\{.*\}', raw or '', re.S)
    try:
        entries = json.loads(match.group(0)).get('slides', []) if match else []
    except (json.JSONDecodeError, AttributeError):
        entries = []
    if not isinstance(entries, list):
        entries = []

    plan: Dict[int, str] = {}
    dropped: List = []
    for entry in entries:
        i = entry.get('i') if isinstance(entry, dict) else None
        layout = str(entry.get('layout', '')).strip() if isinstance(entry, dict) else ''
        name = layout.split('|')[0].strip().lower()
        valid_index = isinstance(i, int) and not isinstance(i, bool) and 0 <= i < slide_count
        if not valid_index or name not in _LAYOUTS:
            dropped.append(entry)
        elif name != 'auto' and (name in _TITLES) != (i == 0):
            dropped.append(entry)  # title layouts belong on slide 0 only
        elif name in _NEEDS_TABLE and slides is not None and not _has_table(slides[i]):
            dropped.append(entry)
        elif name != 'auto':
            plan[i] = layout if name == 'two_column' else name

    brand = plan.get(0) in _BRAND_TITLES
    for i in [i for i, layout in plan.items() if layout.split('|')[0].strip() in _BRAND_ONLY]:
        if not brand:
            dropped.append({'i': i, 'layout': plan.pop(i)})
    return plan, dropped


def generate_script(
    outline_text: str,
    output_script_path: str,
    llm_client,
    theme: str = 'amd',
    progress_callback: Optional[Callable[[str, str], None]] = None,
) -> str:
    """Generate a pptxgenjs .mjs script from one LLM layout plan.

    Same signature and return value as ``pptxgenjs_direct.generate_script``
    plus *llm_client*. Raises ``ScriptGenerationError`` only when the outline
    itself cannot be built (an LLM failure falls back to rule-based layouts).
    """
    slides = plan_slides(outline_text)
    if progress_callback:
        progress_callback('generate', f'Planning layouts for {len(slides)} slides…')

    plan: Dict[int, str] = {}
    try:
        raw = llm_client.generate_text(
            prompt=build_prompt(slides),
            system_prompt=_SYSTEM_PROMPT,
            max_tokens=2000,
            temperature=0.2,
        )
        plan, dropped = parse_plan(raw, len(slides), slides)
        if progress_callback:
            note = f', {len(dropped)} ignored' if dropped else ''
            progress_callback('generate', f'Layout plan ready ({len(plan)} picks{note})')
    except Exception as exc:  # any LLM/gateway error: keep going without a plan
        if progress_callback:
            progress_callback('generate', f'Layout plan unavailable ({exc}); using rule-based layouts')

    return _direct_generate_script(
        outline_text=outline_text,
        output_script_path=output_script_path,
        theme=theme,
        progress_callback=progress_callback,
        layout_plan=plan,
    )
