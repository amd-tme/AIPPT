"""Deterministic pptxgenjs .mjs script generation from a markdown outline.

Stream C — no LLM. Parses the outline with ``aippt.parser.parse_outline``,
maps each slide to the best helper using rule-based layout selection, then
emits a validated .mjs script.

Public API mirrors ``pptxgenjs_gen.generate_script`` so callers can swap
engines transparently.
"""
from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Callable, List, Optional

from aippt.parser import parse_outline
from aippt.pptxgenjs_validate import validate_script

# ---------------------------------------------------------------------------
# Error type (mirrors pptxgenjs_gen)
# ---------------------------------------------------------------------------


class ScriptGenerationError(Exception):
    """Raised when the outline cannot be mapped to a valid script."""


# ---------------------------------------------------------------------------
# Layout classifier
# ---------------------------------------------------------------------------

# Keywords that suggest each layout — checked against title + content combined
_STAT_KEYWORDS    = re.compile(r'\b(\d+[×xX%]|\d+\.\d+[×xX]|\d+\s*TB|\d+\s*GB|\d+x\b)', re.I)
_CODE_FENCE       = re.compile(r'```')
_TWO_COLUMN_WORDS = re.compile(r'\b(vs\.?|versus|compare|comparison|before|after|left|right|pros?|cons?)\b', re.I)
_PROCESS_WORDS    = re.compile(r'\b(step\s*\d|phase\s*\d|first|second|third|then|next|finally|workflow|pipeline|process|flow)\b', re.I)
_IMAGE_DIRECTIVE  = re.compile(r'^IMAGE:\s*\S+', re.M)

# Phrases that typically anchor a title slide
_TITLE_SLIDE_PATTERNS = re.compile(
    r'\b(agenda|overview|introduction|welcome|about|presented by|confidential)\b', re.I
)


# LAYOUT: directive values (python-pptx names) → pptxgenjs helpers
_LAYOUT_DIRECTIVES = {
    'two_column':       'addTwoColumn',
    'numbered':         'addProcessFlow',
    'bullet':           'addBulletSlide',
    'basic':            'addBulletSlide',
    'diagram':          'addImageSlide',
    'title_alt':        'addTitleSlide',
    'section_content':  'addSectionDivider',
    'two_col_numbered': 'addTwoColNumbered',
}


def _bullet_lines(content: List[str]) -> List[str]:
    """Return non-empty content lines that look like bullet items."""
    return [l.lstrip('-* \t') for l in content if re.match(r'^\s*[-*•]\s+\S', l)]


def _all_text(slide: dict) -> str:
    return slide['title'] + ' ' + ' '.join(slide['content'])


