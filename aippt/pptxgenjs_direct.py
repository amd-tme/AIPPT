"""Deterministic pptxgenjs .mjs script generation from a markdown outline.

Stream C — no LLM. Parses the outline with ``aippt.parser.parse_outline``,
maps each slide to the best helper using rule-based layout selection, then
emits a validated .mjs script.

Public API mirrors ``pptxgenjs_gen.generate_script`` so callers can swap
engines transparently.
"""
from __future__ import annotations

import copy
import re
import textwrap
from pathlib import Path
from typing import Callable, List, Optional

from aippt import recipes as _recipes
from aippt.parser import parse_outline
from aippt.pptxgenjs_validate import validate_script

# ---------------------------------------------------------------------------
# Error type (mirrors pptxgenjs_gen)
# ---------------------------------------------------------------------------


class ScriptGenerationError(Exception):
    """Raised when the outline cannot be mapped to a valid script."""


# ---------------------------------------------------------------------------
# Slide body model
# ---------------------------------------------------------------------------

_BULLET_RE        = re.compile(r'^([ \t]*)(?:[-*•+]|(\d+)[.)])\s+(.*\S)')
_GROUP_HEAD_RE    = re.compile(r'^\*\*([^*]+?)\*\*\s*:?\s*$')
_CODE_FENCE       = re.compile(r'^\s*```')
_RULE_LINE        = re.compile(r'^(?:-{3,}|\*{3,}|_{3,})$')
_TABLE_ROW        = re.compile(r'^\|.*\|$')
_TABLE_RULE       = re.compile(r'^\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?$')
_QUOTE_LINE       = re.compile(r'^>\s?(.*)$')
_ATTRIBUTION      = re.compile(r'^(?:—|–|--?)\s*(.+)$')
_AGENDA_TITLE     = re.compile(r'^(agenda|contents|table of contents|outline|topics)$', re.I)
_ROADMAP_TITLE    = re.compile(r'\b(roadmap|timeline|milestones)\b', re.I)
_PERIOD_HEADING   = re.compile(r'^(?:[QH][1-4]\b|FY\s?\d|20\d\d\b|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b|now|next|later)', re.I)
_DISCLAIMER_TITLE = re.compile(r'\b(disclaimer|legal|notices?|attributions?)\b', re.I)
# "Lead — rest", "Lead: rest" — needs a spaced dash or colon-space so
# hyphenated words ("python-pptx") and "AMD:XYZ" are never split
_LEAD_SPLIT       = re.compile(r'^(.{1,60}?)(?:\s+[—–-]\s+|\s*[—–]\s*|:\s+)(.+)$')
# A stat-led item starts with a value that carries a unit ("3x faster",
# "50% lower cost", "192 GB HBM3", "$2M saved"); bare numbers and product
# names like MI300X / H100 don't count
_STAT_LEAD        = re.compile(
    r'^([~≈<>+]?\$?\d[\d,.]*\s?(?:[×xX%+]|[KMB]\b|[KMGTP]B\b|ms\b|µs\b)\+?)'
    r'(?:\s*[—–:-]\s*|\s+)(.+)$'
)
_TWO_COLUMN_WORDS = re.compile(r'\b(vs\.?|versus|compare|comparison|before|after|left|right|pros?|cons?)\b', re.I)
_PROCESS_WORDS    = re.compile(r'\b(step\s*\d|phase\s*\d|first|second|third|then|next|finally|workflow|pipeline|process|flow)\b', re.I)
_IMAGE_DIRECTIVE  = re.compile(r'^IMAGE:\s*\S+', re.M)
_DATE_LINE        = re.compile(r'^(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?:\d{1,2},?\s+)?20\d\d|Q[1-4]\s+20\d\d|20\d\d-\d\d(?:-\d\d)?)$', re.I)
_PRESENTER_LINE   = re.compile(r'^(?:presenter|presented by|speaker|by)\s*:?\s+(.+)$', re.I)
# Product line named in a deck title → lockup text for brand slides
_PRODUCTS         = [(re.compile(r'\brocm\b', re.I), 'ROCm'),
                     (re.compile(r'\b(instinct|mi\d{3}\w*)\b', re.I), 'Instinct'),
                     (re.compile(r'\bepyc\b', re.I), 'EPYC'),
                     (re.compile(r'\bradeon\b', re.I), 'Radeon')]
_CLOSING_WORDS    = re.compile(r'\b(thank|thanks|closing|questions?|q\s*&\s*a|contact|goodbye|end)\b', re.I)

# Most cards / process steps / stats each helper lays out cleanly
_MAX_CARDS = 6
_MAX_STEPS = 6
_MAX_STATS = 4
_MAX_CARD_TEXT = 140
_MAX_LINES = 10      # bullet-slide lines (headings + items) before splitting


def _body(slide: dict) -> dict:
    """Structured view of a slide's content, cached on the slide.

    items   top-level list items ``{'text', 'subs', 'numbered'}``
    loose   items that appear before any group heading
    groups  ``**Heading**`` lines with the items listed under them
    prose   remaining text lines, markdown stripped (subtitle / speaker
            notes — never dropped)
    code    fenced blocks ``{'label', 'code'}``; label is a heading that
            introduced the block, e.g. ``**Search:**``
    quote   ``> `` blockquote lines (a takeaway, or the quote on a quote slide)
    table   markdown pipe table ``{'header', 'rows'}`` or None
    first   'code' or 'text', whichever comes first (for split ordering)
    """
    if '_body' in slide:
        return slide['_body']
    items, loose, groups, prose, code, quote = [], [], [], [], [], []
    header, rows = None, []
    col_break = None
    first = None
    fence = None
    label = None
    for line in slide['content']:
        if fence is not None:
            if _CODE_FENCE.match(line):
                code.append({'label': label, 'code': '\n'.join(fence).rstrip()})
                fence = None
            else:
                fence.append(line)
            continue
        if _CODE_FENCE.match(line):
            fence = []
            first = first or 'code'
            # A heading with nothing under it labels the code that follows
            label = groups.pop()['heading'] if groups and not groups[-1]['items'] else None
            continue
        s = line.strip()
        if not s or _RULE_LINE.match(s):
            continue
        if s == '|||':
            col_break = len(items)
            continue
        if _TABLE_ROW.match(s):
            if _TABLE_RULE.match(s):
                if rows and header is None:
                    header = rows.pop()
                continue
            rows.append([_md_plain(c) for c in s.strip('|').split('|')])
            first = first or 'table'
            continue
        q = _QUOTE_LINE.match(s)
        if q:
            if q.group(1).strip():
                quote.append(_md_plain(q.group(1)))
            continue
        m = _BULLET_RE.match(line)
        if m:
            first = first or 'text'
            indent, num, text = m.groups()
            if len(indent.expandtabs(4)) >= 2 and items:
                items[-1]['subs'].append(text)
                continue
            item = {'text': text, 'subs': [], 'numbered': bool(num)}
            items.append(item)
            (groups[-1]['items'] if groups else loose).append(item)
            continue
        h = _GROUP_HEAD_RE.match(s)
        if h:
            groups.append({'heading': h.group(1).strip().rstrip(':').strip(), 'items': []})
            continue
        prose.append(_md_plain(s))
    if fence:  # unterminated fence — keep what we have
        code.append({'label': label, 'code': '\n'.join(fence).rstrip()})
    # Headings that ended up with no items are just text
    for g in [g for g in groups if not g['items']]:
        prose.append(_md_plain(g['heading']))
        groups.remove(g)
    table = {'header': header, 'rows': rows} if rows or header else None
    body = {'items': items, 'loose': loose, 'groups': groups, 'prose': prose,
            'code': code, 'quote': quote, 'table': table,
            'col_break': col_break, 'first': first or 'text'}
    slide['_body'] = body
    return body


def _directive(slide: dict):
    """Split ``LAYOUT: two_column | Left | Right`` into (name, [headers])."""
    parts = [p.strip() for p in (slide.get('layout') or '').split('|')]
    return parts[0].lower(), parts[1:]


def _md_plain(text: str) -> str:
    """Strip inline markdown for helpers that render text verbatim."""
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)
    text = re.sub(r'(\*\*|__)(.+?)\1', r'\2', text)
    text = re.sub(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])', r'\1', text)
    return text.replace('`', '').strip()


def _md_bullet(text: str) -> str:
    """Like _md_plain, but keep a leading ``**Lead**`` — addBulletSlide renders it."""
    m = re.match(r'^\*\*(.+?)\*\*\s*(:?)\s*(.*)$', text)
    if not m:
        return _md_plain(text)
    lead = _md_plain(m.group(1)) + m.group(2)
    rest = _md_plain(m.group(3))
    return f'**{lead}** {rest}'.rstrip()


def _split_lead(text: str):
    """'Lead — rest' → ('Lead', 'rest'); no lead-in → (text, '')."""
    plain = _md_plain(text)
    m = _LEAD_SPLIT.match(plain)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return plain, ''


def _flat_text(item: dict) -> str:
    """One-line text for an item, folding any sub-bullets in."""
    text = _md_plain(item['text'])
    if item['subs']:
        text += ': ' + '; '.join(_md_plain(s) for s in item['subs'])
    return text


def _cardable(items: List[dict]) -> bool:
    return (2 <= len(items) <= _MAX_CARDS
            and not any(it['subs'] for it in items)
            and all(len(_md_plain(it['text'])) <= _MAX_CARD_TEXT for it in items))


def _is_stat_slide(items: List[dict]) -> bool:
    return (2 <= len(items) <= _MAX_STATS
            and not any(it['subs'] for it in items)
            and all(_STAT_LEAD.match(_md_plain(it['text'])) for it in items))


