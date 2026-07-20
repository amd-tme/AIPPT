"""Generate a validated pptxgenjs .mjs script from a markdown outline.

Implements Approach B from PRD 2026-07-17-web-pptxgenjs-generation.md:
  outline → LLM → candidate script → validate → retry if invalid → write to disk

The LLM is prompted with the create-deck skill's Critical Rules and Layout
Decision Strategy so the generated script matches what the skill produces
interactively.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from aippt.pptxgenjs_validate import validate_script

# ---------------------------------------------------------------------------
# Public error type
# ---------------------------------------------------------------------------


class ScriptGenerationError(Exception):
    """Raised when the LLM cannot produce a valid script within max_retries."""


# ---------------------------------------------------------------------------
# System prompt — embeds Critical Rules + Layout Decision Strategy
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert slides-as-code generator for AIPPT. Your job is to read a
markdown presentation outline and produce a complete, runnable pptxgenjs .mjs
script that uses the AIPPT helper library.

## Available helper functions (import from '../lib/pptxgenjs-helpers.mjs')

createDeck(themePath, opts?)           — initialise deck, returns deck object
addTitleSlide(deck, title, subtitle, slideNum)
addBulletSlide(deck, title, bullets, slideNum, notes)
addTwoColumn(deck, title, leftHeader, rightHeader, leftItems, rightItems, slideNum, notes, opts?)
addCardGrid(deck, title, cards, slideNum, notes)
addStatCallout(deck, title, stats, slideNum, notes)
addProcessFlow(deck, title, steps, slideNum, notes)
addIconRowsSlide(deck, title, items, iconImages, slideNum, notes)
addImageSlide(deck, title, imagePath, slideNum, notes, opts?)
addImageBulletsSlide(deck, title, imagePath, bullets, slideNum, notes)
addCodeSlide(deck, title, code, slideNum, notes)
addSectionDivider(deck, sectionNumber, title, slideNum)
addClosingSlide(deck, slideNum, notes)
cardShadow(theme)                      — shadow factory (never reuse objects)

Optional: import { masterNameFor } from '../lib/pptxgenjs-masters.mjs'

## Script skeleton

```javascript
import { createDeck, addTitleSlide, addBulletSlide, /* ... */ } from '../lib/pptxgenjs-helpers.mjs';

const deck = await createDeck('themes/amd.yaml');

// ═══ Slide 1: <title> ═══
addTitleSlide(deck, '<title>', '<subtitle>', 1);

// ═══ Slide N: <title> ═══
// ... one helper call per slide

const outDir = process.env.AIPPT_PREVIEW_OUT || 'output';
await deck.save(`${outDir}/<sanitized-title>.pptx`);
```

## Critical Rules — violating these corrupts the PPTX file

- NEVER use `#` prefix on hex colors → use '00C2DE' not '#00C2DE'
- NEVER use 8-character hex colors (opacity in hex) → use rgba() instead
- NEVER reuse option objects (especially shadows) → always call cardShadow(deck.theme)
- ALWAYS use `bullet: true` instead of unicode bullet characters
- ALWAYS use `breakLine: true` between text array items
- ALWAYS use `pptx.layout = "LAYOUT_WIDE"` — NEVER use LAYOUT_16x9
- ALWAYS define safe-area constants: SW=13.33, SH=7.5 — validate all positions
- ALWAYS add a slide marker comment before each slide: // ═══ Slide N: Title ═══
- ALWAYS save to `process.env.AIPPT_PREVIEW_OUT || 'output'` — NEVER hardcode 'output/' alone
- NEVER use eval(), Function(), child_process, fs, net, http, setTimeout, setInterval
- NEVER use dynamic import()
- Only import from: '../lib/pptxgenjs-helpers.mjs', '../lib/pptxgenjs-masters.mjs', 'path', 'url'

## AMD Theme — Corporate Match (default)

- Backgrounds: PURE BLACK (000000) — no blue tones
- No decorative shapes on content slides
- No section dividers — skip section headings that have no slide children
- All text: WHITE — titles bold ~28-32pt, body ~18-20pt
- Font: Arial for both headings and body
- Footer: slide number bottom-left, AMD wordmark bottom-right
- Title slide: AMD arrow logo left half, title text right, logo+tagline bottom-right
- Closing slide: large centered AMD wordmark; suppress footer logo and number

## Layout Decision Strategy

Map each slide's content to the best layout:

| Content Signal | Layout |
|---|---|
| First heading in outline | addTitleSlide |
| Section heading (no children, corp-match) | SKIP — do not render |
| 3-4 bullets with bold lead-ins (Key: value) | addCardGrid |
| Prominent number or statistic | addStatCallout |
| Code blocks or CLI commands | addCodeSlide |
| LAYOUT: two_column or ||| separator | addTwoColumn |
| LAYOUT: numbered or sequential steps | addProcessFlow |
| 3 parallel items with headings | addCardGrid (3 cards) |
| Standard bullet list | addBulletSlide |
| IMAGE: with no bullets | addImageSlide |
| IMAGE: with bullets | addImageBulletsSlide |
| Last slide / thank you | addClosingSlide |

Variety Rule: never use the same layout on two consecutive slides.
Substitution: bullet→bullet: use addCardGrid or addIconRowsSlide for the second.

## Speaker Notes Metadata

Add this block to the notes string of every slide:

```
[AIPPT-META]
[{"operation":"create","source":"outline -> pptxgenjs","layout":"<layout>","theme":"amd"}]
[/AIPPT-META]
```

## Output format

Respond with ONLY the .mjs script inside a ```javascript code fence and nothing else.
Do not include any explanation, preamble, or text outside the code fence.
"""


