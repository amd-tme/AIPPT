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


# ---------------------------------------------------------------------------
# Helper call checks (argument count / literal kinds vs lib signatures)
# ---------------------------------------------------------------------------

_HEAD = ("import { createDeck, addBulletSlide, addSplitImageContent, addTableSlide, "
         "addThreeColContent, addTitleWithImage } from '../lib/pptxgenjs-helpers.mjs';\n"
         "const deck = await createDeck('themes/amd.yaml');\n")


def _reasons(body: str) -> list:
    return validate_script(_HEAD + body)[1]


def test_validator_helper_set_matches_library_exports():
    import re
    from pathlib import Path
    from aippt.pptxgenjs_validate import _HELPER_FUNCTIONS
    lib = (Path(__file__).resolve().parents[1] / "lib" / "pptxgenjs-helpers.mjs").read_text()
    exported = set(re.findall(r"^export (?:async )?function (\w+)", lib, re.M))
    assert exported <= _HELPER_FUNCTIONS


def test_unterminated_string_from_apostrophe_is_reported():
    reasons = _reasons("addBulletSlide(deck, 'Why', [\n  'today's clusters',\n], 2, 'n');\n")
    assert len(reasons) == 1
    assert "line 4: unterminated string literal" in reasons[0]
    assert "template literal" in reasons[0]


def test_wrong_argument_count_is_reported_with_signature():
    reasons = _reasons("addThreeColContent(deck, 'T', 'a', 'b', 'c', ['x'], 2, 'n');\n")
    assert reasons == ["line 3: addThreeColContent() called with 8 arguments, expected 4-5 — "
                       "signature is addThreeColContent(deck, title, columns, slideNum, notes)"]


def test_swapped_arguments_are_reported():
    reasons = _reasons("addSplitImageContent(deck, 'T', 'img.png', ['a', 'b'], 3, 'n');\n")
    assert any("argument 3 (bullets) should be an array, got a string" in r for r in reasons)
    assert any("argument 4 (imagePath) should be a string, got an array" in r for r in reasons)


def test_string_slide_number_is_reported():
    reasons = _reasons("addBulletSlide(deck, 'T', ['a'], '2', 'n');\n")
    assert any("(slideNum) should be a number, got a string" in r for r in reasons)


def test_optional_trailing_arguments_may_be_omitted():
    assert _reasons("addBulletSlide(deck, 'T', ['a'], 2);\n"
                    "addTableSlide(deck, 'T', null, [['a']], 3, 'n', { takeaway: 'x' });\n") == []


def test_variables_expressions_and_spreads_are_not_flagged():
    body = ("const items = ['a'];\nconst n = 2;\n"
            "addBulletSlide(deck, `T ${n}`, items.map(x => x.toUpperCase()), n + 1, notesFor('a, b'));\n"
            "addBulletSlide(...args);\n")
    assert _reasons(body) == []


def test_commas_and_parens_inside_strings_and_comments_do_not_split_args():
    body = ("addBulletSlide(deck, 'A, (b), c', [\n  // a comment, with (parens)\n"
            "  \"it's fine, really\",\n  `tmpl ${'x, y'} done`,\n], 2, 'n');\n")
    assert _reasons(body) == []


def test_helper_names_inside_strings_are_ignored():
    assert _reasons("addBulletSlide(deck, 'T', ['call addTableSlide(deck) later'], 2, 'n');\n") == []


def test_local_function_definition_is_not_a_call():
    assert _reasons("function addBulletSlide(a, b) { return a; }\n") == []
