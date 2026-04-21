# Bug: Redundant Bullet Glyphs on Numbered Layout Items

**Date:** 2026-03-10
**Severity:** Minor (cosmetic)
**File:** `aippt/layouts.py`
**Function:** `_apply_bullets_to_text_frame()` (line ~441-447)

## Symptom

When using `LAYOUT: numbered`, slides render items as `• 1. Text` — both a bullet glyph AND an inline number. The bullet glyph comes from the template's paragraph-level formatting; the inline number comes from `_auto_number_content()`.

## Root Cause

In `_apply_bullets_to_text_frame()`, numbered items are placed at `p.level = 0`:

```python
num_match = re.match(r'^(\d+\.\s)', stripped)
if num_match:
    p.level = 0          # <-- inherits template's level-0 bullet glyph
    run = p.add_run()
    run.text = stripped   # <-- already contains "1. " prefix
    run.font.size = base_font_size
```

The AMD template (and most templates) define a bullet character at paragraph level 0. Since `p.level = 0` is set, the template's bullet formatting kicks in, producing `• ` before the `1. ` text.

## Fix

Suppress the template's bullet glyph for numbered items by setting `buNone` on the paragraph's XML. After setting `p.level = 0`:

```python
from pptx.oxml.ns import qn

num_match = re.match(r'^(\d+\.\s)', stripped)
if num_match:
    p.level = 0
    # Suppress template bullet glyph — the inline number serves as the marker
    pPr = p._p.get_or_add_pPr()
    pPr.append(OxmlElement('a:buNone'))
    run = p.add_run()
    run.text = stripped
    run.font.size = base_font_size
```

Or, use `buAutoNum` to let PowerPoint handle numbering natively (and strip the inline `1. ` prefix):

```python
from pptx.oxml import OxmlElement
from pptx.oxml.ns import qn

num_match = re.match(r'^(\d+\.\s)', stripped)
if num_match:
    p.level = 0
    pPr = p._p.get_or_add_pPr()
    # Remove any inherited bullet and use auto-numbering
    buAutoNum = OxmlElement('a:buAutoNum')
    buAutoNum.set('type', 'arabicPeriod')
    pPr.append(buAutoNum)
    run = p.add_run()
    run.text = stripped[num_match.end():]  # strip "1. " prefix
    run.font.size = base_font_size
```

**Recommended approach:** `buNone` is simpler and preserves the existing `_auto_number_content()` logic. `buAutoNum` is more "correct" but requires also updating the bold lead-in detection path to handle numbered items without inline prefixes.

## Affected Slides (mcp-amdsmi deck)

Slides 3, 7, 9, 10, 11, 12 — all using `LAYOUT: numbered`.

## Testing

After applying the fix, regenerate any deck with `LAYOUT: numbered` directives and verify:
- No `•` glyph before numbered items
- Numbered items still display `1. 2. 3.` prefixes
- Sub-bullets under numbered items still render correctly
- Bold lead-in detection still works on numbered items
