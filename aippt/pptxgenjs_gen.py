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

from aippt.pptxgenjs_validate import (
    _CALL_START, _helper_signatures, _scan_until, _skip_comment, _skip_quoted,
    _skip_template, validate_script,
)

# ---------------------------------------------------------------------------
# Public error type
# ---------------------------------------------------------------------------


class ScriptGenerationError(Exception):
    """Raised when the LLM cannot produce a valid script within max_retries."""


# ---------------------------------------------------------------------------
# System prompt — embeds Critical Rules + Layout Decision Strategy
# ---------------------------------------------------------------------------

_EXAMPLE_SCRIPT = """\
import { createDeck, cardShadow, addTitleSlide, addAgendaSlide, addCardGrid,
  addStatCallout, addTableSlide, addProcessFlow, addQuoteSlide, addRoadmapSlide,
  addClosingSlide } from '../lib/pptxgenjs-helpers.mjs';

const deck = await createDeck('themes/amd.yaml');

// ═══ Slide 1: Faster Inference on MI300X ═══
addTitleSlide(deck, `Faster Inference on MI300X`, `What changed and what's next`, 1);

// ═══ Slide 2: Agenda ═══
addAgendaSlide(deck, `Agenda`, [`Why it matters`, `Results`, `How it works`, `Roadmap`], 2,
  `Four parts, about ten minutes.`);

// ═══ Slide 3: Why It Matters ═══
addCardGrid(deck, `Why It Matters`, [
  { title: `Memory`, body: `192 GB HBM3 fits 70B models on one GPU.`, shadow: cardShadow(deck.theme) },
  { title: `Cost`, body: `Fewer GPUs per replica lowers serving cost.`, shadow: cardShadow(deck.theme) },
  { title: `Open`, body: `ROCm runs today's PyTorch and vLLM stacks.`, shadow: cardShadow(deck.theme) },
], 3, `Lead with memory capacity — it's the headline difference.`);

// ═══ Slide 4: Results ═══
addStatCallout(deck, `Results`, [
  { value: `2.1x`, label: `Throughput`, desc: `vs. last release` },
  { value: `-38%`, label: `Latency`, desc: `p95, batch 32` },
], 4, `Numbers from the internal benchmark run.`);

// ═══ Slide 5: Configurations Tested ═══
addTableSlide(deck, `Configurations Tested`, [`Model`, `GPUs`, `Tokens/s`],
  [[`Llama 3 70B`, `1`, `2,450`], [`Mixtral 8x7B`, `1`, `3,900`]], 5,
  `Same driver and container for every row.`,
  { takeaway: `One GPU now serves a 70B model.`, source: `Source: internal benchmarks` });

// ═══ Slide 6: How It Works ═══
addProcessFlow(deck, `How It Works`, [`Quantize\nFP8 weights`, `Shard\nTensor parallel`, `Serve\nvLLM on ROCm`], 6,
  `Walk left to right.`);

// ═══ Slide 7: Customer Quote ═══
addQuoteSlide(deck, `We cut our serving fleet in half without touching the model code.`,
  `Jane Doe, VP Engineering`, 7, `Use with permission only.`);

// ═══ Slide 8: Roadmap ═══
addRoadmapSlide(deck, `Roadmap`, [
  { heading: `Q1`, items: [`FP8 by default`] },
  { heading: `Q2`, items: [`Multi-node serving`, `Speculative decoding`] },
], 8, `Dates are targets, not commitments.`);

// ═══ Slide 9: Thank You ═══
addClosingSlide(deck, 9, `Questions?`);

const outDir = process.env.AIPPT_PREVIEW_OUT || 'output';
await deck.save(`${outDir}/faster-inference-on-mi300x.pptx`);
"""