# ---------------------------------------------------------------------------
# Layout classifier
# ---------------------------------------------------------------------------

# LAYOUT: directive values (python-pptx names) → pptxgenjs helpers
_LAYOUT_DIRECTIVES = {
    'two_column':        'addTwoColumn',
    'numbered':          'addProcessFlow',
    'bullet':            'addBulletSlide',
    'basic':             'addBulletSlide',
    'diagram':           'addImageSlide',
    'title_alt':         'addTitleSlide',
    'section_content':   'addSectionDivider',
    'two_col_numbered':  'addTwoColNumbered',
    'three_col_content': 'addThreeColContent',
    # Shared slide patterns
    'agenda':            'addAgendaSlide',
    'quote':             'addQuoteSlide',
    'roadmap':           'addRoadmapSlide',
    'table':             'addTableSlide',
    'takeaway':          'addTakeawaySlide',
    'disclaimer':        'addDisclaimerSlide',
    # Brand slides (AMD exec / product deck styles)
    'hero_title':        'addHeroTitleSlide',
    'product_title':     'addProductTitleSlide',
    'section_intro':     'addSectionIntroSlide',
    'statement':         'addStatementSlide',
    'proof_point':       'addProofPointSlide',
    'feature_list':      'addFeatureListSlide',
}
# Brand recipes (icon_grid, kpi_tiles, …) — aippt/brand/recipes.json
_LAYOUT_DIRECTIVES.update(_recipes.helpers())
_ENDNOTES_TITLE = re.compile(r'^\s*end\s*notes?\s*$', re.I)
_BRAND_TITLES = {'addHeroTitleSlide', 'addProductTitleSlide'}

_MAX_AGENDA = 10
_MAX_MILESTONES = 6


def _pick_layout(slide: dict, prev_layout: str, slide_index: int, total_slides: int,
                 recipes: bool = False) -> str:
    """Choose the best pptxgenjs helper name for a slide.

    Rules applied in priority order:
    1. Explicit LAYOUT: directive in slide content → honour it
    2. IMAGE: directive → addImageSlide / addImageBulletsSlide
    3. First slide → addTitleSlide
    4. Last slide (closing keywords) → addClosingSlide
    5. Code fences in content → addCodeSlide; markdown table → addTableSlide
       (slides that also carry real bullets are split beforehand, see
       _split_mixed_slides)
    5a. Disclaimer / legal title → addDisclaimerSlide; ``> quote`` with at
        most an attribution line → addQuoteSlide; Agenda title →
        addAgendaSlide; dated or Roadmap-titled groups → addRoadmapSlide;
        ``> takeaway`` with points → addTakeawaySlide
    6. Bold group headings → two groups: addTwoColumn; 3-6 small groups:
       addCardGrid (addThreeColContent for 3 after a card grid); otherwise
       addBulletSlide with sub-bullets
    7. Every item leads with a stat value → addStatCallout
    8. ``|||`` column break, or vs/compare signal → addTwoColumn
    9. Numbered list or process signal → addProcessFlow (3-6 steps),
       addTwoColNumbered (7+ numbered items)
    10. 2-6 short items → addCardGrid
    11. No items and at most one line → addSectionDivider
    12. Fallback → addBulletSlide
    A takeaway on a slide picked by directive goes to the notes when that
    layout can't draw it.
    With *recipes* (themes in recipes.json auto_themes) the brand recipes
    join in: check / spec / chart tables, Endnotes, timeline, stage flow,
    hero number, KPI tiles (for the stat callout) and icon grid.
    Variety rule: avoid repeating prev_layout where an alternative fits.
    Nothing is truncated — layouts are only chosen when all items fit.
    """
    body = _body(slide)
    items = body['items']
    n = len(items)
    has_subs = any(it['subs'] for it in items)
    explicit, _ = _directive(slide)

    has_image = bool(slide.get('image') or _IMAGE_DIRECTIVE.search('\n'.join(slide['content'])))

    # 1. Explicit LAYOUT: directive (diagram without an image has nothing to show)
    if explicit in _LAYOUT_DIRECTIVES:
        layout = _LAYOUT_DIRECTIVES[explicit]
        if layout == 'addImageSlide':
            if not has_image:
                return 'addBulletSlide'
            return 'addImageBulletsSlide' if items else 'addImageSlide'
        if layout == 'addProcessFlow' and n > _MAX_STEPS:
            return 'addTwoColNumbered'
        return layout

    # 2. IMAGE: directive
    if has_image:
        return 'addImageBulletsSlide' if items else 'addImageSlide'

    # 3. First slide
    if slide_index == 0:
        return 'addTitleSlide'

    # 4. Last slide
    if slide_index == total_slides - 1 and _CLOSING_WORDS.search(_all_text(slide)):
        return 'addClosingSlide'

    # 5. Code / table
    if body['code']:
        return 'addCodeSlide'
    if body['table']:
        return (recipes and _table_recipe(slide, body['table'])) or 'addTableSlide'

    # 5a. Endnotes (before the disclaimer check — "notes" matches both)
    if recipes and _ENDNOTES_TITLE.match(_md_plain(slide['title'])) and (items or body['prose']):
        return 'addEndnotesSlide'

    # 5a. Shared slide patterns
    if _DISCLAIMER_TITLE.search(slide['title']) and (items or body['prose']):
        return 'addDisclaimerSlide'
    if body['quote'] and not items and len(body['prose']) <= 1:
        return 'addQuoteSlide'
    if (_AGENDA_TITLE.match(_md_plain(slide['title']).strip())
            and 2 <= n <= _MAX_AGENDA and not has_subs):
        return 'addAgendaSlide'
    if _looks_like_roadmap(slide):
        if recipes and _timeline_fits(slide) and prev_layout != 'addTimeline':
            return 'addTimeline'
        return 'addRoadmapSlide'
    # (a recipe that draws the takeaway itself beats the takeaway slide)
    if body['quote'] and (items or body['prose']) and not (recipes and _recipe_takes_quote(slide)):
        return 'addTakeawaySlide'

    # 6. Grouped content ("**Heading**" followed by its own bullets)
    groups = body['groups']
    if groups and not body['loose']:
        if recipes and _stage_flow_fits(slide) and prev_layout != 'addStageFlow':
            return 'addStageFlow'
        if len(groups) == 2 and prev_layout != 'addTwoColumn':
            return 'addTwoColumn'
        if (3 <= len(groups) <= _MAX_CARDS and prev_layout != 'addCardGrid'
                and all(len(g['items']) <= 4 for g in groups)):
            return 'addCardGrid'
        if len(groups) == 3 and all(len(g['items']) <= 4 for g in groups):
            return 'addThreeColContent'
        return 'addBulletSlide'

    # 7. Stats — every item leads with a value
    stats = 'addKpiTiles' if recipes else 'addStatCallout'
    if _is_stat_slide(items) and prev_layout != stats:
        return stats
    if (recipes and n == 1 and not has_subs and len(body['prose']) <= 1
            and _STAT_LEAD.match(_md_plain(items[0]['text']))):
        return 'addHeroNumber'

    # 8. Two-column — author column break, or comparison signal
    if body['col_break'] is not None:
        return 'addTwoColumn'
    if _TWO_COLUMN_WORDS.search(_all_text(slide)) and 2 <= n <= 8 and prev_layout != 'addTwoColumn':
        return 'addTwoColumn'

    # 9. Ordered steps
    if n >= 3 and not has_subs:
        numbered = all(it['numbered'] for it in items)
        if numbered and n > _MAX_STEPS:
            return 'addTwoColNumbered'
        if ((numbered or _PROCESS_WORDS.search(_all_text(slide)))
                and n <= _MAX_STEPS and prev_layout != 'addProcessFlow'):
            return 'addProcessFlow'

    # 10. Icon grid (each item matches a brand icon), else card grid
    if recipes and prev_layout != 'addIconFeatureGrid' and _icon_items(items):
        return 'addIconFeatureGrid'
    if _cardable(items) and prev_layout != 'addCardGrid':
        return 'addCardGrid'

    # 11. Section divider marker (no real content)
    if not items and len(body['prose']) <= 1:
        return 'addSectionDivider'

    # 12. Fallback
    return 'addBulletSlide'


def _looks_like_roadmap(slide: dict) -> bool:
    """2-6 short headed groups, titled Roadmap/Timeline or headed by periods (Q1, 2026, H2…)."""
    body = _body(slide)
    groups = body['groups']
    if (body['loose'] or not 2 <= len(groups) <= _MAX_MILESTONES
            or any(len(g['items']) > 4 for g in groups)):
        return False
    return bool(_ROADMAP_TITLE.search(slide['title'])
                or all(_PERIOD_HEADING.match(g['heading']) for g in groups))


def _all_text(slide: dict) -> str:
    """Title + visible text, excluding code (so code words don't pick layouts)."""
    body = _body(slide)
    parts = [slide['title']] + body['prose'] + [g['heading'] for g in body['groups']]
    for it in body['items']:
        parts.append(it['text'])
        parts.extend(it['subs'])
    return ' '.join(parts)


_EMPTY_BODY = {'items': [], 'loose': [], 'groups': [], 'prose': [], 'code': [],
               'quote': [], 'table': None, 'col_break': None, 'first': 'text'}