# ---------------------------------------------------------------------------
# Code-block extractor
# ---------------------------------------------------------------------------

_CODE_FENCE_RE = re.compile(
    r"```(?:javascript|js|mjs|typescript)?\s*\n(.*?)```",
    re.DOTALL,
)


def _extract_code_block(text: str) -> str:
    """Strip surrounding ```javascript fences from LLM output."""
    m = _CODE_FENCE_RE.search(text)
    return m.group(1).strip() if m else text.strip()


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
    """Generate and validate a pptxgenjs .mjs script from *outline_text*.

    Parameters
    ----------
    outline_text:
        Raw markdown outline content.
    output_script_path:
        Absolute path where the validated script will be written.
    llm_client:
        An ``aippt.llm.LLMClient`` instance (gateway-aware).
    theme:
        Theme name — currently only ``"amd"`` is used in v1.
    max_retries:
        Number of LLM generation attempts before raising.
    progress_callback:
        Optional ``(step: str, detail: str) -> None`` for SSE progress.

    Returns
    -------
    str
        The validated script content (also written to *output_script_path*).

    Raises
    ------
    ScriptGenerationError
        When the script fails validation after all retries.
    """
    user_prompt = (
        f"Generate a pptxgenjs .mjs script for the following presentation outline.\n"
        f"Theme: {theme}\n\n"
        f"---\n{outline_text.strip()}\n---\n\n"
        "Output ONLY the script inside a ```javascript code fence."
    )

    last_reasons: list[str] = []
    for attempt in range(max_retries):
        if progress_callback:
            if attempt == 0:
                progress_callback("generate", "Generating pptxgenjs script…")
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
        ok, last_reasons = validate_script(script)

        if ok:
            Path(output_script_path).write_text(script, encoding="utf-8")
            if progress_callback:
                progress_callback("generate", f"Script validated ({len(script)} chars)")
            return script

    # All retries exhausted
    reasons_str = "; ".join(last_reasons[:3])
    raise ScriptGenerationError(
        f"Script failed validation after {max_retries} attempt(s): {reasons_str}"
    )