_SYSTEM_PROMPT = """\
You are an expert slides-as-code generator for AIPPT. Your job is to read a
markdown presentation outline and produce a complete, runnable pptxgenjs .mjs
script that uses the AIPPT helper library.

## Available helper functions (import from '../lib/pptxgenjs-helpers.mjs')

createDeck(themePath, opts?)           — initialise deck, returns deck object
addTitleSlide(deck, title, subtitle, slideNum)
addTitleAlt(deck, title, subtitle, slideNum)           — alternate title layout
addBulletSlide(deck, title, bullets, slideNum, notes)   — bullets=string[] or {text, subs: string[]}
addTwoColumn(deck, title, leftHeader, rightHeader, leftItems, rightItems, slideNum, notes, opts?)   — items=string[]
addTwoColNumbered(deck, sectionTitle, items, slideNum, notes)   — items=string[]; the helper numbers them (don't add "1.")
addCardGrid(deck, title, cards, slideNum, notes)   — cards=[{title, body, accent?, iconImg?}] × 2-6
addStatCallout(deck, title, stats, slideNum, notes)   — stats=[{value, label, desc?, color?}] × 1-4
addProcessFlow(deck, title, steps, slideNum, notes)
addIconRowsSlide(deck, title, items, iconImages, slideNum, notes)   — items=[{label, desc}]
addLogoGridSlide(deck, title, items, iconImages, brandColors, slideNum, notes?)
  — partner/ecosystem logo grid; items=[{name, description}], iconImages=preRendered[], brandColors=hex[]
addImageSlide(deck, title, imagePath, slideNum, notes, opts?)
addImageBulletsSlide(deck, title, imagePath, bullets, slideNum, notes)
addTitleWithImage(deck, title, subtitle, imagePath, slideNum)   — no notes argument; chain .addNotes(notes)
addSplitImageContent(deck, title, bullets, imagePath, slideNum, notes)   — bullets BEFORE imagePath
addCodeSlide(deck, title, code, slideNum, notes)
addSectionDivider(deck, sectionNumber, title, slideNum)
addSectionContent(deck, sectionTitle, bullets, slideNum, notes)  — bullets MUST be an array of strings, never a plain string
addCinematicSlide(deck, title, imagePath, slideNum, notes)
addThreeColContent(deck, title, columns, slideNum, notes)   — columns=[{heading, body}] × exactly 3; body is a string
addThreeColImageText(deck, title, columns, slideNum, notes)   — columns=[{heading, imagePath?, body}] × 3
addTwoImageGallery(deck, title, items, slideNum, notes)     — items=[{imagePath?, caption}] × exactly 2
addThreeImageGallery(deck, title, items, slideNum, notes)   — items=[{imagePath?, caption}] × 3
addFourImageGallery(deck, title, items, slideNum, notes)    — items=[{imagePath?, caption}] × exactly 4
addPictureCaption(deck, title, imagePath, caption, slideNum, notes)
addClosingSlide(deck, slideNum, notes)
cardShadow(theme)                      — shadow factory (never reuse objects)

Shared slide patterns (a one-line takeaway is the slide's key message, drawn
in accent colour under the title):
addTakeawaySlide(deck, title, takeaway, points, slideNum, notes)
  — points = string[] or {text, subs: string[]}; "**Lead** — rest" bolds the lead
addTableSlide(deck, title, header, rows, slideNum, notes, opts?)
  — header=string[] (or null), rows=string[][]; opts={takeaway?, source?}
    (source = footnote, e.g. 'Source: AMD spec sheets'); best with ≤10 rows, ≤6 columns
addAgendaSlide(deck, title, items, slideNum, notes, opts?)
  — items=string[] (≤10); opts={current?: 1-based index to highlight}
addQuoteSlide(deck, quote, attribution, slideNum, notes)
  — attribution without a leading dash, e.g. 'Jane Doe, CTO'
addRoadmapSlide(deck, title, columns, slideNum, notes, opts?)
  — columns=[{heading, items: string[]}] × 2-6 (heading = Q1 / 2026 / Phase 1); opts={takeaway?}
addDisclaimerSlide(deck, title, text, slideNum, notes)   — legal text (string, \\n between paragraphs; auto-sized)
  addAgendaSlide opts also take {image: '', label: 'Deck name'} for the photo agenda
  (image '' = bundled photo); use it when the deck uses addHeroTitleSlide/addProductTitleSlide.

Brand slides (AMD exec / product deck styles; bundled photos are used when no image is given):
addHeroTitleSlide(deck, title, subtitle, slideNum, opts?)
  — full-bleed photo title; opts={date?, image?, footnote?} (footnote = small legal line along the bottom, only if the outline has one). Use "\n" in title to break it into 2 lines.
addProductTitleSlide(deck, title, subtitle, slideNum, opts?)
  — product render + product lockup title; opts={product?: 'ROCm'|'Instinct'|'EPYC'|…, presenter?, image?}. A title like 'AMD Instinct – AI Platform' or 'X: Y' draws the lead smaller and the main line large.
addSectionIntroSlide(deck, title, body, slideNum, notes, opts?)
  — section opener: title + 1-3 sentence description (string) beside a photo; opts={image?}
addStatementSlide(deck, headline, subline, evidence, slideNum, notes)
  — big two-tone claim (accent headline + white subline) beside cited evidence;
    evidence=[{text, source?}] × 1-4
addProofPointSlide(deck, headline, subline, proof, slideNum, notes, opts?)
  — one before/after metric as the slide's message;
    proof={before: {value, label}, after: {value, label}, multiple?: '4X', caption?}; opts={label?}
addFeatureListSlide(deck, title, tagline, features, slideNum, notes, opts?)
  — product-branded header (lockup | title + accent tagline) with features=[{heading, lines: string[]}] × 2-4;
    opts={product?, image?}

Optional: import { masterNameFor } from '../lib/pptxgenjs-masters.mjs'

Note on `steps` (addProcessFlow): unlike `cards` (addCardGrid), which takes an
array of objects, `steps` takes an array of PLAIN STRINGS — one per step.
To show a bold label plus description, join them with a literal newline in
the string: "Label\nDescription text". Do NOT pass {label, description}
objects here.

Note on `addLogoGridSlide`: requires pre-rendered icon images from
`preRenderIcons()`. Only use it when you have actual brand/partner logos to
show — do NOT fabricate icon data. If no icons are available, use addCardGrid
with text-only cards instead.

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

{example}

## Critical Rules — violating these corrupts the PPTX file

- NEVER use `#` prefix on hex colors → use '00C2DE' not '#00C2DE'
- NEVER use 8-character hex colors (opacity in hex) → use rgba() instead
- NEVER reuse option objects (especially shadows) → always call cardShadow(deck.theme)
- ALWAYS use `bullet: true` instead of unicode bullet characters
- ALWAYS use `breakLine: true` between text array items
- createDeck() already sets LAYOUT_WIDE (13.33" × 7.5") — never set pptx.layout yourself, and never use LAYOUT_16x9
- Build every slide with the helpers above — no raw deck.pptx.addSlide() / addText() calls
- Write slide text in backtick template literals (`...`) so apostrophes like `today's` can't break the string
- Call each helper with exactly the arguments in its signature, in that order
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
| First heading in outline | a title slide — see "Choosing the title slide" |
| Section heading (no children, corp-match) | SKIP — do not render |
| 2-4 named items / features / use cases | addCardGrid |
| Prominent number or statistic | addStatCallout |
| Code blocks or CLI commands | addCodeSlide |
| Markdown table / spec or feature comparison grid | addTableSlide (keep every cell; never invent values) |
| Slide with a `> ` blockquote line + supporting points | addTakeawaySlide (the blockquote is the takeaway) |
| Agenda / contents / outline of the deck | addAgendaSlide (photo variant with a brand title) |
| Section opener that has a 1-3 sentence description | addSectionIntroSlide (brand decks only) |
| A claim backed by 1-4 facts, quotes or cited stats (often with `Source:` lines) | addStatementSlide (brand decks only; each fact = evidence; a `Source:` sub-bullet = its source) |
| Two values of one metric to compare (old vs new, them vs us, gen vs gen) | addProofPointSlide (brand decks only; first = before, second = after) |
| Product pillars / value props, each a heading + 1-3 short lines | addFeatureListSlide (brand decks only; opts.product = the product) |
| Customer or analyst quote (`> quote` + attribution) | addQuoteSlide |
| Roadmap / timeline / milestones by quarter, year or phase | addRoadmapSlide |
| Legal disclaimer / notices / attributions | addDisclaimerSlide |
| Two contrasting topics / compare | addTwoColumn |
| Numbered two-column list | addTwoColNumbered |
| Sequential steps or process (3-6 items) | addProcessFlow |
| 3 parallel items with headings | addThreeColContent |
| Partner logos / ecosystem / technology stack | addLogoGridSlide (requires preRenderIcons) |
| Image + supporting text | addSplitImageContent or addImageBulletsSlide |
| Image + caption only | addPictureCaption |
| Hero/cinematic image with title overlay | addCinematicSlide |
| 2-4 image gallery | addTwoImageGallery / addThreeImageGallery / addFourImageGallery |
| Section intro with body paragraphs | addSectionContent |
| Simple list with NO natural grouping | addBulletSlide (last resort) |
| IMAGE: with no bullets | addImageSlide |
| IMAGE: with bullets | addImageBulletsSlide |
| Last slide / thank you | addClosingSlide |

### Choosing the title slide (decide from the outline's audience and subject)

- addProductTitleSlide — the deck is about one AMD product or platform (Instinct / MI3xx,
  ROCm, EPYC, Radeon …): product briefings, performance decks, launches. Set opts.product
  to the product line ('ROCm' for software, 'Instinct' for GPUs) and opts.presenter if a
  speaker is named.
- addHeroTitleSlide — executive, strategy, vision, keynote or customer-pitch decks that
  are about a message rather than one product. Pass opts.date when the outline gives one.
- addTitleSlide — the default: internal updates, training, workshops, technical deep
  dives, or whenever the signal is unclear. Never pick a brand title just to vary things.

When you use a brand title, keep the WHOLE deck in that style:
- The agenda MUST be the photo variant:
  addAgendaSlide(deck, `Agenda`, items, n, notes, { image: '', label: `<deck title>` })
- In a brand deck the brand rows above win over addTakeawaySlide: a slide whose bullets
  compare two values of one metric is addProofPointSlide, and a claim with supporting or
  sourced facts is addStatementSlide — even when the slide has a `> ` blockquote (use it as
  the headline).
- Described section openers are addSectionIntroSlide; product pillars are addFeatureListSlide.
With addTitleSlide, use ONLY the standard layouts — never addSectionIntroSlide,
addStatementSlide, addProofPointSlide, addFeatureListSlide or the photo agenda.

Brand title details: do not repeat the date inside the subtitle when you pass opts.date.
addProofPointSlide multiple: write the gain the way the audience reads it — '2.1X' when
higher is better, '40% lower' when lower is better (cost, latency, power). Never a value
below 1X.

Variety Rule: NEVER use the same layout on two consecutive slides.
Substitution: if you would use addBulletSlide twice in a row, use addCardGrid, addTwoColumn, addThreeColContent, or addProcessFlow instead.
Preference: addBulletSlide is the LAST RESORT — always prefer richer layouts when the content fits.
Gallery preference: for 2 images use addTwoImageGallery; for 3 use addThreeImageGallery; for 4+ use addFourImageGallery.
Takeaways: when the outline gives a `> ` line on a table or roadmap slide, pass it as opts.takeaway. On any other layout that can't show it, put it first in the speaker notes — never drop it.

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
""".replace("{example}", "## Complete example (correct calls, backtick text)\n\n```javascript\n"
            + _EXAMPLE_SCRIPT + "```")


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


