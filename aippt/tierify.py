"""Turn an ordinary outline into a 30-3-30 outline with one LLM call.

The result uses the tier H1s the deck engines understand (``# 30 Seconds``,
``# 3 Minutes``, ``# 30 Minutes``, ``# Appendix``). Earlier tiers repeat in
later ones when the deck is built, so each tier only holds its *new* slides.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from aippt.pptxgenjs_direct import _plan


class TierifyError(Exception):
    """Raised when the outline can't be turned into a 30-3-30 outline."""


_SYSTEM_PROMPT = """\
You restructure presentation outlines into the AMD "30-3-30" format: one deck
that can be presented in 30 seconds, 3 minutes or 30 minutes.

Output a markdown outline with exactly this shape:

# <Deck title>

## <Deck title>
<one-line subtitle>

# 30 Seconds

## <slide title>
...  (1-2 slides: the whole story in one breath — the problem, the answer, the proof)

# 3 Minutes

## <slide title>
...  (2-5 slides: the overview — how it works, key results, why it matters)

# 30 Minutes

## <slide title>
...  (the full detail — every remaining slide of the original outline)

# Appendix

## <slide title>
...  (ONLY if the original has backup, reference, legal/disclaimer or resource
      slides — move them here. Otherwise leave out "# Appendix" entirely.)

How the deck is built — this decides what goes where:
- The 3-minute version automatically re-shows the 30-second slides first, and
  the 30-minute version re-shows the 30-second and 3-minute slides first. So
  each tier holds ONLY its new slides — never copy a slide into a later tier.
- Section dividers and per-tier closing slides are added automatically — do not
  write them. A final "Thank you" / "Questions" slide, if the original has one,
  goes last in "# 30 Minutes".

Content rules:
- Use only facts, numbers and names from the original outline — never invent any,
  and never write a slide whose content isn't in the original.
- The 30-second and 3-minute slides condense the original: short, punchy bullets
  (at most 4 per slide) drawn from its strongest points and numbers.
- The 30-minute slides keep the original slides' wording, tables, code blocks,
  `> ` takeaway lines, LAYOUT: / IMAGE: lines and notes blocks
  (`<!-- notes ... -->`, `*Notes:*`) as written.
- Agenda / table-of-contents slides from the original are dropped.
- Every slide is a `## ` heading under one of the `# ` headings above; no other
  `# ` headings.

Respond with ONLY the outline inside a ```markdown code fence.
"""

_FENCE_RE = re.compile(r"```(?:markdown|md)?\s*\n(.*?)```", re.DOTALL)


def _extract(text: str) -> str:
    m = _FENCE_RE.search(text)
    return (m.group(1) if m else text).strip() + "\n"


def tier_problems(outline: str) -> list[str]:
    """Reasons *outline* isn't a usable 30-3-30 outline (empty when it is)."""
    try:
        slides, _ = _plan(outline)
    except Exception as exc:
        return [f"the outline could not be parsed: {exc}"]
    counts: dict = {}
    for slide in slides:
        if slide.get("_tier"):
            counts[slide["_tier"]] = counts.get(slide["_tier"], 0) + 1
    problems = [f"add a `# {name}` section with at least one `## ` slide"
                for key, name in (("30s", "30 Seconds"), ("3m", "3 Minutes"), ("30m", "30 Minutes"))
                if not counts.get(key)]
    if counts.get("30s", 0) > 2:
        problems.append(f"`# 30 Seconds` has {counts['30s']} slides — condense it to 1-2")
    if counts.get("3m", 0) > 5:
        problems.append(f"`# 3 Minutes` has {counts['3m']} slides — condense it to 2-5")
    return problems


def is_tiered(outline: str) -> bool:
    """True when *outline* already uses 30-3-30 tier sections."""
    try:
        return any(s.get("_tier") for s in _plan(outline)[0])
    except Exception:
        return False


def make_30_3_30(
    outline_text: str,
    llm_client,
    max_retries: int = 2,
    progress_callback: Optional[Callable[[str, str], None]] = None,
) -> str:
    """Return a 30-3-30 version of *outline_text*.

    Raises ``TierifyError`` if the outline is empty or already tiered, or if
    the LLM's outline still has problems after *max_retries* attempts.
    """
    if not outline_text.strip():
        raise TierifyError("The outline is empty.")
    if is_tiered(outline_text):
        raise TierifyError("This outline is already in 30-3-30 format.")

    base = f"Restructure this outline into the 30-3-30 format:\n\n---\n{outline_text.strip()}\n---"
    prompt, problems = base, []
    for attempt in range(max_retries):
        if progress_callback:
            progress_callback("tierify", "Writing the 30-3-30 outline…" if attempt == 0
                              else f"Retry {attempt}/{max_retries - 1}: {problems[0]}")
        raw = llm_client.generate_text(prompt=prompt, system_prompt=_SYSTEM_PROMPT, max_tokens=12000)
        outline = _extract(raw)
        problems = tier_problems(outline)
        if not problems:
            return outline
        prompt = (base + "\n\nYour previous outline:\n```markdown\n" + outline + "```\n\n"
                  "Fix these problems, keeping everything else the same:\n"
                  + "\n".join(f"- {p}" for p in problems))
    raise TierifyError("Could not build a 30-3-30 outline: " + "; ".join(problems))