def _pick_layout(slide: dict, prev_layout: str, slide_index: int, total_slides: int) -> str:
    """Choose the best pptxgenjs helper name for a slide.

    Rules applied in priority order:
    1. Explicit LAYOUT: directive in slide content → honour it
    2. IMAGE: directive → addImageSlide / addImageBulletsSlide
    3. First slide → addTitleSlide
    4. Last slide (closing keywords) → addClosingSlide
    5. Code fences in content → addCodeSlide
    6. Stats/numbers prominent → addStatCallout
    7. vs/compare signal + 2 clear halves → addTwoColumn
    8. Process/steps signal + 3-6 items → addProcessFlow
    9. 2-4 bullet items, natural groups → addCardGrid
    10. Section heading with children (kept) → addSectionDivider
    11. Fallback → addBulletSlide
    Variety rule: never repeat same layout as prev_layout (substitution applied).
    """
    title = slide['title'].lower()
    all_text = _all_text(slide).lower()
    bullets = _bullet_lines(slide['content'])
    explicit_layout = slide.get('layout', '')

    has_image = bool(slide.get('image') or _IMAGE_DIRECTIVE.search('\n'.join(slide['content'])))

    # 1. Explicit LAYOUT: directive (diagram without an image has nothing to show)
    if explicit_layout and explicit_layout in _LAYOUT_DIRECTIVES:
        layout = _LAYOUT_DIRECTIVES[explicit_layout]
        if layout == 'addImageSlide':
            if not has_image:
                return 'addBulletSlide'
            return 'addImageBulletsSlide' if bullets else 'addImageSlide'
        return layout

    # 2. IMAGE: directive
    if has_image:
        return 'addImageBulletsSlide' if bullets else 'addImageSlide'

    # 3. First slide
    if slide_index == 0:
        return 'addTitleSlide'

    # 4. Last slide
    closing_words = re.compile(r'\b(thank|thanks|closing|questions?|q\s*&\s*a|contact|goodbye|end)\b', re.I)
    if slide_index == total_slides - 1 and closing_words.search(all_text):
        return 'addClosingSlide'

    # 5. Code
    if _CODE_FENCE.search('\n'.join(slide['content'])):
        return 'addCodeSlide'

    # 6. Stats — at least one stat token in title, first bullet, or any content line
    first_line = slide['title'] + ' ' + (bullets[0] if bullets else '') + ' ' + ' '.join(slide['content'][:3])
    if _STAT_KEYWORDS.search(first_line) and len(bullets) <= 5:
        layout = 'addStatCallout'
        if layout != prev_layout:
            return layout

    # 7. Two-column — comparison signal AND even-ish bullet count
    if _TWO_COLUMN_WORDS.search(all_text) and 2 <= len(bullets) <= 8:
        layout = 'addTwoColumn'
        if layout != prev_layout:
            return layout

    # 8. Process flow — sequential signal AND 3-6 items
    if _PROCESS_WORDS.search(all_text) and 3 <= len(bullets) <= 6:
        layout = 'addProcessFlow'
        if layout != prev_layout:
            return layout

    # 9. Card grid — 2-4 bullets that each read like a named feature
    if 2 <= len(bullets) <= 4:
        layout = 'addCardGrid'
        if layout != prev_layout:
            return layout

    # 10. Section divider marker (no real content)
    if not bullets and len(slide['content']) <= 2:
        return 'addSectionDivider'

    # 11. Fallback with variety: never repeat prev
    if 'addBulletSlide' != prev_layout:
        return 'addBulletSlide'
    return 'addCardGrid'


# ---------------------------------------------------------------------------
# Per-layout code emitters
# ---------------------------------------------------------------------------

def _js_str(s: str) -> str:
    """Escape a Python string for a JS template literal or quoted string."""
    return s.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')


def _js_quoted(s: str) -> str:
    return "'" + s.replace("'", "\\'") + "'"


def _bullets_to_js_array(items: List[str]) -> str:
    """Render a Python list of strings as a JS array literal."""
    lines = [f"    {_js_quoted(item)}," for item in items]
    return '[\n' + '\n'.join(lines) + '\n  ]'


def _meta_note(layout: str) -> str:
    return (
        '[AIPPT-META]\\n'
        f'[{{"operation":"create","source":"outline -> pptxgenjs-direct","layout":"{layout}","theme":"amd"}}]\\n'
        '[/AIPPT-META]'
    )


def _emit_title(slide: dict, n: int) -> str:
    title = _js_str(slide['title'])
    bullets = _bullet_lines(slide['content'])
    subtitle = _js_str(bullets[0]) if bullets else ''
    return (
        f"// ═══ Slide {n}: {slide['title']} ═══\n"
        f"addTitleSlide(deck, `{title}`, `{subtitle}`, {n});\n"
    )


def _emit_closing(slide: dict, n: int) -> str:
    notes = _js_str(_meta_note('addClosingSlide'))
    return (
        f"// ═══ Slide {n}: {slide['title']} ═══\n"
        f"addClosingSlide(deck, {n}, `{notes}`);\n"
    )


def _emit_section_divider(slide: dict, n: int) -> str:
    # addSectionDivider(deck, sectionNumber, title, slideNum)
    title = _js_str(slide['title'])
    return (
        f"// ═══ Slide {n}: {slide['title']} ═══\n"
        f"addSectionDivider(deck, {n}, `{title}`, {n});\n"
    )