def _truncation_reasons(raw: str, script: str) -> list[str]:
    """Catch responses cut off by max_tokens — they can still look valid."""
    reasons = []
    if "```" in raw and not _CODE_FENCE_RE.search(raw):
        reasons.append("the response was cut off (no closing code fence) — "
                       "write a shorter script with fewer, tighter notes")
    if ".save(" not in script:
        reasons.append("the script never calls deck.save(...) — it must end by saving the deck")
    return reasons


def _with_previous(base_prompt: str, script: str, intro: str, problems: list[str]) -> str:
    """Build a fix-up prompt that shows the model its own previous script."""
    return (
        base_prompt
        + "\n\nYour previous script:\n```javascript\n" + script + "\n```\n\n"
        + intro + "\n"
        + "\n".join(f"- {p}" for p in problems)
        + "\n\nReturn the complete corrected script, changing only what is needed."
    )


def _base_prompt(outline_text: str, theme: str) -> str:
    return (
        f"Generate a pptxgenjs .mjs script for the following presentation outline.\n"
        f"Theme: {theme}\n\n"
        f"---\n{outline_text.strip()}\n---\n\n"
        "Output ONLY the script inside a ```javascript code fence."
    )


def _generate_valid(
    base_user_prompt: str,
    first_prompt: str,
    llm_client,
    max_retries: int,
    progress_callback: Optional[Callable[[str, str], None]],
    label: str,
    extra_check: Optional[Callable[[str], list[str]]] = None,
) -> str:
    """Call the LLM until a script passes validation; raise after max_retries."""
    user_prompt = first_prompt
    last_reasons: list[str] = []
    for attempt in range(max_retries):
        if progress_callback:
            if attempt == 0:
                progress_callback("generate", label)
            else:
                progress_callback(
                    "generate",
                    f"Retry {attempt}/{max_retries - 1}: {last_reasons[0] if last_reasons else 'validation failed'}",
                )

        raw = llm_client.generate_text(
            prompt=user_prompt,
            system_prompt=_SYSTEM_PROMPT,
            max_tokens=12000,
        )

        script = _extract_code_block(raw)
        ok, last_reasons = validate_script(script)
        last_reasons = _truncation_reasons(raw, script) + last_reasons
        if extra_check:
            last_reasons += extra_check(script)
        if not last_reasons:
            if progress_callback:
                progress_callback("generate", f"Script validated ({len(script)} chars)")
            return script

        # Feed the failures and the script itself back so the model can make
        # targeted fixes rather than regenerating from scratch.
        user_prompt = _with_previous(
            base_user_prompt, script,
            "It failed these checks — fix each one exactly, keeping everything else the same:",
            last_reasons,
        )

    reasons_str = "; ".join(last_reasons[:3])
    raise ScriptGenerationError(
        f"Script failed validation after {max_retries} attempt(s): {reasons_str}"
    )


