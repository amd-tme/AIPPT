# Slides-as-Code Foundation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add source tracking to the catalog, implement the `---aippt-meta---` speaker notes metadata format, and update the create-deck skill to emit slide markers and metadata.

**Architecture:** Five new nullable columns on the `decks` table track source script path, engine, theme, outline path, and generation timestamp. A new `aippt/notes_meta.py` module handles parsing/serializing YAML metadata blocks in speaker notes (separate from the existing `metadata.py` which uses JSON `[AIPPT-META]` blocks for the improve pipeline). The create-deck skill gains slide marker comments and metadata in speaker notes.

**Tech Stack:** Python 3, SQLite, PyYAML (already a dependency), pytest, pptx

**Spec:** `docs/superpowers/specs/2026-03-11-slides-as-code-design.md` — Components 1, 3, 4

**Worktree:** `.worktrees/slides-foundation/` on branch `feature/slides-as-code-foundation`

**Running commands:** All test commands assume the agent is working inside the worktree directory (`.worktrees/slides-foundation/`). The venv is at the project root, so use `../../venv/bin/python` (or set `VENV_PYTHON` per CLAUDE.md). Example: `../../venv/bin/python -m pytest tests/test_notes_meta.py -v`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `aippt/schema.sql` | Modify | Add 5 new columns to `decks` CREATE TABLE |
| `aippt/catalog.py` | Modify | Migration tuples, `catalog_deck()` kwargs, `resolve_deck()` / `get_deck_by_id()` SELECT lists |
| `aippt/ingest.py` | Modify | `source_script_path` param, engine/theme auto-detection, `source_tracked` return field |
| `aippt/notes_meta.py` | Create | `---aippt-meta---` parser/serializer (separate from existing `metadata.py`) |
| `aippt/cli.py` | Modify | `--source`/`--theme` on ingest, `decks source` subcommand, `decks info` source display |
| `tests/test_notes_meta.py` | Create | Unit tests for notes metadata parsing/serialization |
| `tests/test_source_tracking.py` | Create | Unit tests for source detection, schema migration, catalog source fields |
| `tests/test_decks_cli.py` | Modify | Tests for `decks source` and `decks info` with source metadata |

**Existing `aippt/metadata.py` note:** The existing module uses `[AIPPT-META]` / `[/AIPPT-META]` delimiters with JSON content. It serves the improve pipeline (`aippt improve`). The new `notes_meta.py` uses `---aippt-meta---` / `---end-aippt-meta---` delimiters with YAML content. These are two separate metadata systems — the spec explicitly states they are complementary. PRD 3 will align the improve pipeline to use the new format for new decks.

---

## Chunk 1: Notes Metadata Parser/Serializer

### Task 1: Create `aippt/notes_meta.py` — Parser

**Files:**
- Create: `aippt/notes_meta.py`
- Create: `tests/test_notes_meta.py`

- [ ] **Step 1: Write failing tests for metadata extraction**

In `.worktrees/slides-foundation/tests/test_notes_meta.py`:

```python
"""Tests for aippt.notes_meta — ---aippt-meta--- parser/serializer."""

import pytest
from aippt.notes_meta import parse_notes_meta, serialize_notes_meta


class TestParseNotesMeta:
    def test_extracts_metadata_from_notes(self):
        notes = (
            "Speaker notes content here.\n\n"
            "---aippt-meta---\n"
            "source: outline → pptxgenjs\n"
            "created: 2026-03-11\n"
            "history:\n"
            "  - '2026-03-11: Created from outline (bullet layout)'\n"
            "layout: two_column\n"
            "theme: amd\n"
            "---end-aippt-meta---"
        )
        text, meta = parse_notes_meta(notes)
        assert text == "Speaker notes content here."
        assert meta["source"] == "outline → pptxgenjs"
        assert meta["created"] == "2026-03-11"
        assert meta["layout"] == "two_column"
        assert meta["theme"] == "amd"
        assert len(meta["history"]) == 1

    def test_no_metadata_returns_full_text_and_none(self):
        notes = "Just regular speaker notes."
        text, meta = parse_notes_meta(notes)
        assert text == "Just regular speaker notes."
        assert meta is None

    def test_empty_string(self):
        text, meta = parse_notes_meta("")
        assert text == ""
        assert meta is None

    def test_none_input(self):
        text, meta = parse_notes_meta(None)
        assert text == ""
        assert meta is None

    def test_metadata_only_no_notes(self):
        notes = (
            "---aippt-meta---\n"
            "source: outline → pptxgenjs\n"
            "created: 2026-03-11\n"
            "---end-aippt-meta---"
        )
        text, meta = parse_notes_meta(notes)
        assert text == ""
        assert meta["source"] == "outline → pptxgenjs"

    def test_malformed_yaml_returns_none(self):
        notes = (
            "Some notes\n\n"
            "---aippt-meta---\n"
            "this is: [not: valid: yaml\n"
            "---end-aippt-meta---"
        )
        text, meta = parse_notes_meta(notes)
        assert text == "Some notes"
        assert meta is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_notes_meta.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aippt.notes_meta'`

- [ ] **Step 3: Implement `parse_notes_meta()`**

Create `.worktrees/slides-foundation/aippt/notes_meta.py`:

```python
"""YAML metadata blocks in PPTX speaker notes (---aippt-meta--- format).

Tracks slide lineage for the slides-as-code pipeline: source engine,
creation date, layout type, theme, and edit history.

Separate from metadata.py which uses [AIPPT-META] JSON blocks for the
improve pipeline.
"""

import logging
import re
from typing import Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

META_START = "---aippt-meta---"
META_END = "---end-aippt-meta---"
MAX_HISTORY = 10

_META_RE = re.compile(
    re.escape(META_START) + r"\n(.*?)\n?" + re.escape(META_END),
    re.DOTALL,
)


def parse_notes_meta(notes: Optional[str]) -> Tuple[str, Optional[dict]]:
    """Extract human-readable notes and metadata from speaker notes.

    Returns:
        (notes_text, metadata_dict) — metadata is None if no block found
        or if YAML is malformed.
    """
    if not notes:
        return "", None

    match = _META_RE.search(notes)
    if not match:
        return notes.rstrip(), None

    # Everything before the metadata block is the human-readable notes
    text_before = notes[:match.start()].rstrip()
    try:
        meta = yaml.safe_load(match.group(1))
        if not isinstance(meta, dict):
            return text_before, None
        return text_before, meta
    except yaml.YAMLError:
        logger.warning("Malformed YAML in ---aippt-meta--- block; ignoring")
        return text_before, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_notes_meta.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd .worktrees/slides-foundation
git add aippt/notes_meta.py tests/test_notes_meta.py
git commit -m "feat(notes_meta): add ---aippt-meta--- parser for speaker notes"
```