def _split_mixed_slides(slides: List[dict]) -> List[dict]:
    """Split slides that mix real bullets with code or a table.

    The code and table helpers only show their block, so a slide with an
    explanation *and* a block becomes a bullet slide plus a block slide
    (same title, in the order the author wrote them) instead of losing the
    bullets. A takeaway (``> ``) stays with the bullets.
    """
    out: List[dict] = []
    for i, slide in enumerate(slides):
        body = _body(slide)
        block = 'code' if body['code'] else 'table' if body['table'] else None
        if i == 0 or block is None or len(body['items']) < 2:
            out.append(slide)
            continue
        text_slide = dict(slide, _body=dict(body, code=[], table=None))
        block_slide = {
            'title': slide['title'], 'content': [], 'section': slide.get('section'), '_tier': slide.get('_tier'),
            '_body': dict(_EMPTY_BODY, code=body['code'], table=body['table']),
        }
        out.extend([block_slide, text_slide] if body['first'] == block else [text_slide, block_slide])
    return out


def _split_dense_slides(slides: List[dict]) -> List[dict]:
    """Split slides with too many headed groups to fit on one bullet slide.

    Groups are packed in order into chunks of at most _MAX_LINES lines
    (heading + items each); later chunks get a "(cont.)" title.
    """
    out: List[dict] = []
    for slide in slides:
        body = _body(slide)
        groups = body['groups']
        sizes = [1 + sum(1 + len(it['subs']) for it in g['items']) for g in groups]
        fits_cards = 3 <= len(groups) <= _MAX_CARDS and all(len(g['items']) <= 4 for g in groups)
        if (len(groups) < 3 or body['loose'] or body['code'] or body['table'] or fits_cards
                or sum(sizes) <= _MAX_LINES or slide.get('layout')
                or _looks_like_roadmap(slide)):
            out.append(slide)
            continue
        chunks, current, used = [], [], 0
        for g, size in zip(groups, sizes):
            if current and used + size > _MAX_LINES:
                chunks.append(current)
                current, used = [], 0
            current.append(g)
            used += size
        chunks.append(current)
        for k, chunk in enumerate(chunks):
            title = slide['title'] if k == 0 else f"{slide['title']} (cont.)"
            items = [it for g in chunk for it in g['items']]
            out.append(dict(slide, title=title, _body=dict(
                body, items=items, groups=chunk, prose=body['prose'] if k == 0 else [],
                quote=body['quote'] if k == 0 else [])))
    return out


# ---------------------------------------------------------------------------
# Per-layout code emitters
# ---------------------------------------------------------------------------

def _js_str(s: str) -> str:
    """Escape a Python string for a JS template literal or quoted string."""
    return s.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')


def _js_quoted(s: str) -> str:
    s = s.replace('\\', '\\\\').replace("'", "\\'").replace('\r', '').replace('\n', '\\n')
    return "'" + s + "'"


def _js_entry(entry) -> str:
    if isinstance(entry, dict):
        subs = ', '.join(_js_quoted(s) for s in entry['subs'])
        return f"{{ text: {_js_quoted(entry['text'])}, subs: [{subs}] }}"
    return _js_quoted(entry)


def _bullets_to_js_array(items: list) -> str:
    """Render a list of strings / {text, subs} dicts as a JS array literal."""
    lines = [f"    {_js_entry(item)}," for item in items]
    return '[\n' + '\n'.join(lines) + '\n  ]'


def _notes(layout: str, extra: List[str] = ()) -> str:
    """Speaker notes: any content the layout can't show, then the meta block."""
    meta = (
        '[AIPPT-META]\n'
        f'[{{"operation":"create","source":"outline -> pptxgenjs-direct","layout":"{layout}","theme":"amd"}}]\n'
        '[/AIPPT-META]'
    )
    human = '\n'.join(line for line in extra if line)
    return _js_str(f'{human}\n\n---\n{meta}' if human else meta)


def _item_lines(items: List[dict]) -> List[str]:
    """Items as plain '- text' lines (with indented subs) for speaker notes."""
    lines = []
    for it in items:
        lines.append('- ' + _md_plain(it['text']))
        lines.extend('  - ' + _md_plain(s) for s in it['subs'])
    return lines


def _group_lines(groups: List[dict]) -> List[str]:
    lines = []
    for g in groups:
        lines.append(_md_plain(g['heading']))
        lines.extend(_item_lines(g['items']))
    return lines


def _all_lines(body: dict) -> List[str]:
    """Every piece of text content on the slide, for notes on sparse layouts."""
    lines = body['prose'] + _item_lines(body['loose']) + _group_lines(body['groups'])
    if body['code']:
        lines.append(_code_text(body))
    return lines


def _table_lines(table: dict) -> List[str]:
    rows = ([table['header']] if table['header'] else []) + table['rows']
    return [' | '.join(r) for r in rows]


# Layouts that draw the ``> takeaway`` / table themselves
_SHOWS_QUOTE = {'addTakeawaySlide', 'addTableSlide', 'addRoadmapSlide', 'addQuoteSlide',
                'addStatementSlide', 'addProofPointSlide', 'addFeatureListSlide',
                'addIconFeatureGrid', 'addKpiTiles', 'addMetricTable', 'addSpecTable',
                'addCompetitiveChart', 'addCheckMatrix', 'addTimeline', 'addStageFlow'}
_SHOWS_TABLE = {'addTableSlide', 'addMetricTable', 'addSpecTable', 'addCompetitiveChart',
                'addCheckMatrix'}


def _fold_unshown(slide: dict, layout: str) -> None:
    """Move a takeaway / table the chosen layout can't draw into prose (→ notes)."""
    body = _body(slide)
    extra = []
    if body['quote'] and layout not in _SHOWS_QUOTE:
        extra += body['quote']
    if body['table'] and layout not in _SHOWS_TABLE:
        extra += _table_lines(body['table'])
    if extra:
        slide['_body'] = dict(body, prose=extra + body['prose'], quote=[],
                              table=None if layout not in _SHOWS_TABLE else body['table'])


def _code_text(body: dict) -> str:
    blocks = []
    for block in body['code']:
        blocks.append(f"# {block['label']}\n{block['code']}" if block['label'] else block['code'])
    return '\n\n'.join(blocks)


def _header(slide: dict, n: int) -> str:
    return f"// ═══ Slide {n}: {slide['title']} ═══\n"


def _title(slide: dict) -> str:
    return _js_str(_md_plain(slide['title']))


def _emit_title(slide: dict, n: int) -> str:
    body = _body(slide)
    # Subtitle: the first line under the title, whether prose or a bullet
    lines = body['prose'] + [_md_plain(it['text']) for it in body['items']]
    subtitle = _js_str(lines[0]) if lines else ''
    rest = lines[1:]
    call = f"addTitleSlide(deck, `{_title(slide)}`, `{subtitle}`, {n})"
    if rest:
        call += f".addNotes(`{_js_str(chr(10).join(rest))}`)"
    return _header(slide, n) + call + ";\n"


def _emit_closing(slide: dict, n: int) -> str:
    # The closing helper draws a fixed logo slide — keep the author's
    # title and content as speaker notes
    notes = _notes('addClosingSlide', [_md_plain(slide['title'])] + _all_lines(_body(slide)))
    return _header(slide, n) + f"addClosingSlide(deck, {n}, `{notes}`);\n"


def _emit_section_divider(slide: dict, n: int) -> str:
    # addSectionDivider(deck, sectionNumber, title, slideNum)
    section_no = slide.get('_section_no', 1)
    call = f"addSectionDivider(deck, {section_no}, `{_title(slide)}`, {n})"
    extra = _all_lines(_body(slide))
    if extra:
        call += f".addNotes(`{_notes('addSectionDivider', extra)}`)"
    return _header(slide, n) + call + ";\n"