# ---------------------------------------------------------------------------
# 30-3-30 decks — the LLM writes each slide once, AIPPT adds the tier frame
# ---------------------------------------------------------------------------

_SLIDE_HEADER_RE = re.compile(r"^// ═══ Slide (\d+):(.*?)═══[ \t]*$", re.M)
_SCRIPT_TAIL_RE = re.compile(r"^(?:(?:const|let|var)\s+outDir\b|await\s+deck\.save\()", re.M)
_HELPERS_IMPORT_RE = re.compile(r"import\s*\{([^}]*)\}\s*from\s*(['\"])\.\./lib/pptxgenjs-helpers\.mjs\2")


class _TierPlan:
    """A 30-3-30 outline: its unique slides and the flat outline the LLM sees."""

    def __init__(self, slides: list, no_repeat: set, outline: str):
        self.slides, self.no_repeat, self.outline = slides, no_repeat, outline


def _tier_plan(outline_text: str) -> Optional[_TierPlan]:
    """The tier plan for a 30-3-30 outline (tier H1s), else None."""
    from aippt.pptxgenjs_direct import _plan, _strip_tier_lines
    try:
        slides, no_repeat = _plan(outline_text)
    except Exception:
        return None
    if not any(s.get("_tier") for s in slides):
        return None

    # Each H2 runs to the next heading — the parser's slide boundaries, with
    # notes blocks kept so the LLM can still write them into the notes
    chunks: list[list[str]] = []
    for line in _strip_tier_lines(outline_text)[0].split("\n"):
        if line.startswith("## "):
            chunks.append(["# " + line[3:].strip()])
        elif line.startswith("# "):
            chunks.append(None)
        elif chunks and chunks[-1] is not None:
            chunks[-1].append(line)
    chunks = [c for c in chunks if c is not None]
    if slides[0].get("_synthetic"):
        chunks.insert(0, ["# " + slides[0]["title"], "(Title slide for the whole deck)"])
    if len(chunks) != len(slides):
        return None
    return _TierPlan(slides, no_repeat, "\n\n".join("\n".join(c).strip() for c in chunks))


