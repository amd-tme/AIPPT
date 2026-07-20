"""Unit tests for aippt.pptxgenjs_validate — deterministic, no LLM required."""
import pytest
from aippt.pptxgenjs_validate import validate_script

# ---------------------------------------------------------------------------
# A minimal known-good script that should always pass
# ---------------------------------------------------------------------------

_GOOD_SCRIPT = """\
import { createDeck, addTitleSlide, addBulletSlide, addClosingSlide } from '../lib/pptxgenjs-helpers.mjs';

const deck = await createDeck('themes/amd.yaml');

// ═══ Slide 1: Introduction ═══
addTitleSlide(deck, 'My Presentation', 'An overview', 1);

// ═══ Slide 2: Key Points ═══
addBulletSlide(deck, 'Key Points', ['First point', 'Second point'], 2, '');

// ═══ Slide 3: Thank You ═══
addClosingSlide(deck, 3, '');

await deck.save('output/my-presentation.pptx');
"""


def test_good_script_passes():
    ok, reasons = validate_script(_GOOD_SCRIPT)
    assert ok is True
    assert reasons == []


# ---------------------------------------------------------------------------
# Import allow-list violations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_import,expected_fragment", [
    ("import fs from 'fs';",              "disallowed import 'fs'"),
    ("import { exec } from 'child_process';", "disallowed import 'child_process'"),
    ("import net from 'net';",            "disallowed import 'net'"),
    ("import http from 'http';",          "disallowed import 'http'"),
    ("import crypto from 'crypto';",      "disallowed import 'crypto'"),
    ("import { readFile } from 'fs/promises';", "disallowed import 'fs/promises'"),
])
def test_disallowed_import(bad_import, expected_fragment):
    source = _GOOD_SCRIPT + f"\n{bad_import}\n"
    ok, reasons = validate_script(source)
    assert ok is False
    assert any(expected_fragment in r for r in reasons), reasons


# ---------------------------------------------------------------------------
# Denied constructs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("snippet,expected_fragment", [
    ("eval('console.log(1)')",            "eval()"),
    ("new Function('return 1')()",        "Function()"),
    ("child_process.exec('ls')",          "child_process"),
    ("fs.readFileSync('/etc/passwd')",    "fs module"),
    ("net.connect(80, 'example.com')",   "net module"),
    ("http.get('http://evil.com')",       "http module"),
    ("https.get('https://evil.com')",     "https module"),
    ("process.env.SECRET",               "process.env"),
    ("setTimeout(() => {}, 1000)",       "setTimeout"),
    ("setInterval(() => {}, 1000)",      "setInterval"),
    ("import('./dynamic-module.mjs')",   "dynamic import()"),
])
def test_denied_construct(snippet, expected_fragment):
    source = _GOOD_SCRIPT + f"\n{snippet}\n"
    ok, reasons = validate_script(source)
    assert ok is False
    assert any(expected_fragment in r for r in reasons), reasons


# ---------------------------------------------------------------------------
# Critical Rules
# ---------------------------------------------------------------------------

def test_rejects_hash_prefixed_hex():
    source = _GOOD_SCRIPT + "\nconst color = '#00C2DE';\n"
    ok, reasons = validate_script(source)
    assert ok is False
    assert any("# prefix" in r for r in reasons), reasons


def test_rejects_8char_hex():
    source = _GOOD_SCRIPT + "\nconst color = 'FF0000FF';\n"
    ok, reasons = validate_script(source)
    assert ok is False
    assert any("8-character" in r for r in reasons), reasons


def test_rejects_layout_16x9():
    source = _GOOD_SCRIPT + "\npptx.layout = 'LAYOUT_16x9';\n"
    ok, reasons = validate_script(source)
    assert ok is False
    assert any("LAYOUT_16x9" in r or "LAYOUT_WIDE" in r for r in reasons), reasons


# ---------------------------------------------------------------------------
# Multiple violations — all reported
# ---------------------------------------------------------------------------

def test_multiple_violations_all_reported():
    source = (
        _GOOD_SCRIPT
        + "\nimport fs from 'fs';\n"
        + "eval('1');\n"
        + "const c = '#FF0000';\n"
    )
    ok, reasons = validate_script(source)
    assert ok is False
    assert len(reasons) >= 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_script_passes():
    """Empty source has no violations (no imports either)."""
    ok, reasons = validate_script("")
    assert ok is True


def test_masters_import_allowed():
    source = _GOOD_SCRIPT + "\nimport { masterNameFor } from '../lib/pptxgenjs-masters.mjs';\n"
    ok, reasons = validate_script(source)
    assert ok is True, reasons


def test_path_import_allowed():
    source = _GOOD_SCRIPT + "\nimport { join } from 'path';\n"
    ok, reasons = validate_script(source)
    assert ok is True, reasons


def test_url_import_allowed():
    source = _GOOD_SCRIPT + "\nimport { fileURLToPath } from 'url';\n"
    ok, reasons = validate_script(source)
    assert ok is True, reasons