def _emit_bullet(slide: dict, n: int) -> str:
    body = _body(slide)
    entries: list = []
    for it in body['loose']:
        text = _md_bullet(it['text'])
        entries.append({'text': text, 'subs': [_md_plain(s) for s in it['subs']]} if it['subs'] else text)
    for g in body['groups']:
        subs = []
        for it in g['items']:
            subs.append(_md_plain(it['text']))
            subs.extend(_md_plain(s) for s in it['subs'])
        entries.append({'text': f"**{_md_plain(g['heading'])}**", 'subs': subs})
    notes_extra = list(body['prose'])
    if not entries:
        # Plain-text slide: the lines themselves are the bullets
        entries, notes_extra = list(body['prose']), []
    if body['code']:
        notes_extra.append(_code_text(body))
    notes = _notes('addBulletSlide', notes_extra)
    return (
        _header(slide, n) +
        f"addBulletSlide(deck, `{_title(slide)}`, {_bullets_to_js_array(entries)},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_card_grid(slide: dict, n: int) -> str:
    body = _body(slide)
    cards = []
    if body['groups'] and not body['loose']:
        for g in body['groups']:
            cards.append((_md_plain(g['heading']), '\n'.join(_flat_text(it) for it in g['items'])))
    elif body['items']:
        for it in body['items']:
            head, rest = _split_lead(it['text'])
            if it['subs']:
                rest = '\n'.join(filter(None, [rest] + [_md_plain(s) for s in it['subs']]))
            cards.append((head, rest))
    else:
        cards = [(_md_plain(line), '') for line in body['prose']]
    card_lines = [
        f"    {{ title: {_js_quoted(head)}, body: {_js_quoted(rest)}, "
        f"shadow: cardShadow(deck.theme) }},"
        for head, rest in cards
    ]
    cards_js = '[\n' + '\n'.join(card_lines) + '\n  ]'
    extra = body['prose'] if body['items'] else []
    notes = _notes('addCardGrid', extra)
    return (
        _header(slide, n) +
        f"addCardGrid(deck, `{_title(slide)}`, {cards_js},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_stat_callout(slide: dict, n: int) -> str:
    body = _body(slide)
    stats = []
    for it in body['items']:
        text = _flat_text(it)
        m = _STAT_LEAD.match(text)
        value, label = (m.group(1).strip(), m.group(2).strip()) if m else ('', text)
        stats.append(f"    {{ value: {_js_quoted(value)}, label: {_js_quoted(label)} }},")
    if not stats:
        stats = [f"    {{ value: '', label: {_js_quoted(_md_plain(slide['title']))} }},"]
    stats_js = '[\n' + '\n'.join(stats) + '\n  ]'
    notes = _notes('addStatCallout', body['prose'])
    return (
        _header(slide, n) +
        f"addStatCallout(deck, `{_title(slide)}`, {stats_js},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_two_column(slide: dict, n: int) -> str:
    body = _body(slide)
    _, headers = _directive(slide)
    left_h, right_h = (headers + ['', ''])[:2]
    if body['groups'] and not body['loose'] and len(body['groups']) >= 2:
        # Two groups → one per column; any extra groups join the right column
        first, *others = body['groups']
        left = [_flat_text(it) for it in first['items']]
        right = []
        for g in others:
            if right:
                right.append(f"**{_md_plain(g['heading'])}**")
            right.extend(_flat_text(it) for it in g['items'])
        left_h = left_h or _md_plain(first['heading'])
        right_h = right_h or _md_plain(others[0]['heading'])
    else:
        texts = [_flat_text(it) for it in body['items']] or list(body['prose'])
        mid = body['col_break'] if body['col_break'] is not None else (len(texts) + 1) // 2
        left, right = texts[:mid], texts[mid:]
    if not left_h and not right_h:
        vs_m = re.search(r'\b(.+?)\s+vs\.?\s+(.+)', _md_plain(slide['title']), re.I)
        if vs_m:
            left_h, right_h = vs_m.group(1).strip(), vs_m.group(2).strip()
    extra = body['prose'] if body['items'] else []
    notes = _notes('addTwoColumn', extra)
    return (
        _header(slide, n) +
        f"addTwoColumn(deck, `{_title(slide)}`,\n"
        f"  {_js_quoted(left_h)}, {_js_quoted(right_h)},\n"
        f"  {_bullets_to_js_array(left or [''])},\n"
        f"  {_bullets_to_js_array(right or [''])},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_process_flow(slide: dict, n: int) -> str:
    body = _body(slide)
    # Steps are plain strings — "Label\nDescription" gives a two-line step
    steps = []
    for it in body['items']:
        head, rest = _split_lead(it['text'])
        if it['subs']:
            rest = '; '.join(filter(None, [rest] + [_md_plain(s) for s in it['subs']]))
        steps.append(f"{head}\n{rest}" if rest else head)
    extra = list(body['prose'])
    if not steps:
        steps, extra = list(body['prose']), []
    steps_js = '[\n' + '\n'.join(f"    {_js_quoted(s)}," for s in steps) + '\n  ]'
    notes = _notes('addProcessFlow', extra)
    return (
        _header(slide, n) +
        f"addProcessFlow(deck, `{_title(slide)}`, {steps_js},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_two_col_numbered(slide: dict, n: int) -> str:
    # addTwoColNumbered(deck, sectionTitle, items, slideNum, notes) — the
    # helper numbers items itself, so author "1." prefixes are already gone
    body = _body(slide)
    items = [_flat_text(it) for it in body['items']]
    extra = list(body['prose'])
    if not items:
        items, extra = list(body['prose']), []
    notes = _notes('addTwoColNumbered', extra)
    return (
        _header(slide, n) +
        f"addTwoColNumbered(deck, `{_title(slide)}`, {_bullets_to_js_array(items)},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_three_col(slide: dict, n: int) -> str:
    # addThreeColContent(deck, title, [{heading, body}], slideNum, notes)
    body = _body(slide)
    if body['groups'] and not body['loose']:
        cols = [(_md_plain(g['heading']), '\n'.join(_flat_text(it) for it in g['items']))
                for g in body['groups']]
    else:
        cols = [_split_lead(_flat_text(it)) for it in body['items']]
    cols_js = '[\n' + '\n'.join(
        f"    {{ heading: {_js_quoted(h)}, body: {_js_quoted(b)} }}," for h, b in cols
    ) + '\n  ]'
    notes = _notes('addThreeColContent', body['prose'])
    return (
        _header(slide, n) +
        f"addThreeColContent(deck, `{_title(slide)}`, {cols_js},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_code(slide: dict, n: int) -> str:
    body = _body(slide)
    code = _code_text(body) if body['code'] else '\n'.join(slide['content']).strip()
    extra = body['prose'] + _item_lines(body['loose']) + _group_lines(body['groups'])
    notes = _notes('addCodeSlide', extra)
    return (
        _header(slide, n) +
        f"addCodeSlide(deck, `{_title(slide)}`, `{_js_str(code)}`,\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_image(slide: dict, n: int) -> str:
    img_path = slide.get('image', '')
    body = _body(slide)
    img_js = _js_quoted(img_path)
    if body['items']:
        entries = [{'text': _md_bullet(it['text']), 'subs': [_md_plain(s) for s in it['subs']]}
                   if it['subs'] else _md_bullet(it['text']) for it in body['items']]
        notes = _notes('addImageBulletsSlide', body['prose'])
        return (
            _header(slide, n) +
            f"addImageBulletsSlide(deck, `{_title(slide)}`, {img_js},\n"
            f"  {_bullets_to_js_array(entries)},\n"
            f"  {n}, `{notes}`);\n"
        )
    notes = _notes('addImageSlide', body['prose'])
    return _header(slide, n) + f"addImageSlide(deck, `{_title(slide)}`, {img_js}, {n}, `{notes}`);\n"


def _takeaway(body: dict) -> str:
    return ' '.join(body['quote'])


def _opts(**kw) -> str:
    """JS options object for the non-empty keyword values, or ''."""
    parts = [f"{k}: {_js_quoted(v)}" for k, v in kw.items() if v]
    return ', { ' + ', '.join(parts) + ' }' if parts else ''


def _emit_takeaway(slide: dict, n: int) -> str:
    # addTakeawaySlide(deck, title, takeaway, points, slideNum, notes)
    body = _body(slide)
    points: list = []
    for it in body['loose']:
        text = _md_bullet(it['text'])
        points.append({'text': text, 'subs': [_md_plain(s) for s in it['subs']]} if it['subs'] else text)
    for g in body['groups']:
        subs = []
        for it in g['items']:
            subs.append(_md_plain(it['text']))
            subs.extend(_md_plain(s) for s in it['subs'])
        points.append({'text': f"**{_md_plain(g['heading'])}**", 'subs': subs})
    extra = list(body['prose'])
    if not points:
        points, extra = list(body['prose']), []
    notes = _notes('addTakeawaySlide', extra)
    return (
        _header(slide, n) +
        f"addTakeawaySlide(deck, `{_title(slide)}`, {_js_quoted(_takeaway(body))},\n"
        f"  {_bullets_to_js_array(points)},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_table(slide: dict, n: int) -> str:
    # addTableSlide(deck, title, header, rows, slideNum, notes, {takeaway, source})
    body = _body(slide)
    table = body['table'] or {'header': None, 'rows': []}
    if not table['rows'] and not table['header']:
        # LAYOUT: table without a markdown table — one row per item
        table = {'header': None, 'rows': [list(_split_lead(_flat_text(it))) for it in body['items']]}
        extra = list(body['prose'])
    else:
        extra = body['prose'] + _item_lines(body['loose']) + _group_lines(body['groups'])
    # A trailing "Source: …" line becomes the table footnote
    source = ''
    if extra and re.match(r'^(sources?|data|footnote)\s*:', extra[-1], re.I):
        source, extra = extra[-1], extra[:-1]
    header = '[' + ', '.join(_js_quoted(c) for c in table['header']) + ']' if table['header'] else 'null'
    rows = '[\n' + '\n'.join(
        '    [' + ', '.join(_js_quoted(c) for c in r) + '],' for r in table['rows']
    ) + '\n  ]'
    notes = _notes('addTableSlide', extra)
    return (
        _header(slide, n) +
        f"addTableSlide(deck, `{_title(slide)}`, {header},\n"
        f"  {rows},\n"
        f"  {n}, `{notes}`{_opts(takeaway=_takeaway(body), source=source)});\n"
    )


def _emit_agenda(slide: dict, n: int) -> str:
    # addAgendaSlide(deck, title, items, slideNum, notes)
    body = _body(slide)
    items = [_flat_text(it) for it in body['items']] or list(body['prose'])
    extra = body['prose'] if body['items'] else []
    notes = _notes('addAgendaSlide', extra)
    brand = slide.get('_brand')
    # Brand decks get the photo agenda, labelled with the deck title
    opts = f", {{ image: '', label: {_js_quoted(brand['title'])} }}" if brand else ''
    return (
        _header(slide, n) +
        f"addAgendaSlide(deck, `{_title(slide)}`, {_bullets_to_js_array(items)},\n"
        f"  {n}, `{notes}`{opts});\n"
    )


def _emit_quote(slide: dict, n: int) -> str:
    # addQuoteSlide(deck, quote, attribution, slideNum, notes)
    body = _body(slide)
    lines = body['quote'] or body['prose'] or [_md_plain(slide['title'])]
    # "> — Name, Role" inside the quote, or a line after it, is the attribution
    attribution, quote_lines = '', list(lines)
    rest = list(body['prose']) if body['quote'] else []
    m = _ATTRIBUTION.match(quote_lines[-1]) if len(quote_lines) > 1 else None
    if m:
        attribution, quote_lines = m.group(1), quote_lines[:-1]
    elif rest:
        m = _ATTRIBUTION.match(rest[0])
        attribution, rest = (m.group(1) if m else rest[0]), rest[1:]
    extra = [_md_plain(slide['title'])] + rest + _item_lines(body['items'])
    notes = _notes('addQuoteSlide', extra)
    return (
        _header(slide, n) +
        f"addQuoteSlide(deck, {_js_quoted(' '.join(quote_lines))}, {_js_quoted(attribution)},\n"
        f"  {n}, `{notes}`);\n"
    )


def _emit_roadmap(slide: dict, n: int) -> str:
    # addRoadmapSlide(deck, title, [{heading, items}], slideNum, notes, {takeaway})
    body = _body(slide)
    if body['groups']:
        cols = [(_md_plain(g['heading']), [_flat_text(it) for it in g['items']])
                for g in body['groups']]
        extra = body['prose'] + _item_lines(body['loose'])
    else:
        # LAYOUT: roadmap on a flat list — each "**Q1** — text" item is a milestone
        cols = []
        for it in body['items']:
            head, rest = _split_lead(it['text'])
            cols.append((head, [r for r in [rest] if r] + [_md_plain(s) for s in it['subs']]))
        extra = list(body['prose'])
    cols_js = '[\n' + '\n'.join(
        f"    {{ heading: {_js_quoted(h)}, items: [{', '.join(_js_quoted(i) for i in items)}] }},"
        for h, items in cols
    ) + '\n  ]'
    notes = _notes('addRoadmapSlide', extra)
    return (
        _header(slide, n) +
        f"addRoadmapSlide(deck, `{_title(slide)}`, {cols_js},\n"
        f"  {n}, `{notes}`{_opts(takeaway=_takeaway(body))});\n"
    )


def _emit_disclaimer(slide: dict, n: int) -> str:
    # addDisclaimerSlide(deck, title, text, slideNum, notes)
    body = _body(slide)
    lines = body['prose'] + [_flat_text(it) for it in body['items']]
    for g in body['groups']:
        lines.append(_md_plain(g['heading']))
        lines.extend(_flat_text(it) for it in g['items'])
    notes = _notes('addDisclaimerSlide')
    return (
        _header(slide, n) +
        f"addDisclaimerSlide(deck, `{_title(slide)}`, `{_js_str(chr(10).join(lines))}`,\n"
        f"  {n}, `{notes}`);\n"
    )


def _product(text: str) -> str:
    for pattern, name in _PRODUCTS:
        if pattern.search(text):
            return name
    return ''


def _emit_brand_title(slide: dict, n: int) -> str:
    # addHeroTitleSlide / addProductTitleSlide(deck, title, subtitle, slideNum, opts)
    body = _body(slide)
    lines = body['prose'] + [_md_plain(it['text']) for it in body['items']]
    date = next((l for l in lines if _DATE_LINE.match(l)), '')
    presenter = next((m.group(1) for m in map(_PRESENTER_LINE.match, lines) if m), '')
    rest = [l for l in lines if l != date and not _PRESENTER_LINE.match(l)]
    subtitle, rest = (rest[0], rest[1:]) if rest else ('', [])
    if slide['_layout'] == 'addHeroTitleSlide':
        call = f"addHeroTitleSlide(deck, `{_title(slide)}`, {_js_quoted(subtitle)}, {n}{_opts(date=date)})"
    else:
        # The product title has no date slot — keep it in the notes
        rest = [date] + rest if date else rest
        product = _product(slide['title'] + ' ' + subtitle)
        call = (f"addProductTitleSlide(deck, `{_title(slide)}`, {_js_quoted(subtitle)}, {n}"
                f"{_opts(product=product, presenter=presenter)})")
    if rest:
        call += f".addNotes(`{_js_str(chr(10).join(rest))}`)"
    return _header(slide, n) + call + ";\n"


def _emit_section_intro(slide: dict, n: int) -> str:
    # addSectionIntroSlide(deck, title, body, slideNum, notes)
    body = _body(slide)
    text = body['prose'] + _item_lines(body['items'])
    return (
        _header(slide, n) +
        f"addSectionIntroSlide(deck, `{_title(slide)}`, `{_js_str(chr(10).join(text[:3]))}`,\n"
        f"  {n}, `{_notes('addSectionIntroSlide', text[3:])}`);\n"
    )


def _emit_statement(slide: dict, n: int) -> str:
    # addStatementSlide(deck, headline, subline, [{text, source}], slideNum, notes)
    # headline = the "> " line (else the title); subline = first prose line;
    # each item is a piece of evidence, its first sub-bullet the source
    body = _body(slide)
    headline = _takeaway(body) or _md_plain(slide['title'])
    prose = list(body['prose'])
    subline = prose.pop(0) if prose else ''
    evidence = []
    for it in body['items']:
        source = _md_plain(it['subs'][0]) if it['subs'] else ''
        evidence.append(f"{{ text: {_js_quoted(_md_plain(it['text']))}"
                        + (f", source: {_js_quoted(source)}" if source else '') + ' }')
    extra = ([_md_plain(slide['title'])] if body['quote'] else []) + prose
    return (
        _header(slide, n) +
        f"addStatementSlide(deck, {_js_quoted(headline)}, {_js_quoted(subline)}, [\n"
        + ''.join(f"  {e},\n" for e in evidence) +
        f"], {n}, `{_notes('addStatementSlide', extra)}`);\n"
    )


def _emit_proof_point(slide: dict, n: int) -> str:
    # addProofPointSlide(deck, headline, subline, {before, after, multiple, caption}, slideNum, notes, {label})
    # Items are "**Label** — value": the first is before, the last is after
    body = _body(slide)
    headline = _takeaway(body) or _md_plain(slide['title'])
    prose = list(body['prose'])
    subline = prose.pop(0) if prose else ''
    caption = prose.pop(0) if prose else ''
    pairs = [_split_lead(it['text']) for it in body['items']]
    pairs = [(label, value) for label, value in pairs if value]
    proof = []
    if len(pairs) >= 2:
        (bl, bv), (al, av) = pairs[0], pairs[-1]
        proof += [f"before: {{ value: {_js_quoted(bv)}, label: {_js_quoted(bl)} }}",
                  f"after: {{ value: {_js_quoted(av)}, label: {_js_quoted(al)} }}"]
        nums = [re.sub(r'[^\d.]', '', v.replace(',', '')) for v in (bv, av)]
        try:
            ratio = float(nums[1]) / float(nums[0])
            if ratio >= 1.5:
                multiple = f'{ratio:.0f}' if ratio >= 10 else f'{ratio:.1f}'.removesuffix('.0')
                proof.append(f"multiple: '{multiple}X'")
        except (ValueError, ZeroDivisionError):
            pass
        extra = [f"{l}: {v}" for l, v in pairs[1:-1]]
    else:
        extra = _item_lines(body['items'])
    if caption:
        proof.append(f"caption: {_js_quoted(caption)}")
    label = _md_plain(slide['title']) if body['quote'] else ''
    return (
        _header(slide, n) +
        f"addProofPointSlide(deck, {_js_quoted(headline)}, {_js_quoted(subline)},\n"
        f"  {{ {', '.join(proof)} }},\n"
        f"  {n}, `{_notes('addProofPointSlide', extra + prose)}`{_opts(label=label)});\n"
    )


def _emit_feature_list(slide: dict, n: int) -> str:
    # addFeatureListSlide(deck, title, tagline, [{heading, lines}], slideNum, notes, {product})
    body = _body(slide)
    prose = list(body['prose'])
    tagline = _takeaway(body) or (prose.pop(0) if prose else '')
    if body['groups']:
        feats = [(_md_plain(g['heading']), [_flat_text(it) for it in g['items']]) for g in body['groups']]
        extra = prose + _item_lines(body['loose'])
    else:
        feats = []
        for it in body['items']:
            head, rest = _split_lead(it['text'])
            feats.append((head, [r for r in [rest] if r] + [_md_plain(s) for s in it['subs']]))
        extra = prose
    feats_js = ''.join(
        f"  {{ heading: {_js_quoted(h)}, lines: [{', '.join(_js_quoted(l) for l in lines[:3])}] }},\n"
        for h, lines in feats[:4]
    )
    extra += [f"{h}: {'; '.join(lines[3:])}" for h, lines in feats if lines[3:]]
    extra += [f"{h}: {'; '.join(lines)}" for h, lines in feats[4:]]
    brand = slide.get('_brand') or {}
    product = brand.get('product') or _product(slide['title'])
    return (
        _header(slide, n) +
        f"addFeatureListSlide(deck, `{_title(slide)}`, {_js_quoted(tagline)}, [\n{feats_js}"
        f"], {n}, `{_notes('addFeatureListSlide', extra)}`{_opts(product=product)});\n"
    )


# ---------------------------------------------------------------------------
# Brand recipe emitters (aippt/brand/recipes.json)
# ---------------------------------------------------------------------------

# Lines the recipe helpers show in their source row instead of the notes
_META_LINES = {
    'source':  re.compile(r'^(?:sources?|data source)\s*:\s*(.+)$', re.I),
    'endnote': re.compile(r'^(?:see\s+)?endnotes?\s*:?\s+(\S.*)$', re.I),
    'date':    re.compile(r'^date\s*:\s*(.+)$', re.I),
    'metric':  re.compile(r'^metric\s*:\s*(.+)$', re.I),
}
_NOW_MARK = re.compile(r'\s*[(\[](?:now|current|today|we are here)[)\]]\s*$', re.I)
_ENDNOTE_ID = re.compile(r'^[A-Za-z]{0,8}[-_ ]?\d{1,4}[A-Za-z]?$|^[A-Z][A-Z0-9]*-[A-Z0-9-]+$')
_CONTEXT = re.compile(r'^(.*?)\s*\(((?:vs\.?|versus|compared|over|from|per)\b[^)]*)\)\s*$', re.I)
_MAX_ICON_ITEMS = 6
_MAX_STAGES = 4
_MAX_STAGE_BULLETS = 5


def _js(value) -> str:
    """Python value → JS literal (strings quoted, lists/dicts recursive)."""
    if isinstance(value, str):
        return _js_quoted(value)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'null'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(_js(v) for v in value) + ']'
    return '{ ' + ', '.join(f'{k}: {_js(v)}' for k, v in value.items()) + ' }'


def _js_rows(rows: list) -> str:
    """A JS array with one entry per line."""
    return '[\n' + ''.join(f'    {_js(r)},\n' for r in rows) + '  ]'


def _meta(body: dict):
    """Pull Source: / Endnote: / Date: / Metric: lines out of the prose."""
    meta, rest = {}, []
    for line in body['prose']:
        for key, pattern in _META_LINES.items():
            m = pattern.match(line)
            if m and key not in meta:
                meta[key] = m.group(1).strip()
                break
        else:
            rest.append(line)
    if 'endnote' in meta:
        ids = [i.strip() for i in re.split(r'[,;]', meta['endnote']) if i.strip()]
        meta['endnote'] = ids[0] if len(ids) == 1 else ids
    return meta, rest


def _flat_meta(value) -> str:
    return ', '.join(value) if isinstance(value, list) else value


def _recipe_opts(meta: dict, keys=('source', 'endnote'), **extra) -> str:
    """JS options object from *meta* (only *keys*) plus *extra*, skipping empty values."""
    kw = {k: meta[k] for k in keys if meta.get(k)}
    kw.update({k: v for k, v in extra.items() if v not in (None, '', [], False)})
    return f', {_js(kw)}' if kw else ''


def _recipe_call(slide: dict, n: int, helper: str, args: str, extra_notes: List[str], opts: str) -> str:
    return (_header(slide, n) +
            f"{helper}(deck, {args},\n  {n}, `{_notes(helper, extra_notes)}`{opts});\n")


def _number(cell: str) -> Optional[float]:
    """'1,234', '2.5x', '310 tok/s' → float; None when the cell is not a number."""
    m = re.match(r'^\s*[~≈]?\$?(-?\d[\d,]*(?:\.\d+)?)\s*[A-Za-z%×/]*(?:\s*[A-Za-z/]+)?\s*$', cell or '')
    return float(m.group(1).replace(',', '')) if m else None


_MARK_CELL = re.compile(r'^(?:✓|✔|✗|✘|◐|~|-|—|x|yes|no|check|partial|half|none|n/?a)?$', re.I)


def _is_mark_table(table: dict) -> bool:
    cells = [c.strip() for r in table['rows'] for c in r[1:]]
    return bool(table['header']) and any(cells) and all(_MARK_CELL.match(c) for c in cells)


def _amd_column(header: Optional[list]) -> Optional[int]:
    if not header:
        return None
    return next((i for i, h in enumerate(header) if i and _AMD_HEADER.search(h)), None)


_AMD_HEADER = re.compile(r'\b(?:AMD|Instinct|MI\d{3}\w*|EPYC|Radeon|ROCm)\b', re.I)
_PERF_TITLE = re.compile(r'\b(?:perf\w*|throughput|latency|tokens?|speed\w*|faster|benchmarks?|inference|training|tok/s|tflops|scores?)\b', re.I)


def _numeric_table(table: dict) -> bool:
    rows = table['rows']
    return (bool(table['header']) and 1 <= len(rows) <= 8 and 2 <= len(table['header']) <= 5
            and all(len(r) == len(table['header']) and all(_number(c) is not None for c in r[1:]) for r in rows))


def _table_recipe(slide: dict, table: dict) -> Optional[str]:
    """Recipe for a markdown table on an auto-recipe theme, or None for the plain table."""
    if _is_mark_table(table) and len(table['header']) <= 5:
        return 'addCheckMatrix'
    if _numeric_table(table) and _amd_column(table['header']) and _PERF_TITLE.search(slide['title']):
        return 'addCompetitiveChart'
    if _amd_column(table['header']) and 2 <= len(table['header']) <= 4 and len(table['rows']) <= 12:
        return 'addSpecTable'
    return None


def _icon_items(items: List[dict]) -> Optional[List[dict]]:
    """[{label, desc, icon}] when every item is a short 'Label — description' with a confident icon."""
    from aippt import icons
    if not 3 <= len(items) <= _MAX_ICON_ITEMS or any(it['subs'] for it in items):
        return None
    out = []
    for it in items:
        label, desc = _split_lead(it['text'])
        icon = icons.resolve(label) or icons.best_match(f'{label} {desc}')
        if not desc or len(label.split()) > 4 or not icon:
            return None
        out.append({'icon': icon, 'label': label, 'desc': desc})
    return out


def _timeline_fits(slide: dict) -> bool:
    groups = _body(slide)['groups']
    return (3 <= len(groups) <= 7
            and all(1 <= len(g['items']) <= 2 and not any(it['subs'] for it in g['items']) for g in groups))


def _stage_flow_fits(slide: dict) -> bool:
    body = _body(slide)
    groups = body['groups']
    text = slide['title'] + ' ' + ' '.join(g['heading'] for g in groups)
    return (3 <= len(groups) <= _MAX_STAGES and not body['loose']
            and all(1 <= len(g['items']) <= _MAX_STAGE_BULLETS + 1 for g in groups)
            and bool(_PROCESS_WORDS.search(text)))


def _stat(item: dict):
    """(value, label, context) for a value-led item; the lead/rest split otherwise."""
    text = _md_plain(item['text'])
    m = _STAT_LEAD.match(text)
    value, label = (m.group(1).strip(), m.group(2).strip()) if m else _split_lead(item['text'])
    context = ''
    c = _CONTEXT.match(label)
    if c:
        label, context = c.group(1).strip(), c.group(2).strip()
    if item['subs'] and not context:
        context = _md_plain(item['subs'][0])
    return value, label, context


def _recipe_takes_quote(slide: dict) -> bool:
    body = _body(slide)
    if body['groups'] and not body['loose']:
        return _stage_flow_fits(slide)
    return _is_stat_slide(body['items']) or bool(_icon_items(body['items']))


def _emit_icon_grid(slide: dict, n: int) -> str:
    # addIconFeatureGrid(deck, title, [{icon, label, desc}], slideNum, notes, {takeaway})
    from aippt import icons
    body = _body(slide)
    meta, prose = _meta(body)
    source = body['items'] or [{'text': f"**{g['heading']}** — {'; '.join(_flat_text(i) for i in g['items'])}",
                                'subs': []} for g in body['groups']]
    feats = []
    for it in source[:_MAX_ICON_ITEMS]:
        label, desc = _split_lead(it['text'])
        icon = icons.resolve(label) or icons.best_match(f'{label} {desc}')
        feats.append({k: v for k, v in (('icon', icon), ('label', label), ('desc', desc)) if v})
    # addIconFeatureGrid has no source row — Source / Endnote lines go to the notes
    extra = prose + _item_lines(source[_MAX_ICON_ITEMS:]) + [f'{k.title()}: {_flat_meta(v)}' for k, v in meta.items()]
    return _recipe_call(slide, n, 'addIconFeatureGrid', f"`{_title(slide)}`, {_js_rows(feats)}", extra,
                        _recipe_opts({}, (), takeaway=_takeaway(body)))


def _emit_kpi_tiles(slide: dict, n: int) -> str:
    # addKpiTiles(deck, title, [{value, label, context, highlight}], slideNum, notes, {takeaway, source, endnote})
    body = _body(slide)
    meta, prose = _meta(body)
    items = body['items'][:4]
    tiles = []
    for k, it in enumerate(items):
        value, label, context = _stat(it)
        tile = {'value': value, 'label': label}
        if context:
            tile['context'] = context
        if k == 0:
            tile['highlight'] = True
        tiles.append(tile)
    extra = prose + _item_lines(body['items'][4:])
    return _recipe_call(slide, n, 'addKpiTiles', f"`{_title(slide)}`, {_js_rows(tiles)}", extra,
                        _recipe_opts(meta, takeaway=_takeaway(body)))


def _emit_hero_number(slide: dict, n: int) -> str:
    # addHeroNumber(deck, value, label, slideNum, notes, {title, context, source, endnote})
    body = _body(slide)
    meta, prose = _meta(body)
    items = body['items']
    if items:
        value, label, context = _stat(items[0])
    else:
        value, label, context = _md_plain(slide['title']), (prose.pop(0) if prose else ''), ''
    extra = prose + _item_lines(items[1:]) + body['quote']
    return _recipe_call(slide, n, 'addHeroNumber', f"{_js(value)}, {_js(label)}", extra,
                        _recipe_opts(meta, title=_md_plain(slide['title']) if items else '', context=context))


def _table_or_items(body: dict):
    """(header, rows) from the markdown table, else from 'Label — value — more' items."""
    table = body['table']
    if table and (table['rows'] or table['header']):
        header, rows = table['header'], [list(r) for r in table['rows']]
        if not header and rows:
            header, rows = rows[0], rows[1:]
        return header, rows
    rows = []
    for it in body['items']:
        lead, rest = _split_lead(it['text'])
        cells = [lead] + [c.strip() for c in re.split(r'\s+[—–]\s+', rest) if c.strip()]
        rows.append(cells + [_md_plain(s) for s in it['subs']])
    return None, rows


def _emit_metric_table(slide: dict, n: int) -> str:
    # addMetricTable(deck, title, [{label, value, why}], slideNum, notes, {header, takeaway, source, endnote})
    body = _body(slide)
    meta, prose = _meta(body)
    header, rows = _table_or_items(body)
    out = []
    for r in rows[:6]:
        row = {'label': r[0] if r else '', 'value': r[1] if len(r) > 1 else ''}
        if len(r) > 2:
            row['why'] = ' '.join(r[2:])
        out.append(row)
    extra = prose + [' | '.join(r) for r in rows[6:]]
    if body['table']:
        extra += _item_lines(body['items'])
    return _recipe_call(slide, n, 'addMetricTable', f"`{_title(slide)}`, {_js_rows(out)}", extra,
                        _recipe_opts(meta, takeaway=_takeaway(body), header=(header or [])[:3]))


def _emit_spec_table(slide: dict, n: int) -> str:
    # addSpecTable(deck, title, header, rows, slideNum, notes, {takeaway, source, endnote})
    body = _body(slide)
    meta, prose = _meta(body)
    header, rows = _table_or_items(body)
    width = max([len(header or [])] + [len(r) for r in rows] + [2])
    header = list(header or ['Spec'] + [''] * (width - 1))
    rows = [r + [''] * (len(header) - len(r)) for r in rows]
    extra = prose + [' | '.join(r) for r in rows[12:]]
    if body['table']:
        extra += _item_lines(body['items'])
    return _recipe_call(slide, n, 'addSpecTable', f"`{_title(slide)}`, {_js(header)},\n  {_js_rows(rows[:12])}",
                        extra, _recipe_opts(meta, takeaway=_takeaway(body)))


def _emit_competitive_chart(slide: dict, n: int) -> str:
    # addCompetitiveChart(deck, title, categories, [{name, values}], slideNum, notes,
    #   {takeaway, metric, date, source, endnote})
    body = _body(slide)
    table = body['table']
    if not table or not _numeric_table(table):
        # LAYOUT: competitive_chart needs a numeric table — show the data as a table instead
        return _emit_table(slide, n)
    meta, prose = _meta(body)
    header, rows = table['header'], table['rows']
    series = [{'name': name, 'values': [_number(r[k]) for r in rows]}
              for k, name in enumerate(header) if k]
    categories = [r[0] for r in rows]
    extra = prose + _item_lines(body['items'])
    decimals = max((len(f'{v:g}'.partition('.')[2]) for s in series for v in s['values']), default=0)
    lower = bool(re.search(r'lower is better|latency|\btime\b', meta.get('metric') or slide['title'], re.I))
    return _recipe_call(slide, n, 'addCompetitiveChart',
                        f"`{_title(slide)}`, {_js(categories)},\n  {_js_rows(series)}", extra,
                        _recipe_opts(meta, ('source', 'endnote', 'date', 'metric'), takeaway=_takeaway(body),
                                     valueFormat='#,##0.' + '0' * min(decimals, 2) if decimals else '',
                                     lowerIsBetter=lower))


def _emit_check_matrix(slide: dict, n: int) -> str:
    # addCheckMatrix(deck, title, header, [{label, values, group}], slideNum, notes, {takeaway, source, endnote})
    body = _body(slide)
    meta, prose = _meta(body)
    header, rows = _table_or_items(body)
    out, group = [], ''
    for r in rows:
        if len(r) > 1 and not any(c.strip() for c in r[1:]) or len(r) == 1:
            group = r[0]            # a row with only its first cell filled heads a group
            continue
        row = {'label': r[0], 'values': r[1:]}
        if group:
            row['group'] = group
        out.append(row)
    width = max([len(r['values']) for r in out] + [1]) + 1
    header = list(header or ['Feature'] + [''] * (width - 1))
    extra = prose + [' | '.join([r['label']] + r['values']) for r in out[14:]]
    if body['table']:
        extra += _item_lines(body['items'])
    return _recipe_call(slide, n, 'addCheckMatrix', f"`{_title(slide)}`, {_js(header)},\n  {_js_rows(out[:14])}",
                        extra, _recipe_opts(meta, takeaway=_takeaway(body)))


def _milestone(date: str, label: str, desc: str) -> dict:
    current = bool(_NOW_MARK.search(date))
    m = {'date': _NOW_MARK.sub('', date).strip(), 'label': label}
    if desc:
        m['desc'] = desc
    if current:
        m['current'] = True
    return m


def _emit_timeline(slide: dict, n: int) -> str:
    # addTimeline(deck, title, [{date, label, desc, current}], slideNum, notes, {takeaway, source, endnote, caveat})
    body = _body(slide)
    meta, prose = _meta(body)
    milestones, extra = [], list(prose)
    if body['groups']:
        for g in body['groups']:
            texts = [_flat_text(it) for it in g['items']]
            milestones.append(_milestone(_md_plain(g['heading']), texts[0] if texts else '', ' '.join(texts[1:])))
        extra += _item_lines(body['loose'])
    else:
        for it in body['items']:
            date, rest = _split_lead(it['text'])
            label, desc = _split_lead(rest) if rest else ('', '')
            desc = ' '.join([desc] + [_md_plain(s) for s in it['subs']]).strip()
            milestones.append(_milestone(date, label, desc))
    extra += [f"{m['date']}: {m['label']} {m.get('desc', '')}".strip() for m in milestones[7:]]
    caveat = 'roadmap' in slide['title'].lower()
    return _recipe_call(slide, n, 'addTimeline', f"`{_title(slide)}`, {_js_rows(milestones[:7])}", extra,
                        _recipe_opts(meta, takeaway=_takeaway(body), caveat=caveat))


def _emit_stage_flow(slide: dict, n: int) -> str:
    # addStageFlow(deck, title, [{title, subhead, bullets}], slideNum, notes, {takeaway, closing, source, endnote})
    body = _body(slide)
    meta, prose = _meta(body)
    stages, extra = [], list(prose)
    if body['groups']:
        for g in body['groups']:
            items = list(g['items'])
            stage = {'title': _md_plain(g['heading'])}
            first = items[0]['text'].strip() if items else ''
            if len(items) > 1 and re.fullmatch(r'\*\*[^*]+\*\*:?', first):
                stage['subhead'] = _md_plain(first).rstrip(':')
                items = items[1:]
            bullets = [_flat_text(it) for it in items]
            stage['bullets'] = bullets[:_MAX_STAGE_BULLETS]
            extra += [f"{stage['title']}: {b}" for b in bullets[_MAX_STAGE_BULLETS:]]
            stages.append(stage)
        extra += _item_lines(body['loose'])
    else:
        for it in body['items']:
            head, rest = _split_lead(it['text'])
            bullets = [r for r in [rest] if r] + [_md_plain(s) for s in it['subs']]
            stages.append({'title': head, 'bullets': bullets[:_MAX_STAGE_BULLETS]})
    extra += [f"{s['title']}: {'; '.join(s['bullets'])}" for s in stages[_MAX_STAGES:]]
    return _recipe_call(slide, n, 'addStageFlow', f"`{_title(slide)}`, {_js_rows(stages[:_MAX_STAGES])}", extra,
                        _recipe_opts(meta, closing=_takeaway(body)))


def _emit_endnotes(slide: dict, n: int) -> str:
    # addEndnotesSlide(deck, title, [{id, text} | text], slideNum, notes)
    body = _body(slide)
    notes = []
    lines = [it['text'] for it in body['items']] + body['prose']
    for g in body['groups']:
        lines += [it['text'] for it in g['items']]
    for line in lines:
        lead, rest = _split_lead(line)
        if rest and _ENDNOTE_ID.match(lead):
            notes.append({'id': lead, 'text': rest})
        else:
            notes.append(_md_plain(line))
    return _recipe_call(slide, n, 'addEndnotesSlide', f"`{_title(slide)}`, {_js_rows(notes)}", [], '')


_EMITTERS = {
    'addTitleSlide':        _emit_title,
    'addClosingSlide':      _emit_closing,
    'addSectionDivider':    _emit_section_divider,
    'addBulletSlide':       _emit_bullet,
    'addCardGrid':          _emit_card_grid,
    'addStatCallout':       _emit_stat_callout,
    'addTwoColumn':         _emit_two_column,
    'addProcessFlow':       _emit_process_flow,
    'addCodeSlide':         _emit_code,
    'addTwoColNumbered':    _emit_two_col_numbered,
    'addThreeColContent':   _emit_three_col,
    'addImageSlide':        _emit_image,
    'addImageBulletsSlide': _emit_image,
    'addTakeawaySlide':     _emit_takeaway,
    'addTableSlide':        _emit_table,
    'addAgendaSlide':       _emit_agenda,
    'addQuoteSlide':        _emit_quote,
    'addRoadmapSlide':      _emit_roadmap,
    'addDisclaimerSlide':   _emit_disclaimer,
    'addHeroTitleSlide':    _emit_brand_title,
    'addProductTitleSlide': _emit_brand_title,
    'addSectionIntroSlide': _emit_section_intro,
    'addStatementSlide':    _emit_statement,
    'addProofPointSlide':   _emit_proof_point,
    'addFeatureListSlide':  _emit_feature_list,
    # Brand recipes (aippt/brand/recipes.json)
    'addIconFeatureGrid':   _emit_icon_grid,
    'addKpiTiles':          _emit_kpi_tiles,
    'addHeroNumber':        _emit_hero_number,
    'addMetricTable':       _emit_metric_table,
    'addSpecTable':         _emit_spec_table,
    'addCompetitiveChart':  _emit_competitive_chart,
    'addCheckMatrix':       _emit_check_matrix,
    'addTimeline':          _emit_timeline,
    'addStageFlow':         _emit_stage_flow,
    'addEndnotesSlide':     _emit_endnotes,
}


# ---------------------------------------------------------------------------
# Script assembler
# ---------------------------------------------------------------------------

# 30-3-30 tiers: H1 pattern → (divider title, PowerPoint section name)
_TIERS = {
    '30m': (re.compile(r'\b30[\s-]*m(?:in(?:ute)?s?)?\b', re.I), 'Deep Dive (30 Minute)', '30 Minutes'),
    '3m':  (re.compile(r'(?<!\d)3[\s-]*m(?:in(?:ute)?s?)?\b', re.I), 'Overview (3 Minute)', '3 Minutes'),
    '30s': (re.compile(r'\b30[\s-]*s(?:ec(?:ond)?s?)?\b', re.I), 'Executive Overview (30 Sec)', '30 Seconds'),
}
_APPENDIX_SECTION = re.compile(r'^\s*(?:appendix|backup)\b', re.I)
_TIER_LINE = re.compile(r'^\s*TIER:\s*(.*?)\s*$')


def _tier_of(section_name: str) -> Optional[str]:
    """Tier key for an H1 name ('30s', '3m', '30m', 'appendix') or None."""
    for key, (pattern, _, _) in _TIERS.items():
        if pattern.search(section_name):
            return key
    return 'appendix' if _APPENDIX_SECTION.match(section_name) else None


def _strip_tier_lines(outline_text: str):
    """Remove ``TIER:`` lines; return (text, tier keys marked ``no-repeat``)."""
    kept, no_repeat, tier = [], set(), None
    for line in outline_text.split('\n'):
        if line.startswith('# '):
            tier = _tier_of(line[2:].strip())
        m = _TIER_LINE.match(line)
        if m:
            if 'no-repeat' in m.group(1).lower() and tier:
                no_repeat.add(tier)
            continue
        kept.append(line)
    return '\n'.join(kept), no_repeat


def _plan(outline_text: str):
    """(slides, no-repeat tiers); 30-3-30 slides carry their tier as ``_tier``."""
    outline_text, no_repeat = _strip_tier_lines(outline_text)
    parsed = parse_outline(outline_text)
    slides = parsed['slides']
    sections = parsed.get('sections', [])
    if not slides:
        raise ScriptGenerationError("Outline produced no slides.")

    # A 30-3-30 outline has at least two of the timed H1 sections
    tiers = {sec['name']: _tier_of(sec['name']) for sec in sections}
    timed = {t for t in tiers.values() if t in _TIERS}
    if len(timed) >= 2:
        current = None
        for slide in slides:
            current = tiers.get(slide.get('section')) or current
            slide['_tier'] = current
    else:
        tiers = {}

    # If the outline has H1 sections, prepend a synthetic title slide using
    # the first section name as the deck title (H1 → deck title, H2 → slides).
    # A 30-3-30 outline that opens with a tier uses its first slide's title.
    # A 30-3-30 intro slide titled like the deck is the title slide itself.
    first = sections[0]['name'] if sections else None
    own_title = tiers and slides[0].get('section') == first and slides[0]['title'] == first
    if sections and slides[0].get('section') and not own_title:
        deck_title_slide = {
            'title': slides[0]['title'] if tiers.get(first) else first,
            'content': [],
            'section': None,
            'layout': 'title_alt',
            '_synthetic': True,
        }
        slides = [deck_title_slide] + slides
    return slides, no_repeat


def plan_slides(outline_text: str) -> List[dict]:
    """Parsed slides in the order a layout plan indexes them (deck title first)."""
    return _plan(outline_text)[0]


def _tier_sequence(slides: List[dict], items: list, no_repeat: set,
                   is_closing: Callable[[object], bool] = lambda item: item == 'addClosingSlide') -> list:
    """Emission order for a 30-3-30 deck.

    Intro slides, then per tier: a PowerPoint section, a tier divider, the
    earlier tiers' slides again (unless ``TIER: no-repeat``), the tier's own
    slides and a closing slide (unless the tier already ends with one). The
    appendix gets a divider and no repeats. *items* pairs with *slides*
    (a layout name here, a script block in the AI engine). Entries:
    ('section', name) | ('divider', title) | ('closing',) | ('slide', slide, item).
    """
    seq: list = [('section', 'Intro')]
    own: dict = {}
    for slide, item in zip(slides, items):
        tier = slide.get('_tier')
        if tier is None:
            seq.append(('slide', slide, item))
        else:
            own.setdefault(tier, []).append((slide, item))

    earlier: list = []
    for tier, entries in own.items():
        if tier == 'appendix':
            seq += [('section', 'Appendix'), ('divider', 'Appendix')]
            seq += [('slide', s, i) for s, i in entries]
            continue
        _, divider, section = _TIERS[tier]
        seq += [('section', section), ('divider', divider)]
        if tier not in no_repeat:
            seq += [('slide', s, i) for s, i in earlier]
        seq += [('slide', s, i) for s, i in entries]
        if not is_closing(entries[-1][1]):
            seq.append(('closing',))
        earlier += [e for e in entries if not is_closing(e[1])]
    return seq


def _emit_tier_frame(entry: tuple, n: int, deck_title: str) -> str:
    """Script for a sequence entry AIPPT adds itself (section, divider, closing)."""
    if entry[0] == 'section':
        return f"startSection(deck, `{_js_str(entry[1])}`);\n"
    if entry[0] == 'divider':
        subtitle = deck_title if entry[1] != 'Appendix' else ''
        return (f"// ═══ Slide {n}: {entry[1]} ═══\n"
                f"addTierDivider(deck, `{entry[1]}`, `{subtitle}`, {n});\n")
    return f"// ═══ Slide {n}: Closing ═══\naddClosingSlide(deck, {n});\n"


def _build_script(outline_text: str, theme: str = 'amd',
                  layout_plan: Optional[dict] = None) -> str:
    """Parse outline and assemble a complete .mjs script string.

    *layout_plan* maps a ``plan_slides`` index to a LAYOUT directive value
    (e.g. ``'hero_title'``). An author's own LAYOUT: line always wins.
    """
    slides, no_repeat = _plan(outline_text)
    for i, layout in (layout_plan or {}).items():
        if 0 <= i < len(slides) and (not slides[i].get('layout') or slides[i].get('_synthetic')):
            slides[i]['layout'] = layout

    slides = _split_dense_slides(_split_mixed_slides(slides))

    # Determine layouts for all slides first (needed for variety rule)
    layouts: List[str] = []
    prev = ''
    section_no = 0
    auto_recipes = theme in _recipes.auto_themes()
    for i, slide in enumerate(slides):
        layout = _pick_layout(slide, prev, i, len(slides), recipes=auto_recipes)
        if layout not in _EMITTERS:
            # Never import a helper we can't emit a call for
            layout = 'addBulletSlide'
        if layout == 'addSectionDivider':
            section_no += 1
            slide['_section_no'] = section_no
        layouts.append(layout)
        prev = layout

    # A brand title (LAYOUT: hero_title / product_title) styles the whole deck
    brand = None
    if layouts and layouts[0] in _BRAND_TITLES:
        brand = {'title': _md_plain(slides[0]['title']),
                 'product': _product(slides[0]['title'] + ' ' + ' '.join(_body(slides[0])['prose']))}

    tiered = any(slide.get('_tier') for slide in slides)
    if tiered:
        # The author's own "Thank you" ends its tier as the closing slide
        for k, slide in enumerate(slides):
            nxt = slides[k + 1].get('_tier') if k + 1 < len(slides) else None
            if slide.get('_tier') not in (None, 'appendix', nxt) and _CLOSING_WORDS.search(slide['title']):
                layouts[k] = 'addClosingSlide'

    for slide, layout in zip(slides, layouts):
        slide['_layout'] = layout
        if brand:
            slide['_brand'] = brand
        _fold_unshown(slide, layout)

    if tiered:
        sequence = _tier_sequence(slides, layouts, no_repeat)
    else:
        sequence = [('slide', slide, layout) for slide, layout in zip(slides, layouts)]

    deck_title = _js_str(_md_plain(slides[0]['title']))
    slide_blocks: List[str] = []
    n = 0
    for entry in sequence:
        n += entry[0] != 'section'
        if entry[0] == 'slide':
            # A repeated slide is emitted again from a fresh copy
            slide_blocks.append(_EMITTERS[entry[2]](copy.deepcopy(entry[1]), n))
        else:
            slide_blocks.append(_emit_tier_frame(entry, n, deck_title))

    # Import exactly the helpers the emitted code calls (an emitter may pick
    # a variant, e.g. addImageBulletsSlide, of the layout it was given)
    body = '\n'.join(slide_blocks)
    used_helpers = set(re.findall(r'^(add[A-Z]\w+)\(deck', body, re.M)) | {'createDeck'}
    for helper in ('cardShadow', 'startSection'):
        if f'{helper}(' in body:
            used_helpers.add(helper)

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
    layout_plan: Optional[dict] = None,
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
    layout_plan:
        Optional ``{slide index: LAYOUT directive}`` (see ``plan_slides``).

    Returns
    -------
    str
        The validated script content (also written to *output_script_path*).

    Raises
    ------
    ScriptGenerationError
        When the outline cannot be mapped to a valid script.
    """
    if progress_callback and layout_plan is None:
        progress_callback('generate', 'Building pptxgenjs script (deterministic)…')

    try:
        script = _build_script(outline_text, theme=theme, layout_plan=layout_plan)
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
        source = 'no LLM' if layout_plan is None else 'from AI layout plan'
        progress_callback('generate', f'Script built ({len(script)} chars, {source})')
    return script