def _tier_instructions(count: int) -> str:
    return (
        f"\n\nThis outline has exactly {count} slides — each `# ` heading is one slide. "
        f"Write exactly {count} slides in the outline's order, one per heading, numbered 1 to "
        f"{count}: start each with its marker `// ═══ Slide N: <title> ═══` and pass N as its "
        "slideNum. Never split, merge, add or drop slides, and use addClosingSlide only for a "
        "heading that is itself a thank-you / closing slide. AIPPT adds the section dividers "
        "and repeats slides itself, so do not add any."
    )


def _tier_problems(script: str, count: int) -> list[str]:
    """Reasons the script can't be split into the outline's *count* slides."""
    headers = list(_SLIDE_HEADER_RE.finditer(script))
    numbers = [int(m.group(1)) for m in headers]
    problems = []
    if numbers != list(range(1, count + 1)):
        problems.append(
            f"write exactly {count} slides, one per outline heading, each starting with "
            f"`// ═══ Slide N: <title> ═══` numbered 1 to {count} in order (found "
            f"{len(numbers)} markers)")
    if not _SCRIPT_TAIL_RE.search(script, headers[-1].end() if headers else 0):
        problems.append("end the script with `const outDir = process.env.AIPPT_PREVIEW_OUT || "
                        "'output';` and `await deck.save(...)`")
    return problems


