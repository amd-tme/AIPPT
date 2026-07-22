"""Quality lint for LLM-generated pptxgenjs scripts.

**This is a quality convenience, not a security boundary.** Execution safety is
enforced deterministically at runtime by the ``preview.py`` Renderer sandbox
(scrubbed subprocess environment + Node ``--permission`` model), which cannot be
evaded by script content the way a static text scan can. See
``swproductmgmt/projects/aippt/specs/2026-07-21-renderer-hardening-and-validation.md``.

This module catches only the handful of rules that *corrupt the PPTX output*
(hash-prefixed hex, 8-char hex, ``LAYOUT_16x9``) plus a best-effort import hint,
and feeds its reasons back into the generator's regenerate prompt. It is pure and
LLM-independent so it can be unit-tested without any LLM calls.

Historical note: earlier versions also carried a denylist of "dangerous"
constructs (``eval``, ``fs``, ``net``, ``process.env`` …). Those were removed on
2026-07-21 — they were trivially bypassable (aliased ``require``, bracket
property access) so gave false security, and their word-boundary patterns
false-positived on ordinary slide content (a title containing "net", a git SHA,
an interpolated template literal). The runtime sandbox owns execution safety now.
"""
from __future__ import annotations

import re
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Allow-list: the import sources a well-formed script is expected to use.
# Kept as a *lint hint* (helps the generator produce correct scripts); it is NOT
# a security control — the Renderer sandbox is.
# ---------------------------------------------------------------------------

_ALLOWED_IMPORT_SOURCES: frozenset[str] = frozenset({
    "../lib/pptxgenjs-helpers.mjs",
    "../lib/pptxgenjs-masters.mjs",
    "path",
    "url",
})

# ---------------------------------------------------------------------------
# Critical Rules from the create-deck skill that corrupt PPTX output.
#
# The hex rules are scoped to *color-argument positions* (a color-ish key
# followed by the offending literal) so they fire on genuine color usage like
# ``color: '#00C2DE'`` but NOT on hex-looking text in slide content — e.g. a
# title "Kubernetes net policies", a code slide containing a git SHA
# "abc12345", or an interpolated template literal ```Slide ${n}```.
# ---------------------------------------------------------------------------

# Keys that take a color value in pptxgenjs / the AIPPT helpers.
_COLOR_KEY = r"(?:color|fill|fontColor|backgroundColor|bkgd|line|glow|outline|highlight|transparency\s*:\s*\d+\s*,\s*color)"

_CRITICAL_RULES: List[Tuple[re.Pattern, str]] = [
    # Hex colors must NOT be prefixed with '#' — only when used as a color value.
    (
        re.compile(rf'''\b{_COLOR_KEY}\s*:\s*["']#[0-9A-Fa-f]{{3,8}}["']'''),
        "hex color must not use # prefix (e.g. use '00C2DE' not '#00C2DE')",
    ),
    # 8-char hex (opacity embedded in hex) corrupts PPTX — only as a color value.
    (
        re.compile(rf'''\b{_COLOR_KEY}\s*:\s*["'][0-9A-Fa-f]{{8}}["']'''),
        "8-character hex color not allowed; use rgba() / transparency for opacity",
    ),
    # LAYOUT_16x9 produces wrong slide dimensions — always use LAYOUT_WIDE.
    (
        re.compile(r'\bLAYOUT_16x9\b'),
        "use pptx.layout = 'LAYOUT_WIDE' (13.33\" × 7.5\"), never LAYOUT_16x9",
    ),
]

# ---------------------------------------------------------------------------
# Import parser
# ---------------------------------------------------------------------------

_IMPORT_RE = re.compile(
    r'''^\s*import\s+(?:[^"']+from\s+)?["']([^"']+)["']''',
    re.MULTILINE,
)

# Named imports extracted from the helpers import statement
_NAMED_IMPORT_RE = re.compile(
    r'''import\s*\{([^}]+)\}\s*from\s*["']\.\.\/lib\/pptxgenjs-helpers\.mjs["']''',
    re.DOTALL,
)

# All AIPPT helper function names exported by lib/pptxgenjs-helpers.mjs. Kept in
# sync with that file — if a helper is added/renamed there, update this set.
_HELPER_FUNCTIONS: frozenset[str] = frozenset({
    "addBulletSlide", "addCardGrid", "addCinematicSlide", "addClosingSlide",
    "addCodeSlide", "addEyebrowText", "addFooter", "addFourImageGallery",
    "addIconRowsSlide", "addImageBulletsSlide", "addImageSlide",
    "addPictureCaption", "addProcessFlow", "addSectionContent",
    "addSectionDivider", "addSplitImageContent", "addStatCallout",
    "addThreeColContent", "addThreeColImageText", "addThreeImageGallery",
    "addTitleAlt", "addTitleSlide", "addTitleWithImage", "addTwoColNumbered",
    "addTwoColumn", "addTwoImageGallery", "cardShadow", "computeLayout",
    "createDeck", "iconToBase", "loadTheme", "preRenderIcons", "renderIconSvg",
})


def _extract_import_sources(source: str) -> List[str]:
    """Return all import source specifiers found in *source*."""
    return _IMPORT_RE.findall(source)


def _check_missing_imports(source: str) -> List[str]:
    """Return reasons for any helper functions called but not imported.

    Catches the common failure where the LLM calls e.g. ``addCardGrid`` but
    omits it from the import list, which throws ``ReferenceError`` at render
    time. Only helper names in ``_HELPER_FUNCTIONS`` are checked, so a
    same-named local function is not flagged (it would appear imported or be
    defined in-file).
    """
    m = _NAMED_IMPORT_RE.search(source)
    imported: set[str] = set()
    if m:
        imported = {name.strip() for name in m.group(1).split(",") if name.strip()}

    reasons = []
    for fn in sorted(_HELPER_FUNCTIONS):
        # Called (followed by open paren) but neither imported nor defined locally.
        called = re.search(rf'\b{fn}\s*\(', source)
        defined = re.search(rf'\bfunction\s+{fn}\b', source) or re.search(
            rf'\b(?:const|let|var)\s+{fn}\s*=', source
        )
        if called and fn not in imported and not defined:
            reasons.append(f"'{fn}' is called but not imported from pptxgenjs-helpers.mjs")
    return reasons


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_script(source: str) -> Tuple[bool, List[str]]:
    """Lint a candidate pptxgenjs script for PPTX-corrupting mistakes.

    Returns ``(True, [])`` when the script passes, or ``(False, reasons)`` with
    human-readable failure messages. Pure function — no I/O, no side effects.

    This is a *quality* lint, not a security gate: it does not attempt to detect
    malicious code (the Renderer sandbox handles execution safety). It flags
    only import mistakes and the color/layout rules that corrupt output.
    """
    reasons: List[str] = []

    # 1. Import allow-list (lint hint — unexpected sources usually signal a
    #    hallucinated dependency, not an attack).
    for specifier in _extract_import_sources(source):
        if specifier not in _ALLOWED_IMPORT_SOURCES:
            reasons.append(
                f"unexpected import '{specifier}' — expected only "
                f"{sorted(_ALLOWED_IMPORT_SOURCES)}"
            )

    # 2. Critical rules (PPTX-corrupting).
    for pattern, message in _CRITICAL_RULES:
        if pattern.search(source):
            reasons.append(message)

    # 3. Missing imports — helper called but not imported.
    reasons.extend(_check_missing_imports(source))

    return (len(reasons) == 0, reasons)