def _emit_bullet(slide: dict, n: int) -> str:
    bullets = _bullet_lines(slide['content'])
    if not bullets:
        bullets = [l.strip() for l in slide['content'] if l.strip()][:6]
    title = _js_str(slide['title'])
    notes = _js_str(_meta_note('addBulletSlide'))
    items_js = _bullets_to_js_array(bullets)
    return (
        f"// ═══ Slide {n}: {slide['title']} ═══\n"
        f"addBulletSlide(deck, `{title}`, {items_js},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_card_grid(slide: dict, n: int) -> str:
    bullets = _bullet_lines(slide['content'])
    if not bullets:
        bullets = [l.strip() for l in slide['content'] if l.strip()][:4]
    title = _js_str(slide['title'])
    notes = _js_str(_meta_note('addCardGrid'))
    # Cards: [{title, body}] — split each bullet on first ' — ' or ': '
    card_lines = []
    for b in bullets[:4]:
        m = re.match(r'^(.+?)\s*[—\-:]\s*(.+)$', b)
        if m:
            card_lines.append(
                f"    {{ title: {_js_quoted(m.group(1).strip())}, "
                f"body: {_js_quoted(m.group(2).strip())}, "
                f"shadow: cardShadow(deck.theme) }},"
            )
        else:
            card_lines.append(
                f"    {{ title: {_js_quoted(b)}, body: '', "
                f"shadow: cardShadow(deck.theme) }},"
            )
    cards_js = '[\n' + '\n'.join(card_lines) + '\n  ]'
    return (
        f"// ═══ Slide {n}: {slide['title']} ═══\n"
        f"addCardGrid(deck, `{title}`, {cards_js},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_stat_callout(slide: dict, n: int) -> str:
    bullets = _bullet_lines(slide['content'])
    # Fall back to raw non-empty content lines when no bullet-formatted items
    if not bullets:
        bullets = [l.strip() for l in slide['content'] if l.strip()]
    title = _js_str(slide['title'])
    notes = _js_str(_meta_note('addStatCallout'))
    # Stats: [{value, label}] — first bullet is the stat, rest are context
    stats = []
    for b in bullets[:3]:
        m = re.match(r'^([\d\.×xX%\+\-]+\s*\S*)\s*[—\-:]\s*(.*)$', b)
        if m:
            stats.append(
                f"    {{ value: {_js_quoted(m.group(1).strip())}, "
                f"label: {_js_quoted(m.group(2).strip())} }},"
            )
        else:
            # Use the whole bullet as label with title-derived stat
            stat_m = _STAT_KEYWORDS.search(b)
            val = stat_m.group(0) if stat_m else b[:10]
            label = b
            stats.append(
                f"    {{ value: {_js_quoted(val)}, label: {_js_quoted(label)} }},"
            )
    if not stats:
        stats = [f"    {{ value: '', label: {_js_quoted(bullets[0] if bullets else slide['title'])} }},"]
    stats_js = '[\n' + '\n'.join(stats) + '\n  ]'
    return (
        f"// ═══ Slide {n}: {slide['title']} ═══\n"
        f"addStatCallout(deck, `{title}`, {stats_js},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_two_column(slide: dict, n: int) -> str:
    bullets = _bullet_lines(slide['content'])
    title = _js_str(slide['title'])
    notes = _js_str(_meta_note('addTwoColumn'))
    # Split bullets roughly in half
    mid = max(1, len(bullets) // 2)
    left = bullets[:mid]
    right = bullets[mid:]
    if not right:
        right = ['']
    # Try to infer column headers from content
    left_h, right_h = '', ''
    vs_m = re.search(r'\b(.+?)\s+vs\.?\s+(.+)', slide['title'], re.I)
    if vs_m:
        left_h = vs_m.group(1).strip()
        right_h = vs_m.group(2).strip()
    return (
        f"// ═══ Slide {n}: {slide['title']} ═══\n"
        f"addTwoColumn(deck, `{title}`,\n"
        f"  {_js_quoted(left_h)}, {_js_quoted(right_h)},\n"
        f"  {_bullets_to_js_array(left)},\n"
        f"  {_bullets_to_js_array(right)},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_process_flow(slide: dict, n: int) -> str:
    bullets = _bullet_lines(slide['content'])
    if not bullets:
        bullets = [l.strip() for l in slide['content'] if l.strip()][:6]
    title = _js_str(slide['title'])
    notes = _js_str(_meta_note('addProcessFlow'))
    # Steps are plain strings (not objects) — join label + description with \n
    step_lines = []
    for b in bullets[:6]:
        m = re.match(r'^(.+?)\s*[—\-:]\s*(.+)$', b)
        if m:
            step_lines.append(
                f"    {_js_quoted(m.group(1).strip() + '\\n' + m.group(2).strip())},"
            )
        else:
            step_lines.append(f"    {_js_quoted(b)},")
    steps_js = '[\n' + '\n'.join(step_lines) + '\n  ]'
    return (
        f"// ═══ Slide {n}: {slide['title']} ═══\n"
        f"addProcessFlow(deck, `{title}`, {steps_js},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_two_col_numbered(slide: dict, n: int) -> str:
    # addTwoColNumbered(deck, sectionTitle, items, slideNum, notes) — the
    # helper numbers items itself, so strip any author-supplied "1." prefixes
    items = _bullet_lines(slide['content'])
    if not items:
        items = [re.sub(r'^\d+[.)]\s+', '', l.strip())
                 for l in slide['content'] if l.strip()]
    title = _js_str(slide['title'])
    notes = _js_str(_meta_note('addTwoColNumbered'))
    return (
        f"// ═══ Slide {n}: {slide['title']} ═══\n"
        f"addTwoColNumbered(deck, `{title}`, {_bullets_to_js_array(items)},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_code(slide: dict, n: int) -> str:
    title = _js_str(slide['title'])
    notes = _js_str(_meta_note('addCodeSlide'))
    # Extract fenced code block or use raw content
    content_raw = '\n'.join(slide['content'])
    fence_m = re.search(r'```\w*\n(.*?)```', content_raw, re.DOTALL)
    code = fence_m.group(1).strip() if fence_m else content_raw.strip()
    code_escaped = _js_str(code)
    return (
        f"// ═══ Slide {n}: {slide['title']} ═══\n"
        f"addCodeSlide(deck, `{title}`, `{code_escaped}`,\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_image(slide: dict, n: int) -> str:
    img_path = slide.get('image', '')
    bullets = _bullet_lines(slide['content'])
    title = _js_str(slide['title'])
    notes = _js_str(_meta_note('addImageSlide'))
    img_js = _js_quoted(img_path)
    if bullets:
        return (
            f"// ═══ Slide {n}: {slide['title']} ═══\n"
            f"addImageBulletsSlide(deck, `{title}`, {img_js},\n"
            f"  {_bullets_to_js_array(bullets)},\n"
            f"  {n}, `{notes}`);\n"
        )
    return (
        f"// ═══ Slide {n}: {slide['title']} ═══\n"
        f"addImageSlide(deck, `{title}`, {img_js}, {n}, `{notes}`);\n"
    )


_EMITTERS = {
    'addTitleSlide':     _emit_title,
    'addClosingSlide':   _emit_closing,
    'addSectionDivider': _emit_section_divider,
    'addBulletSlide':    _emit_bullet,
    'addCardGrid':       _emit_card_grid,
    'addStatCallout':    _emit_stat_callout,
    'addTwoColumn':      _emit_two_column,
    'addProcessFlow':    _emit_process_flow,
    'addCodeSlide':      _emit_code,
    'addTwoColNumbered': _emit_two_col_numbered,
    'addImageSlide':     _emit_image,
    'addImageBulletsSlide': _emit_image,
}


# ---------------------------------------------------------------------------
# Script assembler
# ---------------------------------------------------------------------------

def _build_script(outline_text: str, theme: str = 'amd') -> str:
    """Parse outline and assemble a complete .mjs script string."""
    parsed = parse_outline(outline_text)
    slides = parsed['slides']
    sections = parsed.get('sections', [])
    if not slides:
        raise ScriptGenerationError("Outline produced no slides.")

    # If the outline has H1 sections, prepend a synthetic title slide using
    # the first section name as the deck title (H1 → deck title, H2 → slides).
    if sections and slides[0].get('section'):
        deck_title_slide = {
            'title': sections[0]['name'],
            'content': [],
            'section': None,
            'layout': 'title_alt',
        }
        slides = [deck_title_slide] + slides

    # Determine layouts for all slides first (needed for variety rule)
    layouts: List[str] = []
    prev = ''
    for i, slide in enumerate(slides):
        layout = _pick_layout(slide, prev, i, len(slides))
        if layout not in _EMITTERS:
            # Never import a helper we can't emit a call for
            layout = 'addBulletSlide'
        layouts.append(layout)
        prev = layout

    slide_blocks: List[str] = []
    for i, (slide, layout) in enumerate(zip(slides, layouts), start=1):
        slide_blocks.append(_EMITTERS[layout](slide, i))

    # Import exactly the helpers the emitted code calls (an emitter may pick
    # a variant, e.g. addImageBulletsSlide, of the layout it was given)
    body = '\n'.join(slide_blocks)
    used_helpers = set(re.findall(r'^(add[A-Z]\w+)\(deck', body, re.M)) | {'createDeck'}
    if 'cardShadow(' in body:
        used_helpers.add('cardShadow')

    imports_line = (
        "import { " +
        ', '.join(sorted(used_helpers)) +
        " } from '../lib/pptxgenjs-helpers.mjs';"
    )

    deck_name = re.sub(r'[^a-z0-9]+', '-', slides[0]['title'].lower()).strip('-')[:40] or 'deck'

    script = textwrap.dedent(f"""\
        {imports_line}

        const deck = await createDeck('themes/{theme}.yaml');

        """) + '\n'.join(slide_blocks) + textwrap.dedent(f"""
        const outDir = process.env.AIPPT_PREVIEW_OUT || 'output';
        await deck.save(`${{outDir}}/{deck_name}.pptx`);
        """)

    return script


# ---------------------------------------------------------------------------
# Public API  (mirrors pptxgenjs_gen.generate_script)
# ---------------------------------------------------------------------------


def generate_script(
    outline_text: str,
    output_script_path: str,
    theme: str = 'amd',
    progress_callback: Optional[Callable[[str, str], None]] = None,
) -> str:
    """Generate a deterministic pptxgenjs .mjs script from *outline_text*.

    No LLM calls. Parses the outline, classifies each slide with rule-based
    layout selection, and emits validated helper calls.

    Parameters
    ----------
    outline_text:
        Raw markdown outline content.
    output_script_path:
        Absolute path where the script will be written.
    theme:
        Theme YAML name (default ``'amd'``).
    progress_callback:
        Optional ``(step: str, detail: str) -> None`` for SSE progress.

    Returns
    -------
    str
        The validated script content (also written to *output_script_path*).

    Raises
    ------
    ScriptGenerationError
        When the outline cannot be mapped to a valid script.
    """
    if progress_callback:
        progress_callback('generate', 'Building pptxgenjs script (deterministic)…')

    try:
        script = _build_script(outline_text, theme=theme)
    except Exception as exc:
        raise ScriptGenerationError(f"Script build failed: {exc}") from exc

    ok, reasons = validate_script(script)
    if not ok:
        # This should never happen for deterministic output — surface it clearly
        raise ScriptGenerationError(
            "Generated script failed validation (this is a bug): "
            + '; '.join(reasons)
        )

    Path(output_script_path).write_text(script, encoding='utf-8')
    if progress_callback:
        progress_callback('generate', f'Script built ({len(script)} chars, no LLM)')
    return script