def _renumber(block: str, old: int, new: int) -> str:
    """*block* with its slide marker and helper slideNum arguments moved to *new*."""
    block = re.sub(rf"^// ═══ Slide {old}:", f"// ═══ Slide {new}:", block, count=1, flags=re.M)
    sigs = _helper_signatures()
    spans = []
    i = 0
    while i < len(block):
        c = block[i]
        if c in "'\"":
            i = _skip_quoted(block, i)
            continue
        if c == "`":
            i = _skip_template(block, i)
            continue
        end = _skip_comment(block, i)
        if end is not None:
            i = end
            continue
        m = _CALL_START.match(block, i)
        if not m:
            i += 1
            continue
        args, end = _scan_until(block, m.end(), ")")
        params = [p for p, _ in sigs.get(m.group(1), [])]
        if "slideNum" in params and params.index("slideNum") < len(args):
            # Pieces are consecutive slices, so each is found after the last
            cursor = m.end()
            for k, arg in enumerate(args):
                at = block.find(arg, cursor)
                cursor = at + len(arg)
                if k == params.index("slideNum") and arg.strip() == str(old):
                    num_at = at + arg.index(str(old))
                    spans.append((num_at, num_at + len(str(old))))
        i = end
    for a, b in reversed(spans):
        block = block[:a] + str(new) + block[b:]
    return block


def _assemble_tiers(script: str, plan: _TierPlan) -> str:
    """Expand a one-slide-per-heading script into the full 30-3-30 deck."""
    from aippt.pptxgenjs_direct import _emit_tier_frame, _js_str, _md_plain, _tier_sequence
    headers = list(_SLIDE_HEADER_RE.finditer(script))
    tail_at = _SCRIPT_TAIL_RE.search(script, headers[-1].end()).start()
    preamble, tail = script[:headers[0].start()], script[tail_at:]
    blocks = [script[h.start():(headers[k + 1].start() if k + 1 < len(headers) else tail_at)]
              for k, h in enumerate(headers)]

    def add_imports(m):
        names = [n.strip() for n in m.group(1).split(",") if n.strip()]
        names += [n for n in ("startSection", "addTierDivider", "addClosingSlide") if n not in names]
        return "import { " + ", ".join(names) + " } from '../lib/pptxgenjs-helpers.mjs'"
    preamble = _HELPERS_IMPORT_RE.sub(add_imports, preamble, count=1)

    sequence = _tier_sequence(plan.slides, list(enumerate(blocks, 1)), plan.no_repeat,
                              is_closing=lambda item: "addClosingSlide(" in item[1])
    deck_title = _js_str(_md_plain(plan.slides[0]["title"]))
    out, n = [], 0
    for entry in sequence:
        n += entry[0] != "section"
        if entry[0] == "slide":
            old, block = entry[2]
            out.append(_renumber(block, old, n).rstrip() + "\n")
        else:
            out.append(_emit_tier_frame(entry, n, deck_title))
    return preamble + "\n".join(out) + "\n" + tail