### Task 2: Notes Metadata Serializer

**Files:**
- Modify: `aippt/notes_meta.py`
- Modify: `tests/test_notes_meta.py`

- [ ] **Step 1: Write failing tests for serialization**

Append to `tests/test_notes_meta.py`:

```python
class TestSerializeNotesMeta:
    def test_creates_metadata_block_with_notes(self):
        result = serialize_notes_meta(
            "My speaker notes",
            {
                "source": "outline → pptxgenjs",
                "created": "2026-03-11",
                "history": ["2026-03-11: Created from outline (bullet layout)"],
                "layout": "bullet",
                "theme": "amd",
            },
        )
        assert result.startswith("My speaker notes\n\n---aippt-meta---\n")
        assert result.endswith("\n---end-aippt-meta---")
        assert "source: " in result
        # Round-trip: parse it back
        text, meta = parse_notes_meta(result)
        assert text == "My speaker notes"
        assert meta["source"] == "outline → pptxgenjs"

    def test_metadata_only_no_notes(self):
        result = serialize_notes_meta("", {"source": "outline → pptxgenjs", "created": "2026-03-11"})
        assert result.startswith("---aippt-meta---\n")
        text, meta = parse_notes_meta(result)
        assert text == ""
        assert meta["source"] == "outline → pptxgenjs"

    def test_none_metadata_returns_notes_only(self):
        result = serialize_notes_meta("Just notes", None)
        assert result == "Just notes"

    def test_history_capped_at_10(self):
        history = [f"2026-03-{i:02d}: Edit {i}" for i in range(1, 16)]
        assert len(history) == 15
        result = serialize_notes_meta(
            "Notes",
            {"source": "test", "created": "2026-03-01", "history": history},
        )
        _, meta = parse_notes_meta(result)
        assert len(meta["history"]) == 10
        # Should keep the LAST 10 (most recent)
        assert meta["history"][0] == "2026-03-06: Edit 6"
        assert meta["history"][-1] == "2026-03-15: Edit 15"

    def test_replaces_existing_metadata(self):
        """Serializing with existing meta block should replace it, not append."""
        original = (
            "Old notes\n\n"
            "---aippt-meta---\n"
            "source: old\n"
            "---end-aippt-meta---"
        )
        text, _ = parse_notes_meta(original)
        result = serialize_notes_meta(text, {"source": "new", "created": "2026-03-12"})
        _, meta = parse_notes_meta(result)
        assert meta["source"] == "new"
        # Should not contain "old" in the metadata
        assert "old" not in result.split("---aippt-meta---")[1]
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_notes_meta.py::TestSerializeNotesMeta -v`
Expected: FAIL

- [ ] **Step 3: Implement `serialize_notes_meta()`**

Add to `aippt/notes_meta.py`:

```python
def serialize_notes_meta(notes_text: str, meta: Optional[dict]) -> str:
    """Combine human-readable notes with a ---aippt-meta--- block.

    Args:
        notes_text: Human-readable speaker notes (no metadata block).
        meta: Metadata dict to serialize as YAML. If None, returns notes_text as-is.

    Returns:
        Combined string with notes followed by the metadata block.
    """
    if meta is None:
        return notes_text

    # Cap history at MAX_HISTORY (keep most recent)
    meta = dict(meta)  # shallow copy to avoid mutating caller's dict
    if "history" in meta and len(meta["history"]) > MAX_HISTORY:
        meta["history"] = meta["history"][-MAX_HISTORY:]

    yaml_str = yaml.dump(meta, default_flow_style=False, sort_keys=False, allow_unicode=True).rstrip()
    meta_block = f"{META_START}\n{yaml_str}\n{META_END}"

    if notes_text.strip():
        return f"{notes_text}\n\n{meta_block}"
    return meta_block
```

