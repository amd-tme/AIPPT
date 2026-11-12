"""Quality lint for LLM-generated pptxgenjs scripts.

**This is a quality convenience, not a security boundary.** Execution safety is
enforced deterministically at runtime by the ``preview.py`` Renderer sandbox
(scrubbed subprocess environment + Node ``--permission`` model), which cannot be
evaded by script content the way a static text scan can. See
``swproductmgmt/projects/aippt/specs/2026-07-21-renderer-hardening-and-validation.md``.

This module catches only the handful of rules that *corrupt the PPTX output*
(hash-prefixed hex, 8-char hex, ``LAYOUT_16x9``), unterminated string literals,
helper calls whose arguments don't match the helper's signature, plus a
best-effort import hint, and feeds its reasons back into the generator's
regenerate prompt. It is pure and
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
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
        "remove LAYOUT_16x9 — createDeck() already sets the 13.33\" × 7.5\" wide layout",
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
    "addAgendaSlide", "addBulletSlide", "addCardGrid", "addCinematicSlide",
    "addClosingSlide", "addCodeSlide", "addDisclaimerSlide", "addEyebrowText", "addFeatureListSlide",
    "addFooter", "addFourImageGallery", "addHeroTitleSlide",
    "addIconRowsSlide", "addImageBulletsSlide", "addImageSlide",
    "addLogoGridSlide", "addPictureCaption", "addProcessFlow", "addProductTitleSlide",
    "addProofPointSlide", "addQuoteSlide",
    "addRoadmapSlide", "addSectionContent", "addSectionDivider", "addSectionIntroSlide",
    "addSplitImageContent", "addStatementSlide",
    "addStatCallout", "addTableSlide", "addTakeawaySlide", "addThreeColContent", "addThreeColImageText",
    "addThreeImageGallery", "addTierDivider", "addTitleAlt", "addTitleSlide", "addTitleWithImage",
    "addTwoColNumbered", "addTwoColumn", "addTwoImageGallery", "cardShadow",
    "computeLayout", "createDeck", "iconToBase64", "loadIcons", "loadTheme",
    "preRenderIcons", "renderIconSvg", "startSection",
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
# Helper call checks — argument count / literal kinds vs the real signatures
# ---------------------------------------------------------------------------

_HELPERS_LIB = Path(__file__).resolve().parents[1] / "lib" / "pptxgenjs-helpers.mjs"

# Trailing parameters a call may leave out
_OPTIONAL_PARAMS = frozenset({"notes", "opts", "options"})

# Expected literal kind by parameter name (other names are not checked)
_PARAM_KINDS: Dict[str, str] = {
    **dict.fromkeys(("bullets", "items", "cards", "stats", "steps", "columns", "rows",
                     "points", "leftItems", "rightItems", "iconImages", "brandColors",
                     "evidence", "features"), "array"),
    **dict.fromkeys(("title", "subtitle", "sectionTitle", "imagePath", "code", "caption",
                     "takeaway", "quote", "attribution", "text", "leftHeader",
                     "rightHeader", "themePath", "headline", "subline", "tagline",
                     "body"), "string"),
    **dict.fromkeys(("slideNum", "sectionNumber"), "number"),
    "opts": "object",
    "proof": "object",
}


@lru_cache(maxsize=1)
def _helper_signatures() -> Dict[str, List[Tuple[str, bool]]]:
    """``{name: [(param, optional), ...]}`` parsed from the helper library."""
    try:
        text = _HELPERS_LIB.read_text(encoding="utf-8")
    except OSError:
        return {}
    sigs = {}
    for m in re.finditer(r"^export (?:async )?function (\w+)\(([^)]*)\)", text, re.M):
        params = []
        for p in m.group(2).split(","):
            name, eq, _ = p.partition("=")
            if name.strip():
                params.append((name.strip(), bool(eq) or name.strip() in _OPTIONAL_PARAMS))
        sigs[m.group(1)] = params
    return sigs


class _ScanError(Exception):
    def __init__(self, pos: int, message: str):
        super().__init__(message)
        self.pos = pos


def _skip_quoted(src: str, i: int) -> int:
    """Index after the '...' or "..." literal starting at *i*."""
    quote, j = src[i], i + 1
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == quote:
            return j + 1
        if c == "\n":
            break
        j += 1
    raise _ScanError(i, "unterminated string literal")


def _skip_template(src: str, i: int) -> int:
    """Index after the `...` template literal starting at *i* (handles ${...})."""
    j = i + 1
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "`":
            return j + 1
        if src.startswith("${", j):
            j = _scan_until(src, j + 2, "}")[1]
            continue
        j += 1
    raise _ScanError(i, "unterminated template literal")


def _skip_comment(src: str, i: int) -> Optional[int]:
    if src.startswith("//", i):
        end = src.find("\n", i)
        return len(src) if end < 0 else end
    if src.startswith("/*", i):
        end = src.find("*/", i + 2)
        return len(src) if end < 0 else end + 2
    return None


_CLOSERS = {"(": ")", "[": "]", "{": "}"}


def _scan_until(src: str, i: int, closer: str) -> Tuple[List[str], int]:
    """Scan code from *i* to the matching *closer*.

    Returns the top-level comma-separated pieces and the index after *closer*.
    Strings, templates and comments are skipped so their contents never count.
    """
    pieces, start, stack = [], i, []
    while i < len(src):
        c = src[i]
        if c in "'\"":
            i = _skip_quoted(src, i)
            continue
        if c == "`":
            i = _skip_template(src, i)
            continue
        end = _skip_comment(src, i)
        if end is not None:
            i = end
            continue
        if c in _CLOSERS:
            stack.append(_CLOSERS[c])
        elif stack and c == stack[-1]:
            stack.pop()
        elif not stack and c == closer:
            pieces.append(src[start:i])
            return [p for p in pieces if p.strip()], i + 1
        elif not stack and c == ",":
            pieces.append(src[start:i])
            start = i + 1
        i += 1
    raise _ScanError(len(src), f"missing '{closer}'")


def _literal_kind(arg: str) -> Optional[str]:
    a = arg.strip()
    while a.startswith("/*"):  # leading comment
        a = a[a.find("*/") + 2:].strip() if "*/" in a else ""
    if a[:1] in ("'", '"', "`"):
        return "string"
    if a.startswith("["):
        return "array"
    if a.startswith("{"):
        return "object"
    if re.fullmatch(r"-?\d+(?:\.\d+)?", a):
        return "number"
    return None  # variable / expression — can't tell statically


_CALL_START = re.compile(r"(?<![\w$.])(add[A-Z]\w*|createDeck|cardShadow)\s*\(")


def _check_helper_calls(source: str) -> List[str]:
    """Reasons for helper calls that don't match the library signatures.

    Also reports unterminated string literals (e.g. an apostrophe inside a
    '...' string), which Node rejects before rendering a single slide.
    """
    sigs = dict(_helper_signatures())
    # A same-named local function shadows the library helper
    for local in re.findall(r"\b(?:function\s+|(?:const|let|var)\s+)(\w+)", source):
        sigs.pop(local, None)
    reasons: List[str] = []

    def line_of(pos: int) -> int:
        return source.count("\n", 0, pos) + 1

    i = 0
    try:
        while i < len(source):
            c = source[i]
            if c in "'\"":
                i = _skip_quoted(source, i)
                continue
            if c == "`":
                i = _skip_template(source, i)
                continue
            end = _skip_comment(source, i)
            if end is not None:
                i = end
                continue
            m = _CALL_START.match(source, i)
            if not m:
                i += 1
                continue
            name = m.group(1)
            args, _ = _scan_until(source, m.end(), ")")
            if name in sigs:
                reasons.extend(_check_call(name, args, sigs[name], line_of(i)))
            # Continue inside the arguments so nested helper calls are checked
            i = m.end()
    except _ScanError as exc:
        hint = (" — an apostrophe inside a '...' string? Escape it as \\' or use a "
                "`template literal`" if "string" in str(exc) else "")
        reasons.append(f"line {line_of(exc.pos)}: {exc}{hint}")
    return reasons


_A = {"array": "an array", "object": "an object", "string": "a string", "number": "a number"}


def _check_call(name: str, args: List[str], params: List[Tuple[str, bool]], line: int) -> List[str]:
    if any(a.strip().startswith("...") for a in args):
        return []  # spread arguments — can't count
    signature = f"{name}({', '.join(p for p, _ in params)})"
    required = max((k + 1 for k, (_, opt) in enumerate(params) if not opt), default=0)
    if not required <= len(args) <= len(params):
        expected = str(len(params)) if required == len(params) else f"{required}-{len(params)}"
        return [f"line {line}: {name}() called with {len(args)} arguments, expected "
                f"{expected} — signature is {signature}"]
    reasons = []
    for k, (arg, (param, _)) in enumerate(zip(args, params)):
        want, got = _PARAM_KINDS.get(param), _literal_kind(arg)
        if want and got and got != want:
            reasons.append(f"line {line}: {name}() argument {k + 1} ({param}) should be "
                           f"{_A[want]}, got {_A[got]} — signature is {signature}")
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
    import mistakes, the color/layout rules that corrupt output, unterminated
    strings, and helper calls whose arguments don't fit the signature.
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

    # 4. Helper calls match the library signatures; no unterminated strings.
    reasons.extend(_check_helper_calls(source))

    return (len(reasons) == 0, reasons)