def _generate_tiered(plan: _TierPlan, theme: str, llm_client, max_retries: int,
                     progress_callback, first_prompt: Optional[str] = None,
                     label: str = "Generating pptxgenjs script…") -> tuple[str, str]:
    """(one-slide-per-heading script, assembled 30-3-30 script)."""
    base = _base_prompt(plan.outline, theme) + _tier_instructions(len(plan.slides))
    unique = _generate_valid(base, first_prompt or base, llm_client, max_retries,
                             progress_callback, label,
                             extra_check=lambda s: _tier_problems(s, len(plan.slides)))
    full = _assemble_tiers(unique, plan)
    ok, reasons = validate_script(full)
    if not ok:
        raise ScriptGenerationError("Assembled 30-3-30 script failed validation: "
                                    + "; ".join(reasons[:3]))
    return unique, full


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
    plan = _tier_plan(outline_text)
    if plan:
        script = _generate_tiered(plan, theme, llm_client, max_retries, progress_callback)[1]
    else:
        base = _base_prompt(outline_text, theme)
        script = _generate_valid(base, base, llm_client, max_retries,
                                 progress_callback, "Generating pptxgenjs script…")
    Path(output_script_path).write_text(script, encoding="utf-8")
    return script


def generate_and_render(
    outline_text: str,
    output_script_path: str,
    llm_client,
    renderer,
    out_dir: str,
    theme: str = "amd",
    max_retries: int = 3,
    max_repairs: int = 2,
    progress_callback: Optional[Callable[[str, str], None]] = None,
):
    """Generate a script, render it, and repair it if Node rejects it.

    Validation can't catch every runtime error (bad JS syntax, a helper
    throwing on malformed data), so on a failed render the script and the
    tail of Node's stderr go back to the LLM for up to *max_repairs* rounds.

    Returns the last ``RenderResult`` — check ``.success``. Raises
    ``ScriptGenerationError`` if a (re)generated script fails validation.
    """
    plan = _tier_plan(outline_text)
    if plan:
        # Repairs work on the one-slide-per-heading script, then re-assemble
        base = _base_prompt(plan.outline, theme) + _tier_instructions(len(plan.slides))
        script, full = _generate_tiered(plan, theme, llm_client, max_retries, progress_callback)
        Path(output_script_path).write_text(full, encoding="utf-8")
    else:
        base = _base_prompt(outline_text, theme)
        script = generate_script(outline_text, output_script_path, llm_client,
                                 theme, max_retries, progress_callback)
    for repair in range(max_repairs + 1):
        if progress_callback:
            progress_callback("render", "Executing script…")
        result = renderer.render(output_script_path, out_dir)
        if result.success or repair == max_repairs:
            return result
        error = (result.stderr_tail or "no .pptx was produced").strip()
        first_line = error.splitlines()[-1] if error else ""
        if progress_callback:
            progress_callback("generate", f"Repair {repair + 1}/{max_repairs}: {first_line[:160]}")
        prompt = _with_previous(
            base, script,
            "It passed validation but crashed when run with Node. Error output:\n"
            f"```\n{error[-3000:]}\n```\nFix the cause:",
            ["fix the error above (check quoting, brackets and helper arguments)"],
        )
        if plan:
            script, full = _generate_tiered(plan, theme, llm_client, max_retries,
                                            progress_callback, prompt, "Repairing script…")
        else:
            script = full = _generate_valid(base, prompt, llm_client, max_retries,
                                            progress_callback, "Repairing script…")
        Path(output_script_path).write_text(full, encoding="utf-8")
    return result
