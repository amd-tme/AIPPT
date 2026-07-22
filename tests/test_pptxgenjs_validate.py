"""Unit tests for aippt.pptxgenjs_validate — a quality lint (not a security gate).

Execution safety is enforced at runtime by the Renderer sandbox
(tests/test_preview_sandbox.py), NOT by this module. These tests cover the
PPTX-corrupting rules, the import hint, and — critically — that legitimate slide
*content* is not false-positived (the regression class that motivated the
2026-07-21 rewrite).
"""
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

const outDir = process.env.AIPPT_PREVIEW_OUT || 'output';
await deck.save(`${outDir}/my-presentation.pptx`);
"""


def test_good_script_passes():
    ok, reasons = validate_script(_GOOD_SCRIPT)
    assert ok is True
    assert reasons == []


# ---------------------------------------------------------------------------
# Critical Rules — PPTX-corrupting mistakes (scoped to color positions)
# ---------------------------------------------------------------------------

def test_rejects_hash_prefixed_hex_color():
    source = _GOOD_SCRIPT + "\nconst opt = { color: '#00C2DE' };\n"
    ok, reasons = validate_script(source)
    assert ok is False
    assert any("# prefix" in r for r in reasons), reasons


def test_rejects_8char_hex_color():
    source = _GOOD_SCRIPT + "\nconst opt = { fill: 'FF0000FF' };\n"
    ok, reasons = validate_script(source)
    assert ok is False
    assert any("8-character" in r for r in reasons), reasons


def test_rejects_layout_16x9():
    source = _GOOD_SCRIPT + "\npptx.layout = 'LAYOUT_16x9';\n"
    ok, reasons = validate_script(source)
    assert ok is False
    assert any("LAYOUT_16x9" in r or "LAYOUT_WIDE" in r for r in reasons), reasons


def test_rejects_hash_hex_in_fontcolor():
    source = _GOOD_SCRIPT + "\naddText(slide, 'x', { fontColor: '#FFFFFF' });\n"
    ok, reasons = validate_script(source)
    assert ok is False
    assert any("# prefix" in r for r in reasons), reasons


# ---------------------------------------------------------------------------
# Legitimate content must NOT be rejected — the 2026-07-21 regression class.
# These are the cases the old word-boundary denylist / unscoped hex rules broke.
# ---------------------------------------------------------------------------

def test_title_containing_net_passes():
    source = _GOOD_SCRIPT + "\naddTitleSlide(deck, 'Kubernetes net policies', 'sub', 4);\n"
    ok, reasons = validate_script(source)
    assert ok is True, reasons


def test_content_mentioning_fs_and_http_passes():
    source = (
        _GOOD_SCRIPT
        + "\naddBulletSlide(deck, 'APIs', "
        "['fs.readFileSync reads a file', 'http.get fetches a URL', "
        "'see https://example.com/docs'], 5, '');\n"
    )
    ok, reasons = validate_script(source)
    assert ok is True, reasons


def test_git_sha_in_code_slide_passes():
    """An 8-hex git SHA in content is not a color literal and must pass."""
    source = (
        "import { createDeck, addCodeSlide } from '../lib/pptxgenjs-helpers.mjs';\n"
        "const deck = await createDeck('themes/amd.yaml');\n"
        "addCodeSlide(deck, 'Commit', 'git checkout abc12345', 6, '');\n"
    )
    ok, reasons = validate_script(source)
    assert ok is True, reasons


def test_interpolated_template_literal_passes():
    """`Slide ${n}` is a normal pptxgenjs idiom, not shell exec."""
    source = _GOOD_SCRIPT + "\nconst label = `Slide ${n} of ${total}`;\n"
    ok, reasons = validate_script(source)
    assert ok is True, reasons


def test_bare_hex_string_in_content_passes():
    """A hex-looking string that is NOT a color argument must pass."""
    source = _GOOD_SCRIPT + "\naddBulletSlide(deck, 'Hashes', ['deadbeef', 'cafebabe'], 7, '');\n"
    ok, reasons = validate_script(source)
    assert ok is True, reasons


# ---------------------------------------------------------------------------
# Import hint
# ---------------------------------------------------------------------------

def test_unexpected_import_flagged():
    source = _GOOD_SCRIPT + "\nimport crypto from 'crypto';\n"
    ok, reasons = validate_script(source)
    assert ok is False
    assert any("unexpected import 'crypto'" in r for r in reasons), reasons


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


# ---------------------------------------------------------------------------
# Missing-import detection
# ---------------------------------------------------------------------------

def test_helper_called_but_not_imported():
    source = (
        "import { createDeck, addTitleSlide } from '../lib/pptxgenjs-helpers.mjs';\n"
        "const deck = await createDeck('themes/amd.yaml');\n"
        "addTitleSlide(deck, 'T', 'S', 1);\n"
        "addCardGrid(deck, 'Cards', [], 2, '');\n"  # called, not imported
    )
    ok, reasons = validate_script(source)
    assert ok is False
    assert any("addCardGrid" in r and "not imported" in r for r in reasons), reasons


def test_locally_defined_helper_name_not_flagged():
    """A same-named local function must not trip the missing-import check."""
    source = (
        "import { createDeck } from '../lib/pptxgenjs-helpers.mjs';\n"
        "function addCardGrid(a) { return a; }\n"
        "addCardGrid(1);\n"
    )
    ok, reasons = validate_script(source)
    assert ok is True, reasons


def test_newly_known_helpers_recognized():
    """Helpers added to the library (e.g. addThreeColContent) are known."""
    source = (
        "import { createDeck, addThreeColContent } from '../lib/pptxgenjs-helpers.mjs';\n"
        "const deck = await createDeck('themes/amd.yaml');\n"
        "addThreeColContent(deck, 'T', [], 1, '');\n"
    )
    ok, reasons = validate_script(source)
    assert ok is True, reasons


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_script_passes():
    ok, reasons = validate_script("")
    assert ok is True


def test_multiple_violations_all_reported():
    source = (
        _GOOD_SCRIPT
        + "\nimport crypto from 'crypto';\n"
        + "const a = { color: '#FF0000' };\n"
        + "pptx.layout = 'LAYOUT_16x9';\n"
    )
    ok, reasons = validate_script(source)
    assert ok is False
    assert len(reasons) >= 3
