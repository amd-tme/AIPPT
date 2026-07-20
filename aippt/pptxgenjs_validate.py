"""Deterministic validation gate for LLM-generated pptxgenjs scripts.

Every script produced by pptxgenjs_gen.py must pass this gate before the
Renderer subprocess is allowed to execute it.  The gate is intentionally
conservative and LLM-independent — it can be unit-tested without any LLM
calls and enforces the Critical Rules from the create-deck skill.
"""
from __future__ import annotations

import re
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Allow-list: the only import sources a generated script may use
# ---------------------------------------------------------------------------

_ALLOWED_IMPORT_SOURCES: frozenset[str] = frozenset({
    "../lib/pptxgenjs-helpers.mjs",
    "../lib/pptxgenjs-masters.mjs",
    "path",
    "url",
})

# ---------------------------------------------------------------------------
# Deny-list: patterns whose presence in the source is an automatic rejection
# ---------------------------------------------------------------------------

_DENIED_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\beval\s*\('),           "eval() is not allowed"),
    (re.compile(r'\bFunction\s*\('),       "Function() constructor is not allowed"),
    (re.compile(r'\bchild_process\b'),     "child_process module is not allowed"),
    (re.compile(r'\bfs\s*\.'),             "fs module is not allowed"),
    (re.compile(r'\bnet\b'),               "net module is not allowed"),
    (re.compile(r'\bhttp\s*\.'),           "http module is not allowed"),
    (re.compile(r'\bhttps\s*\.'),          "https module is not allowed"),
    (re.compile(r'process\s*\.\s*env'),    "process.env access is not allowed"),
    (re.compile(r'\bsetTimeout\s*\('),     "setTimeout is not allowed"),
    (re.compile(r'\bsetInterval\s*\('),    "setInterval is not allowed"),
    # Dynamic import() — pattern catches `import(` and `import (` etc.
    (re.compile(r'\bimport\s*\('),         "dynamic import() is not allowed"),
    # Shell execution via tagged template literals: `cmd ${...}` patterns
    (re.compile(r'`[^`]*\$\{[^`]*\}`'),   "template-literal shell exec pattern detected"),
]

# ---------------------------------------------------------------------------
# Critical Rules from the create-deck skill that corrupt PPTX output
# ---------------------------------------------------------------------------

_CRITICAL_RULES: List[Tuple[re.Pattern, str]] = [
    # Hex colors must NOT be prefixed with #
    (
        re.compile(r'''["']#[0-9A-Fa-f]{3,8}["']'''),
        "hex color must not use # prefix (e.g. use '00C2DE' not '#00C2DE')",
    ),
    # 8-char hex (opacity embedded in hex) corrupts PPTX — use rgba instead
    (
        re.compile(r'''["'][0-9A-Fa-f]{8}["']'''),
        "8-character hex not allowed; use rgba() for opacity",
    ),
    # LAYOUT_16x9 produces wrong slide dimensions — always use LAYOUT_WIDE
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


def _extract_import_sources(source: str) -> List[str]:
    """Return all import source specifiers found in *source*."""
    return _IMPORT_RE.findall(source)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_script(source: str) -> Tuple[bool, List[str]]:
    """Validate a candidate pptxgenjs script.

    Returns ``(True, [])`` when the script passes all checks, or
    ``(False, reasons)`` where *reasons* is a non-empty list of human-readable
    failure messages.  Pure function — no I/O, no side effects.
    """
    reasons: List[str] = []

    # 1. Import allow-list
    for specifier in _extract_import_sources(source):
        if specifier not in _ALLOWED_IMPORT_SOURCES:
            reasons.append(
                f"disallowed import '{specifier}' — only {sorted(_ALLOWED_IMPORT_SOURCES)} are allowed"
            )

    # 2. Denied constructs
    for pattern, message in _DENIED_PATTERNS:
        if pattern.search(source):
            reasons.append(message)

    # 3. Critical rules
    for pattern, message in _CRITICAL_RULES:
        if pattern.search(source):
            reasons.append(message)

    return (len(reasons) == 0, reasons)
