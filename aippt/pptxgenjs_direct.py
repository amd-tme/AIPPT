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
_BRAND_TITLES = {'addHeroTitleSlide', 'addProductTitleSlide'}

_MAX_AGENDA = 10
_MAX_MILESTONES = 6


def _pick_layout(slide: dict, prev_layout: str, slide_index: int, total_slides: int) -> str:
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
        return 'addTableSlide'

    # 5a. Shared slide patterns
    if _DISCLAIMER_TITLE.search(slide['title']) and (items or body['prose']):
        return 'addDisclaimerSlide'
    if body['quote'] and not items and len(body['prose']) <= 1:
        return 'addQuoteSlide'
    if (_AGENDA_TITLE.match(_md_plain(slide['title']).strip())
            and 2 <= n <= _MAX_AGENDA and not has_subs):
        return 'addAgendaSlide'
    if _looks_like_roadmap(slide):
        return 'addRoadmapSlide'
    if body['quote'] and (items or body['prose']):
        return 'addTakeawaySlide'

    # 6. Grouped content ("**Heading**" followed by its own bullets)
    groups = body['groups']
    if groups and not body['loose']:
        if len(groups) == 2 and prev_layout != 'addTwoColumn':
            return 'addTwoColumn'
        if (3 <= len(groups) <= _MAX_CARDS and prev_layout != 'addCardGrid'
                and all(len(g['items']) <= 4 for g in groups)):
            return 'addCardGrid'
        if len(groups) == 3 and all(len(g['items']) <= 4 for g in groups):
            return 'addThreeColContent'
        return 'addBulletSlide'

    # 7. Stats — every item leads with a value
    if _is_stat_slide(items) and prev_layout != 'addStatCallout':
        return 'addStatCallout'

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

    # 10. Card grid — a handful of short, flat items
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
                'addStatementSlide', 'addProofPointSlide', 'addFeatureListSlide'}
_SHOWS_TABLE = {'addTableSlide'}


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


def _tier_sequence(slides: List[dict], layouts: List[str], no_repeat: set) -> list:
    """Emission order for a 30-3-30 deck.

    Intro slides, then per tier: a PowerPoint section, a tier divider, the
    earlier tiers' slides again (unless ``TIER: no-repeat``), the tier's own
    slides and a closing slide. The appendix gets a divider and no repeats.
    Entries: ('section', name) | ('divider', title) | ('closing',) |
    ('slide', slide, layout).
    """
    seq: list = [('section', 'Intro')]
    own: dict = {}
    for slide, layout in zip(slides, layouts):
        tier = slide.get('_tier')
        if tier is None:
            seq.append(('slide', slide, layout))
        else:
            own.setdefault(tier, []).append((slide, layout))

    earlier: list = []
    for tier, entries in own.items():
        if tier == 'appendix':
            seq += [('section', 'Appendix'), ('divider', 'Appendix')]
            seq += [('slide', s, l) for s, l in entries]
            continue
        _, divider, section = _TIERS[tier]
        seq += [('section', section), ('divider', divider)]
        if tier not in no_repeat:
            seq += [('slide', s, l) for s, l in earlier]
        last_slide = entries[-1][0]
        if _CLOSING_WORDS.search(last_slide['title']):
            entries[-1] = (last_slide, 'addClosingSlide')  # author's own closing
        seq += [('slide', s, l) for s, l in entries]
        if entries[-1][1] != 'addClosingSlide':
            seq.append(('closing',))
        earlier += [e for e in entries if e[1] != 'addClosingSlide']
    return seq


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
    for i, slide in enumerate(slides):
        layout = _pick_layout(slide, prev, i, len(slides))
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

    for slide, layout in zip(slides, layouts):
        slide['_layout'] = layout
        if brand:
            slide['_brand'] = brand
        _fold_unshown(slide, layout)

    if any(slide.get('_tier') for slide in slides):
        sequence = _tier_sequence(slides, layouts, no_repeat)
    else:
        sequence = [('slide', slide, layout) for slide, layout in zip(slides, layouts)]

    deck_title = _js_str(_md_plain(slides[0]['title']))
    slide_blocks: List[str] = []
    n = 0
    for entry in sequence:
        if entry[0] == 'section':
            slide_blocks.append(f"startSection(deck, `{_js_str(entry[1])}`);\n")
            continue
        n += 1
        if entry[0] == 'divider':
            subtitle = deck_title if entry[1] != 'Appendix' else ''
            slide_blocks.append(f"// ═══ Slide {n}: {entry[1]} ═══\n"
                                f"addTierDivider(deck, `{entry[1]}`, `{subtitle}`, {n});\n")
        elif entry[0] == 'closing':
            slide_blocks.append(f"// ═══ Slide {n}: Closing ═══\naddClosingSlide(deck, {n});\n")
        else:
            # A repeated slide is emitted again from a fresh copy
            slide_blocks.append(_EMITTERS[entry[2]](copy.deepcopy(entry[1]), n))

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