- [ ] **Step 4: Run all notes_meta tests**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_notes_meta.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
cd .worktrees/slides-foundation
git add aippt/notes_meta.py tests/test_notes_meta.py
git commit -m "feat(notes_meta): add serializer with history cap at 10 entries"
```

### Task 3: History Append Helper

**Files:**
- Modify: `aippt/notes_meta.py`
- Modify: `tests/test_notes_meta.py`

- [ ] **Step 1: Write failing tests for append_history**

Append to `tests/test_notes_meta.py`:

```python
class TestAppendHistory:
    def test_appends_to_existing_history(self):
        meta = {
            "source": "outline → pptxgenjs",
            "created": "2026-03-11",
            "history": ["2026-03-11: Created from outline (bullet layout)"],
            "layout": "bullet",
            "theme": "amd",
        }
        append_history(meta, "Changed to two_column layout", "/edit-deck")
        assert len(meta["history"]) == 2
        assert meta["history"][1].endswith("[/edit-deck]")
        assert "two_column" in meta["history"][1]
        # Should have today's date prefix
        assert meta["history"][1].startswith("2026-")

    def test_creates_history_list_if_missing(self):
        meta = {"source": "test", "created": "2026-03-11"}
        append_history(meta, "Initial creation", "/create-deck")
        assert "history" in meta
        assert len(meta["history"]) == 1

    def test_caps_at_max_history(self):
        meta = {
            "source": "test",
            "created": "2026-03-01",
            "history": [f"2026-03-{i:02d}: Edit {i}" for i in range(1, 11)],
        }
        assert len(meta["history"]) == 10
        append_history(meta, "One more edit", "/edit-deck")
        assert len(meta["history"]) == 10  # still capped
        assert meta["history"][-1].endswith("[/edit-deck]")
        # Oldest entry should be trimmed
        assert "Edit 1" not in str(meta["history"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_notes_meta.py::TestAppendHistory -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement `append_history()`**

Add to `aippt/notes_meta.py`:

```python
from datetime import date


def append_history(meta: dict, description: str, source: str) -> None:
    """Append a history entry to a metadata dict (mutates in place).

    Format: "YYYY-MM-DD: description [source]"
    Caps at MAX_HISTORY entries (trims oldest).
    """
    entry = f"{date.today().isoformat()}: {description} [{source}]"
    if "history" not in meta:
        meta["history"] = []
    meta["history"].append(entry)
    if len(meta["history"]) > MAX_HISTORY:
        meta["history"] = meta["history"][-MAX_HISTORY:]
```

Also add `append_history` to the import in `tests/test_notes_meta.py`:

```python
from aippt.notes_meta import parse_notes_meta, serialize_notes_meta, append_history
```

- [ ] **Step 4: Run all notes_meta tests**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_notes_meta.py -v`
Expected: All 14 tests PASS

- [ ] **Step 5: Commit**

```bash
cd .worktrees/slides-foundation
git add aippt/notes_meta.py tests/test_notes_meta.py
git commit -m "feat(notes_meta): add append_history helper with date prefix and cap"
```

### Task 4: Initial Metadata Builder

**Files:**
- Modify: `aippt/notes_meta.py`
- Modify: `tests/test_notes_meta.py`

- [ ] **Step 1: Write failing test for `build_initial_meta()`**

Append to `tests/test_notes_meta.py`:

```python
from aippt.notes_meta import build_initial_meta


class TestBuildInitialMeta:
    def test_builds_complete_metadata(self):
        meta = build_initial_meta(
            engine="pptxgenjs",
            layout="bullet",
            theme="amd",
            outline_source=True,
        )
        assert meta["source"] == "outline → pptxgenjs"
        assert "created" in meta
        assert meta["layout"] == "bullet"
        assert meta["theme"] == "amd"
        assert len(meta["history"]) == 1
        assert "Created from outline" in meta["history"][0]

    def test_no_outline_source(self):
        meta = build_initial_meta(engine="python-pptx", layout="numbered")
        assert meta["source"] == "python-pptx"
        assert "Created" in meta["history"][0]

    def test_no_theme(self):
        meta = build_initial_meta(engine="pptxgenjs", layout="basic")
        assert "theme" not in meta
```

- [ ] **Step 2: Run to verify failure**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_notes_meta.py::TestBuildInitialMeta -v`
Expected: FAIL

- [ ] **Step 3: Implement `build_initial_meta()`**

Add to `aippt/notes_meta.py`:

```python
def build_initial_meta(
    engine: str,
    layout: str,
    theme: Optional[str] = None,
    outline_source: bool = False,
) -> dict:
    """Build the initial metadata dict for a newly created slide.

    Args:
        engine: 'pptxgenjs' or 'python-pptx'
        layout: Layout type (bullet, two_column, numbered, basic, diagram)
        theme: Theme name (amd, default, etc.) or None
        outline_source: True if the deck was generated from an outline

    Returns:
        Metadata dict ready for serialize_notes_meta()
    """
    source = f"outline → {engine}" if outline_source else engine
    today = date.today().isoformat()
    meta = {
        "source": source,
        "created": today,
        "history": [f"{today}: Created from outline ({layout} layout)" if outline_source
                    else f"{today}: Created ({layout} layout)"],
        "layout": layout,
    }
    if theme:
        meta["theme"] = theme
    return meta
```

- [ ] **Step 4: Run all notes_meta tests**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_notes_meta.py -v`
Expected: All 17 tests PASS

- [ ] **Step 5: Commit**

```bash
cd .worktrees/slides-foundation
git add aippt/notes_meta.py tests/test_notes_meta.py
git commit -m "feat(notes_meta): add build_initial_meta for create-deck integration"
```

---

## Chunk 2: Schema Migration & Source Tracking

### Task 5: Schema and Migration

**Files:**
- Modify: `aippt/schema.sql` (lines 4-17, `decks` table)
- Modify: `aippt/catalog.py` (lines 51-60, migration tuples)
- Create: `tests/test_source_tracking.py`

- [ ] **Step 1: Write failing test for migration**

Create `.worktrees/slides-foundation/tests/test_source_tracking.py`:

```python
"""Tests for source tracking: schema migration, detection, catalog integration."""

import os
import sqlite3
import tempfile

import pytest

from aippt.catalog import get_db


class TestSchemaMigration:
    def test_new_source_columns_exist_on_fresh_db(self):
        """Fresh database should have all 5 source columns."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = get_db(db_path)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(decks)").fetchall()}
            conn.close()
            assert "source_script_path" in cols
            assert "source_engine" in cols
            assert "source_theme" in cols
            assert "outline_path" in cols
            assert "source_generated_at" in cols
        finally:
            os.unlink(db_path)

    def test_migration_adds_columns_to_existing_db(self):
        """Columns should be added to a pre-existing database missing them."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            # Create a minimal DB without source columns
            conn = sqlite3.connect(db_path)
            conn.execute("""CREATE TABLE decks (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                slide_count INTEGER NOT NULL DEFAULT 0,
                cataloged_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""")
            conn.execute("""CREATE TABLE slides (
                id INTEGER PRIMARY KEY,
                deck_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                content_text TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                image_path TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""")
            conn.commit()
            conn.close()

            # Now open via get_db which runs migrations
            conn = get_db(db_path)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(decks)").fetchall()}
            conn.close()
            assert "source_script_path" in cols
            assert "source_engine" in cols
            assert "source_theme" in cols
            assert "outline_path" in cols
            assert "source_generated_at" in cols
        finally:
            os.unlink(db_path)

    def test_migration_is_idempotent(self):
        """Running get_db twice should not fail."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn1 = get_db(db_path)
            conn1.close()
            conn2 = get_db(db_path)
            cols = {row[1] for row in conn2.execute("PRAGMA table_info(decks)").fetchall()}
            conn2.close()
            assert "source_script_path" in cols
        finally:
            os.unlink(db_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_source_tracking.py::TestSchemaMigration -v`
Expected: FAIL — columns not found

- [ ] **Step 3: Update `schema.sql`**

In `.worktrees/slides-foundation/aippt/schema.sql`, add 5 columns to the `decks` CREATE TABLE (after `description` line 16, before the closing `);` on line 17):

```sql
    source_script_path TEXT DEFAULT NULL,
    source_engine TEXT DEFAULT NULL,
    source_theme TEXT DEFAULT NULL,
    outline_path TEXT DEFAULT NULL,
    source_generated_at TEXT DEFAULT NULL
```

- [ ] **Step 4: Add migration tuples in `catalog.py`**

In `.worktrees/slides-foundation/aippt/catalog.py`, add to the decks migration tuple list (after the `description` entry at line 56, before the closing `):` at line 57):

```python
        ("source_script_path TEXT DEFAULT NULL", "source_script_path"),
        ("source_engine TEXT DEFAULT NULL", "source_engine"),
        ("source_theme TEXT DEFAULT NULL", "source_theme"),
        ("outline_path TEXT DEFAULT NULL", "outline_path"),
        ("source_generated_at TEXT DEFAULT NULL", "source_generated_at"),
```

- [ ] **Step 5: Run migration tests**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_source_tracking.py::TestSchemaMigration -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Run full test suite to check for regressions**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/ -v --timeout=30`
Expected: All existing tests PASS (schema changes are additive, nullable columns)

- [ ] **Step 7: Commit**

```bash
cd .worktrees/slides-foundation
git add aippt/schema.sql aippt/catalog.py tests/test_source_tracking.py
git commit -m "feat(catalog): add 5 source tracking columns to decks table"
```

### Task 6: Engine and Theme Auto-Detection

**Files:**
- Modify: `aippt/ingest.py`
- Modify: `tests/test_source_tracking.py`

- [ ] **Step 1: Write failing tests for detection functions**

Append to `tests/test_source_tracking.py`:

```python
import tempfile

from aippt.ingest import detect_source_engine, detect_source_theme


class TestEngineDetection:
    def test_detects_pptxgenjs_require_single_quotes(self):
        script = "const PptxGenJS = require('pptxgenjs');\nlet pptx = new PptxGenJS();\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(script)
            f.flush()
            assert detect_source_engine(f.name) == "pptxgenjs"
            os.unlink(f.name)

    def test_detects_pptxgenjs_require_double_quotes(self):
        script = 'const PptxGenJS = require("pptxgenjs");\n'
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(script)
            f.flush()
            assert detect_source_engine(f.name) == "pptxgenjs"
            os.unlink(f.name)

    def test_detects_pptxgenjs_esm_import(self):
        script = "import { createDeck, addTitleSlide } from '../lib/pptxgenjs-helpers.mjs';\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False) as f:
            f.write(script)
            f.flush()
            assert detect_source_engine(f.name) == "pptxgenjs"
            os.unlink(f.name)

    def test_detects_python_pptx_from_import(self):
        script = "from pptx import Presentation\nprs = Presentation()\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            f.flush()
            assert detect_source_engine(f.name) == "python-pptx"
            os.unlink(f.name)

    def test_detects_python_pptx_import_pptx(self):
        script = "import pptx\nprs = pptx.Presentation()\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            f.flush()
            assert detect_source_engine(f.name) == "python-pptx"
            os.unlink(f.name)

    def test_returns_none_for_unknown(self):
        script = "print('hello world')\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(script)
            f.flush()
            assert detect_source_engine(f.name) is None
            os.unlink(f.name)

    def test_first_match_wins_by_line_number(self):
        script = "const PptxGenJS = require('pptxgenjs');\nfrom pptx import Presentation\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(script)
            f.flush()
            assert detect_source_engine(f.name) == "pptxgenjs"
            os.unlink(f.name)

    def test_nonexistent_file_returns_none(self):
        assert detect_source_engine("/nonexistent/path.js") is None


class TestThemeDetection:
    def test_detects_amd_theme(self):
        script = "const theme = loadYaml('themes/amd.yaml');\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(script)
            f.flush()
            assert detect_source_theme(f.name) == "amd"
            os.unlink(f.name)

    def test_detects_default_theme(self):
        script = "theme_path = 'themes/default.yaml'\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            f.flush()
            assert detect_source_theme(f.name) == "default"
            os.unlink(f.name)

    def test_returns_none_when_no_theme(self):
        script = "print('no theme here')\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            f.flush()
            assert detect_source_theme(f.name) is None
            os.unlink(f.name)

    def test_nonexistent_file_returns_none(self):
        assert detect_source_theme("/nonexistent/path.js") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_source_tracking.py::TestEngineDetection tests/test_source_tracking.py::TestThemeDetection -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement detection functions in `ingest.py`**

Add to `.worktrees/slides-foundation/aippt/ingest.py` (before the `ingest_deck` function):

```python
import re

_ENGINE_PATTERNS = [
    (re.compile(r"""require\(['""]pptxgenjs['"]\)"""), "pptxgenjs"),
    (re.compile(r"pptxgenjs-helpers\.mjs"), "pptxgenjs"),
    (re.compile(r"(?:from pptx import|import pptx)"), "python-pptx"),
]

_THEME_RE = re.compile(r"themes/(\w+)\.yaml")


def detect_source_engine(script_path: str) -> Optional[str]:
    """Auto-detect engine from script content (first 50 lines).

    Returns 'pptxgenjs', 'python-pptx', or None.
    """
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            lines = [f.readline() for _ in range(50)]
    except (OSError, UnicodeDecodeError):
        return None

    for i, line in enumerate(lines):
        for pattern, engine in _ENGINE_PATTERNS:
            if pattern.search(line):
                return engine
    return None


def detect_source_theme(script_path: str) -> Optional[str]:
    """Auto-detect theme from theme YAML path references (first 50 lines).

    Returns theme stem (e.g., 'amd', 'default') or None.
    """
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            lines = [f.readline() for _ in range(50)]
    except (OSError, UnicodeDecodeError):
        return None

    for line in lines:
        match = _THEME_RE.search(line)
        if match:
            return match.group(1)
    return None
```

- [ ] **Step 4: Run detection tests**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_source_tracking.py::TestEngineDetection tests/test_source_tracking.py::TestThemeDetection -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
cd .worktrees/slides-foundation
git add aippt/ingest.py tests/test_source_tracking.py
git commit -m "feat(ingest): add engine and theme auto-detection from script content"
```

### Task 7: `catalog_deck()` Source Fields

**Files:**
- Modify: `aippt/catalog.py` (lines 94-99, 162-185)
- Modify: `tests/test_source_tracking.py`

- [ ] **Step 1: Write failing tests for catalog_deck with source fields**

Append to `tests/test_source_tracking.py`:

```python
from unittest.mock import patch, MagicMock
from aippt.catalog import catalog_deck, get_db, resolve_deck


class TestCatalogDeckSourceFields:
    @pytest.fixture
    def db_and_pptx(self, tmp_path):
        """Create a temp DB and a minimal PPTX for testing."""
        db_path = str(tmp_path / "test.db")
        pptx_path = str(tmp_path / "test.pptx")
        # Create minimal PPTX
        from pptx import Presentation
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
        prs.save(pptx_path)
        return db_path, pptx_path

    def test_stores_source_fields_on_insert(self, db_and_pptx):
        db_path, pptx_path = db_and_pptx
        deck_id = catalog_deck(
            pptx_path,
            db_path=db_path,
            source_script_path="output/test.js",
            source_engine="pptxgenjs",
            source_theme="amd",
            outline_path="outlines/test.md",
        )
        conn = get_db(db_path)
        row = conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
        conn.close()
        assert row["source_script_path"] == "output/test.js"
        assert row["source_engine"] == "pptxgenjs"
        assert row["source_theme"] == "amd"
        assert row["outline_path"] == "outlines/test.md"
        assert row["source_generated_at"] is not None

    def test_null_source_fields_by_default(self, db_and_pptx):
        db_path, pptx_path = db_and_pptx
        deck_id = catalog_deck(pptx_path, db_path=db_path)
        conn = get_db(db_path)
        row = conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
        conn.close()
        assert row["source_script_path"] is None
        assert row["source_engine"] is None
        assert row["source_theme"] is None
        assert row["outline_path"] is None
        assert row["source_generated_at"] is None

    def test_preserves_source_on_recatalog(self, db_and_pptx, tmp_path):
        db_path, pptx_path = db_and_pptx
        # First catalog with source
        deck_id = catalog_deck(
            pptx_path,
            db_path=db_path,
            source_script_path="output/test.js",
            source_engine="pptxgenjs",
        )
        # Modify PPTX to change hash
        from pptx import Presentation
        prs = Presentation(pptx_path)
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(pptx_path)
        # Re-catalog without source fields
        deck_id2 = catalog_deck(pptx_path, db_path=db_path)
        assert deck_id == deck_id2
        conn = get_db(db_path)
        row = conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
        conn.close()
        # Source fields should be preserved
        assert row["source_script_path"] == "output/test.js"
        assert row["source_engine"] == "pptxgenjs"

    def test_source_generated_at_updates_for_source_tracked_decks(self, db_and_pptx, tmp_path):
        db_path, pptx_path = db_and_pptx
        deck_id = catalog_deck(
            pptx_path, db_path=db_path,
            source_script_path="output/test.js",
        )
        conn = get_db(db_path)
        row1 = conn.execute("SELECT source_generated_at FROM decks WHERE id = ?", (deck_id,)).fetchone()
        conn.close()
        ts1 = row1["source_generated_at"]

        # Modify and re-catalog
        from pptx import Presentation
        prs = Presentation(pptx_path)
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(pptx_path)

        catalog_deck(pptx_path, db_path=db_path)
        conn = get_db(db_path)
        row2 = conn.execute("SELECT source_generated_at FROM decks WHERE id = ?", (deck_id,)).fetchone()
        conn.close()
        assert row2["source_generated_at"] is not None
        # Timestamp should have been updated (or same if fast enough)
        assert row2["source_generated_at"] >= ts1

    def test_source_generated_at_stays_null_for_non_source_decks(self, db_and_pptx, tmp_path):
        db_path, pptx_path = db_and_pptx
        # Catalog without source
        deck_id = catalog_deck(pptx_path, db_path=db_path)
        # Modify and re-catalog (still no source)
        from pptx import Presentation
        prs = Presentation(pptx_path)
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(pptx_path)
        catalog_deck(pptx_path, db_path=db_path)
        conn = get_db(db_path)
        row = conn.execute("SELECT source_generated_at FROM decks WHERE id = ?", (deck_id,)).fetchone()
        conn.close()
        assert row["source_generated_at"] is None
```

- [ ] **Step 2: Run to verify failures**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_source_tracking.py::TestCatalogDeckSourceFields -v`
Expected: FAIL — `catalog_deck()` doesn't accept source kwargs

- [ ] **Step 3: Update `catalog_deck()` signature and logic**

In `.worktrees/slides-foundation/aippt/catalog.py`, update `catalog_deck()`:

**Signature** (line 94-99) — add source kwargs:

```python
def catalog_deck(
    deck_path: str,
    db_path: str = "slides.db",
    images_dir: Optional[str] = None,
    base_dir: Optional[str] = None,
    source_script_path: Optional[str] = None,
    source_engine: Optional[str] = None,
    source_theme: Optional[str] = None,
    outline_path: Optional[str] = None,
) -> int:
```

**INSERT branch** (around line 176-185) — add source columns:

```python
    else:
        source_generated_at = (
            datetime.now().isoformat() if source_script_path else None
        )
        cur = conn.execute(
            """INSERT INTO decks (name, file_path, file_hash, slide_count,
                                  author, created_date, modified_date,
                                  subject, description,
                                  source_script_path, source_engine,
                                  source_theme, outline_path,
                                  source_generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (deck_name, deck_path, fhash, len(prs.slides),
             deck_author, deck_created_date, deck_modified_date,
             deck_subject, deck_description,
             source_script_path, source_engine, source_theme,
             outline_path, source_generated_at),
        )
        deck_id = cur.lastrowid
```

**UPDATE branch** (around line 162-174) — preserve source fields, conditionally update timestamp:

```python
    if existing_deck:
        deck_id = existing_deck["id"]
        # Build source field updates: preserve existing unless new values passed
        source_updates = []
        source_params = []
        for col, val in [
            ("source_script_path", source_script_path),
            ("source_engine", source_engine),
            ("source_theme", source_theme),
            ("outline_path", outline_path),
        ]:
            if val is not None:
                source_updates.append(f"{col} = ?")
                source_params.append(val)

        # source_generated_at: auto-update only for source-tracked decks
        existing_source = conn.execute(
            "SELECT source_script_path FROM decks WHERE id = ?", (deck_id,)
        ).fetchone()
        has_source = (source_script_path is not None or
                      (existing_source and existing_source["source_script_path"] is not None))
        if has_source:
            source_updates.append("source_generated_at = ?")
            source_params.append(datetime.now().isoformat())

        source_clause = (", " + ", ".join(source_updates)) if source_updates else ""
        conn.execute(
            f"""UPDATE decks
               SET file_hash = ?, slide_count = ?, author = ?, modified_date = ?,
                   subject = ?, description = ?,
                   updated_at = datetime('now'){source_clause}
               WHERE id = ?""",
            (fhash, len(prs.slides), deck_author, deck_modified_date,
             deck_subject, deck_description, *source_params, deck_id),
        )
        # Remove old slides for re-catalog
        conn.execute("DELETE FROM slides WHERE deck_id = ?", (deck_id,))
```

- [ ] **Step 4: Run source tracking tests**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_source_tracking.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite for regressions**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd .worktrees/slides-foundation
git add aippt/catalog.py tests/test_source_tracking.py
git commit -m "feat(catalog): catalog_deck() accepts source tracking fields"
```

### Task 8: Update `resolve_deck()` and `get_deck_by_id()` SELECT Lists

**Files:**
- Modify: `aippt/catalog.py` (lines 514-518, 538-551)

- [ ] **Step 1: Update `get_deck_by_id()` to include source columns**

In `catalog.py`, update the SELECT in `get_deck_by_id()` (line 516) to include the 5 new columns:

```python
    row = conn.execute(
        """SELECT id, name, file_path, file_hash, slide_count, author,
                  cataloged_at, updated_at, subject, description,
                  source_script_path, source_engine, source_theme,
                  outline_path, source_generated_at
           FROM decks WHERE id = ?""",
        (deck_id,),
    ).fetchone()
```

- [ ] **Step 2: Update `resolve_deck()` SELECTs**

Update both SELECT statements in `resolve_deck()` (lines 540 and 550) to include source columns:

```python
        row = conn.execute(
            """SELECT id, name, file_path, file_hash, slide_count, author,
                      subject, description, cataloged_at, updated_at,
                      source_script_path, source_engine, source_theme,
                      outline_path, source_generated_at
               FROM decks WHERE id = ?""",
            (deck_id,),
        ).fetchone()
```

And the name-match query:

```python
    rows = conn.execute(
        """SELECT id, name, file_path, file_hash, slide_count, author,
                  subject, description, cataloged_at, updated_at,
                  source_script_path, source_engine, source_theme,
                  outline_path, source_generated_at
           FROM decks WHERE name LIKE ? COLLATE NOCASE""",
        (f"%{identifier}%",),
    ).fetchall()
```

- [ ] **Step 3: Run existing tests to verify no regressions**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_catalog.py tests/test_decks_cli.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
cd .worktrees/slides-foundation
git add aippt/catalog.py
git commit -m "feat(catalog): include source columns in resolve_deck and get_deck_by_id"
```

---

## Chunk 3: Ingest Pipeline & CLI

### Task 9: `ingest_deck()` Source Parameter

**Files:**
- Modify: `aippt/ingest.py`
- Modify: `tests/test_source_tracking.py`

- [ ] **Step 1: Write failing test for ingest with source**

Append to `tests/test_source_tracking.py`:

```python
from aippt.ingest import ingest_deck


class TestIngestWithSource:
    @pytest.fixture
    def deck_and_script(self, tmp_path):
        """Create a minimal PPTX and a fake JS script."""
        pptx_path = str(tmp_path / "test.pptx")
        script_path = str(tmp_path / "test.js")
        from pptx import Presentation
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(pptx_path)
        with open(script_path, "w") as f:
            f.write("const PptxGenJS = require('pptxgenjs');\n// rest of script\n")
        return str(tmp_path), pptx_path, script_path

    def test_ingest_with_source_returns_source_tracked(self, deck_and_script):
        base, pptx_path, script_path = deck_and_script
        db_path = os.path.join(base, "test.db")
        result = ingest_deck(
            pptx_path,
            db_path=db_path,
            source_script_path=script_path,
            require_images=False,
        )
        assert result["source_tracked"] is True
        assert result["deck_id"] > 0

    def test_ingest_without_source_returns_not_tracked(self, deck_and_script):
        base, pptx_path, _ = deck_and_script
        db_path = os.path.join(base, "test.db")
        result = ingest_deck(
            pptx_path,
            db_path=db_path,
            require_images=False,
        )
        assert result["source_tracked"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_source_tracking.py::TestIngestWithSource -v`
Expected: FAIL — `ingest_deck()` doesn't accept `source_script_path`

- [ ] **Step 3: Update `ingest_deck()`**

In `.worktrees/slides-foundation/aippt/ingest.py`, update the function signature (add after `require_images` param):

```python
def ingest_deck(
    deck_path: str,
    db_path: str = "slides.db",
    images_dir: Optional[str] = None,
    generate_tags: bool = False,
    taxonomy: Optional[str] = None,
    model: Optional[str] = None,
    gateway_config: Optional[str] = None,
    api_key: Optional[str] = None,
    width: int = 1920,
    height: int = 1080,
    require_images: bool = True,
    source_script_path: Optional[str] = None,
    source_theme_override: Optional[str] = None,
    outline_path: Optional[str] = None,
    progress_callback: Optional[callable] = None,
) -> dict:
```

Update the catalog call (line 96) to pass source fields:

```python
    # --- Step 2: Catalog ---
    _progress("catalog", "Cataloging deck...")

    # Auto-detect engine and theme from source script
    source_engine = None
    source_theme = source_theme_override
    if source_script_path:
        source_engine = detect_source_engine(source_script_path)
        if source_theme is None:
            source_theme = detect_source_theme(source_script_path)

    deck_id = catalog_deck(
        deck_path,
        db_path=db_path,
        images_dir=images_dir,
        source_script_path=source_script_path,
        source_engine=source_engine,
        source_theme=source_theme,
        outline_path=outline_path,
    )
    source_tracked = source_script_path is not None
    _progress("catalog_done", f"Cataloged as deck_id={deck_id}")
```

Update the return dict (line 131) to include `source_tracked`:

```python
    return {
        "deck_id": deck_id,
        "deck_name": deck_name,
        "slide_count": slide_count,
        "images_dir": images_dir,
        "images_exported": images_exported,
        "tags_generated": tags_generated,
        "source_tracked": source_tracked,
    }
```

- [ ] **Step 4: Run ingest tests**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_source_tracking.py::TestIngestWithSource -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd .worktrees/slides-foundation
git add aippt/ingest.py tests/test_source_tracking.py
git commit -m "feat(ingest): add source_script_path param with auto-detection"
```

### Task 10: CLI `--source` and `--theme` Flags on Ingest

**Files:**
- Modify: `aippt/cli.py` (ingest argparse + cmd_ingest)
- Modify: `tests/test_source_tracking.py`

- [ ] **Step 1: Add `--source` and `--theme` args to ingest subparser**

In `.worktrees/slides-foundation/aippt/cli.py`, after the `--height` argument (line 1453), add:

```python
    p_ingest.add_argument("--source", default=None,
                          help="Path to source script (JS/Python) for source tracking")
    p_ingest.add_argument("--theme", default=None,
                          help="Theme name override (auto-detected from script if not provided)")
    p_ingest.add_argument("--outline", default=None,
                          help="Path to originating markdown outline")
```

- [ ] **Step 2: Pass args through in `cmd_ingest()`**

In `cmd_ingest()` (around line 905-916), update the `ingest_deck()` call:

```python
        result = ingest_deck(
            deck_path=args.deck,
            db_path=db_path,
            images_dir=images_dir,
            generate_tags=args.tags,
            taxonomy=args.taxonomy,
            model=args.model,
            gateway_config=args.gateway_config,
            api_key=getattr(args, 'api_key', None),
            width=args.width,
            height=args.height,
            source_script_path=getattr(args, 'source', None),
            source_theme_override=getattr(args, 'theme', None),
            outline_path=getattr(args, 'outline', None),
            progress_callback=progress,
        )
```

Update the summary output (around line 925-934) to show source tracking:

```python
    print(f"\n{'=' * 50}")
    print(f"INGEST COMPLETE")
    print(f"{'=' * 50}")
    print(f"  Deck: {args.deck}")
    print(f"  Deck ID: {result['deck_id']}")
    print(f"  Images: {result['images_dir']}")
    print(f"  Database: {args.db}")
    if result['tags_generated']:
        print(f"  Tags: generated")
    if result.get('source_tracked'):
        print(f"  Source: tracked ({getattr(args, 'source', 'N/A')})")
    print(f"{'=' * 50}\n")
```

- [ ] **Step 3: Run full test suite**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/ -v --timeout=30`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
cd .worktrees/slides-foundation
git add aippt/cli.py
git commit -m "feat(cli): add --source and --theme flags to ingest command"
```

### Task 11: `decks source` Subcommand

**Files:**
- Modify: `aippt/cli.py` (decks subparser + cmd_decks)
- Modify: `tests/test_decks_cli.py`

- [ ] **Step 1: Add `source` action to decks subparser**

In `.worktrees/slides-foundation/aippt/cli.py`, after the `p_decks_delete` block (around line 1439), add:

```python
    p_decks_source = decks_sub.add_parser("source", help="Show source script path for a deck")
    p_decks_source.add_argument("deck", help="Deck ID or name substring")
    p_decks_source.add_argument("--db", default="slides.db")
    p_decks_source.add_argument("--cat", action="store_true", help="Print the script contents")
```

- [ ] **Step 2: Add `source` action handling in `cmd_decks()`**

In `cmd_decks()`, add a new action branch (after the `info` action, before `rename`):

```python
    if action == "source":
        result = resolve_deck(args.deck, db_path=args.db)
        if result is None:
            print(f"No deck found matching '{args.deck}'")
            return 1
        if isinstance(result, list):
            print(f"Multiple decks match '{args.deck}':")
            for d in result:
                print(f"  ID {d['id']}: {display_name(d['name'])}")
            return 1

        deck = result
        script_path = deck.get("source_script_path")
        if not script_path:
            print(f"No source script tracked for '{display_name(deck['name'])}'")
            print("Hint: provide a direct script path instead, or re-ingest with --source")
            return 1

        if getattr(args, "cat", False):
            abs_path = os.path.abspath(script_path)
            if not os.path.exists(abs_path):
                print(f"Source script not found: {script_path}")
                return 1
            with open(abs_path, "r", encoding="utf-8") as f:
                print(f.read())
        else:
            print(script_path)
        return 0
```

- [ ] **Step 3: Update `decks info` to show source metadata**

In the `info` action of `cmd_decks()`, after the "Updated" line (around line 637-638), add:

```python
        if deck.get("source_script_path"):
            print(f"\nSource Tracking:")
            print(f"  Script: {deck['source_script_path']}")
            if deck.get("source_engine"):
                print(f"  Engine: {deck['source_engine']}")
            if deck.get("source_theme"):
                print(f"  Theme: {deck['source_theme']}")
            if deck.get("outline_path"):
                print(f"  Outline: {deck['outline_path']}")
            if deck.get("source_generated_at"):
                print(f"  Generated: {deck['source_generated_at']}")
```

Also update the JSON output in `info` to include source fields:

```python
        if getattr(args, "json", False):
            data = dict(deck)
            data["display_name"] = display_name(deck["name"])
            data["slides"] = [{"position": s["position"], "title": s["title"]} for s in slides]
            data["sections"] = sections
            data["tag_count"] = tag_count
            data["top_tags"] = [{"name": t[0], "count": t[1]} for t in top_tags]
            # Source tracking fields are already in the deck dict from resolve_deck
            print(json_mod.dumps(data, indent=2))
            return 0
```

- [ ] **Step 4: Write tests for `decks source` and `decks info` with source fields**

Append to `tests/test_source_tracking.py`:

```python
class TestDecksSourceCommand:
    @pytest.fixture
    def tracked_deck(self, tmp_path):
        from pptx import Presentation
        from aippt.catalog import catalog_deck
        pptx_path = str(tmp_path / "test.pptx")
        script_path = str(tmp_path / "test.js")
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(pptx_path)
        with open(script_path, "w") as f:
            f.write("const PptxGenJS = require('pptxgenjs');\n")
        db_path = str(tmp_path / "test.db")
        deck_id = catalog_deck(
            pptx_path, db_path=db_path,
            source_script_path="output/test.js",
            source_engine="pptxgenjs",
            source_theme="amd",
            outline_path="outlines/test.md",
        )
        return db_path, deck_id

    def test_source_command_prints_path(self, tracked_deck, capsys):
        from aippt.cli import cmd_decks
        import argparse
        db_path, deck_id = tracked_deck
        args = argparse.Namespace(
            decks_action="source", deck=str(deck_id),
            db=db_path, cat=False,
        )
        rc = cmd_decks(args)
        assert rc == 0
        assert "output/test.js" in capsys.readouterr().out

    def test_source_command_no_source(self, tmp_path, capsys):
        from pptx import Presentation
        from aippt.catalog import catalog_deck
        from aippt.cli import cmd_decks
        import argparse
        pptx_path = str(tmp_path / "nosource.pptx")
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(pptx_path)
        db_path = str(tmp_path / "test.db")
        deck_id = catalog_deck(pptx_path, db_path=db_path)
        args = argparse.Namespace(
            decks_action="source", deck=str(deck_id),
            db=db_path, cat=False,
        )
        rc = cmd_decks(args)
        assert rc == 1
        assert "No source script tracked" in capsys.readouterr().out

    def test_info_shows_source_tracking(self, tracked_deck, capsys):
        from aippt.cli import cmd_decks
        import argparse
        db_path, deck_id = tracked_deck
        args = argparse.Namespace(
            decks_action="info", deck=str(deck_id),
            db=db_path, json=False,
        )
        rc = cmd_decks(args)
        assert rc == 0
        output = capsys.readouterr().out
        assert "Source Tracking:" in output
        assert "pptxgenjs" in output
        assert "amd" in output
```

- [ ] **Step 5: Run tests**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/test_source_tracking.py::TestDecksSourceCommand -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/ -v --timeout=30`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
cd .worktrees/slides-foundation
git add aippt/cli.py tests/test_source_tracking.py
git commit -m "feat(cli): add 'decks source' command and source metadata in 'decks info'"
```

---

## Chunk 4: Create-Deck Skill Updates

### Task 12: Slide Markers in Create-Deck Prompts

The create-deck skill is a Claude Code skill (`.claude/skills/create-deck/SKILL.md` and reference files). Updating it means editing the skill's prompt guidance and reference documentation so the LLM generates scripts with slide markers and metadata.

**Files:**
- Modify: `.claude/skills/create-deck/SKILL.md` (handoff section, ~lines 398-434)
- Modify: `.claude/skills/create-deck/references/pptxgenjs-guide.md` (code examples)
- Modify: `.claude/skills/create-deck/references/sectioned-generation.md` (if it has code templates)

**Important:** Since `.claude/` is gitignored, use `git add -f` for these files.

- [ ] **Step 1: Add slide marker pattern to pptxgenjs-guide.md**

Read the current pptxgenjs-guide.md in the worktree. Find the section with code generation examples/patterns. Add a requirement that each slide block must start with a comment marker:

```javascript
// ═══ Slide 1: Title Slide ═══
```

And the Python equivalent in any python-pptx examples:

```python
# ═══ Slide 1: Title Slide ═══
```

The exact location depends on the current file structure — read it first, then add the marker guidance in the code patterns section.

- [ ] **Step 2: Add metadata in speaker notes guidance**

In the pptxgenjs-guide.md (or SKILL.md if more appropriate), add guidance that each slide's `addNotes()` call should include the initial `---aippt-meta---` block. Example:

```javascript
slide.addNotes(`Speaker notes content here.

---aippt-meta---
source: outline → pptxgenjs
created: ${new Date().toISOString().split('T')[0]}
history:
  - "${new Date().toISOString().split('T')[0]}: Created from outline (${layoutType} layout)"
layout: ${layoutType}
theme: ${themeName}
---end-aippt-meta---`);
```

- [ ] **Step 3: Update SKILL.md handoff to pass `--source`**

In SKILL.md's "Output & Handoff" section (around line 418), update the ingest command:

```
- aippt ingest output/{name}.pptx --source output/{name}.mjs — Catalog with source tracking
```

- [ ] **Step 4: Commit**

```bash
cd .worktrees/slides-foundation
git add -f .claude/skills/create-deck/SKILL.md .claude/skills/create-deck/references/pptxgenjs-guide.md
git commit -m "feat(create-deck): add slide markers, metadata in notes, --source in handoff"
```

### Task 13: Update Sectioned Generation Reference

**Files:**
- Modify: `.claude/skills/create-deck/references/sectioned-generation.md`

- [ ] **Step 1: Read the sectioned generation reference**

Read the file to understand its code templates.

- [ ] **Step 2: Add slide marker requirement to section code templates**

Ensure that each section's generated code includes the `// ═══ Slide N: Title ═══` marker pattern. The slide numbering must be global across sections (not per-section), so the template should accept a `startSlideNumber` parameter or use a comment that the assembler updates.

- [ ] **Step 3: Add metadata block to section templates' speaker notes**

Same `---aippt-meta---` pattern as Task 12.

- [ ] **Step 4: Commit**

```bash
cd .worktrees/slides-foundation
git add -f .claude/skills/create-deck/references/sectioned-generation.md
git commit -m "feat(create-deck): add slide markers and metadata to sectioned generation"
```

---

## Chunk 5: Test Plan & Final Verification

### Task 14: Write the Standalone Test Plan

**Files:**
- Create: `docs/plans/slides-as-code-test-plan.md`

- [ ] **Step 1: Write the test plan**

Create `docs/plans/slides-as-code-test-plan.md` with:

1. **Unit test matrix** for each PRD (PRD 1 tests from this plan, PRD 2 and 3 placeholders)
2. **Integration test scenarios:**
   - Schema migration on existing DB with data
   - Ingest with `--source` → `decks info` shows source → `decks source` prints path
   - Re-ingest preserves source metadata
   - `source_generated_at` conditional behavior
3. **Cross-PRD E2E scenarios** (placeholders for future PRDs):
   - create-outline → create-deck → edit-deck → verify metadata
   - create-outline → create-deck → deck-review → edit-deck → verify
   - Source tracking round-trip: generate → ingest → `decks info` → verify
4. **Manual QA checklist** for edit-deck skill (PRD 2 placeholder)

- [ ] **Step 2: Commit**

```bash
cd .worktrees/slides-foundation
git add docs/plans/slides-as-code-test-plan.md
git commit -m "docs: add slides-as-code cross-PRD test plan"
```

### Task 15: Final Verification

- [ ] **Step 1: Run full test suite in worktree**

Run: `cd .worktrees/slides-foundation && venv/bin/python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS, including all new tests from this PRD

- [ ] **Step 2: Verify test count increased**

Compare test count before and after. Should have added approximately:
- 6 tests in `TestParseNotesMeta`
- 5 tests in `TestSerializeNotesMeta`
- 3 tests in `TestAppendHistory`
- 3 tests in `TestBuildInitialMeta`
- 3 tests in `TestSchemaMigration`
- 12 tests in `TestEngineDetection` + `TestThemeDetection`
- 5 tests in `TestCatalogDeckSourceFields`
- 2 tests in `TestIngestWithSource`
- 3 tests in `TestDecksSourceCommand`

Total: ~42 new tests

- [ ] **Step 3: Review git log**

Run: `cd .worktrees/slides-foundation && git log --oneline`
Verify all commits are on the `feature/slides-as-code-foundation` branch with clean, descriptive messages.

- [ ] **Step 4: Check for uncommitted changes**

Run: `cd .worktrees/slides-foundation && git status`
Expected: Clean working directory
