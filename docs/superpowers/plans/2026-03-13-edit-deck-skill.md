# Edit-Deck Skill Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the `/edit-deck` Claude Code skill that enables conversational editing of deck source code — the third skill in the slides-as-code closed loop (create-deck → deck-review → edit-deck).

**Architecture:** A new skill at `.claude/skills/edit-deck/` with SKILL.md defining the 8-step workflow (resolve source → read context → LLM edit → diff preview → apply → regenerate → update metadata → continue/handoff) plus 3 reference files for edit patterns, error recovery, and examples. A thin Python helper module `aippt/source_resolver.py` provides programmatic source lookup from the catalog.

**Tech Stack:** Claude Code skill (markdown prompts), Python 3, pptx, node.js (for pptxgenjs scripts)

**Spec:** `docs/superpowers/specs/2026-03-11-slides-as-code-design.md` — Component 2

**Worktree:** `.worktrees/edit-deck/` on branch `feature/edit-deck-skill`

**Depends on:** PRD 1 (Foundation) must be fully merged before running tests. Specifically requires: schema columns `source_script_path`/`source_engine` on `decks` table, `catalog_deck()` source kwargs (PRD 1 Task 7), `resolve_deck()` SELECT lists including source columns (PRD 1 Task 8), `notes_meta.py` module (PRD 1 Tasks 1-4), `detect_source_engine()` in `ingest.py` (PRD 1 Task 6), slide markers in generated scripts (PRD 1 Task 12)

**Running commands:** All commands assume the agent is working inside the worktree directory (`.worktrees/edit-deck/`). The venv is at the project root, so use `../../venv/bin/python`. Example: `../../venv/bin/python -m pytest tests/test_source_resolver.py -v`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `aippt/source_resolver.py` | Create | Resolve deck name → source script path via catalog; engine detection; backup management |
| `.claude/skills/edit-deck/SKILL.md` | Create | Skill workflow: argument parsing, 8-step edit loop, capabilities, safety, troubleshooting |
| `.claude/skills/edit-deck/references/edit-patterns.md` | Create | Script editing patterns: single-slide edits, deck-level operations, diff format |
| `.claude/skills/edit-deck/references/error-recovery.md` | Create | Error handling: syntax errors, file locks, backup restore, LLM fix attempts |
| `.claude/skills/edit-deck/references/edit-examples.md` | Create | Concrete before/after examples for common edits (layout change, add notes, reorder) |
| `tests/test_source_resolver.py` | Create | Unit tests for source resolution, backup management |

**Why a separate `source_resolver.py`?** The edit-deck skill needs to: (1) look up script paths from deck names, (2) detect which engine a script uses, (3) manage `.bak` backups. These are programmatic operations that benefit from tests. The skill's SKILL.md instructs the LLM to call these functions. Engine detection (`detect_source_engine`) already lives in `ingest.py` (PRD 1) — `source_resolver.py` imports and reuses it rather than duplicating.

---

## Chunk 1: Source Resolution Module

### Task 1: `resolve_source()` — Look Up Script Path by Deck Name

**Files:**
- Create: `aippt/source_resolver.py`
- Create: `tests/test_source_resolver.py`

- [ ] **Step 1: Write failing tests for `resolve_source()`**

Create `.worktrees/edit-deck/tests/test_source_resolver.py`:

```python
"""Tests for aippt.source_resolver — deck name to source script resolution."""

import os
import pytest
from pathlib import Path
from pptx import Presentation

from aippt.catalog import catalog_deck, get_db, resolve_deck
from aippt.source_resolver import resolve_source


class TestResolveSource:
    @pytest.fixture
    def tracked_deck(self, tmp_path):
        """Create a cataloged deck with source tracking metadata.

        Requires PRD 1 merged: catalog_deck() source kwargs + resolve_deck()
        SELECT lists including source columns.
        """
        db_path = str(tmp_path / "test.db")
        pptx_path = str(tmp_path / "test.pptx")
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(pptx_path)
        deck_id = catalog_deck(
            pptx_path, db_path=db_path,
            source_script_path="output/test.mjs",
            source_engine="pptxgenjs",
            source_theme="amd",
        )
        assert deck_id is not None, "catalog_deck returned None"
        # Verify PRD 1 SELECT lists include source columns
        deck = resolve_deck(str(deck_id), db_path=db_path)
        assert "source_script_path" in deck, (
            "resolve_deck() missing source columns — PRD 1 Task 8 not merged"
        )
        return db_path, deck_id

    @pytest.fixture
    def untracked_deck(self, tmp_path):
        """Create a cataloged deck WITHOUT source tracking."""
        db_path = str(tmp_path / "test.db")
        pptx_path = str(tmp_path / "nosource.pptx")
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(pptx_path)
        deck_id = catalog_deck(pptx_path, db_path=db_path)
        return db_path, deck_id

    def test_resolve_by_script_path(self, tmp_path):
        """Direct script path should be returned as-is with engine detected."""
        script_path = str(tmp_path / "deck.mjs")
        Path(script_path).write_text(
            "import { createDeck } from '../lib/pptxgenjs-helpers.mjs';\n"
        )
        result = resolve_source(script_path)
        assert result["script_path"] == script_path
        assert result["engine"] == "pptxgenjs"
        assert result["resolved_from"] == "path"

    def test_resolve_by_deck_id(self, tracked_deck):
        db_path, deck_id = tracked_deck
        result = resolve_source(str(deck_id), db_path=db_path)
        assert result["script_path"] == "output/test.mjs"
        assert result["engine"] == "pptxgenjs"
        assert result["resolved_from"] == "catalog"

    def test_resolve_by_deck_name(self, tracked_deck):
        db_path, _ = tracked_deck
        result = resolve_source("test", db_path=db_path)
        assert result["script_path"] == "output/test.mjs"
        assert result["resolved_from"] == "catalog"

    def test_resolve_untracked_deck_returns_error(self, untracked_deck):
        db_path, deck_id = untracked_deck
        result = resolve_source(str(deck_id), db_path=db_path)
        assert result["error"] is not None
        assert "No source script" in result["error"]

    def test_resolve_no_match_returns_error(self, tracked_deck):
        db_path, _ = tracked_deck
        result = resolve_source("nonexistent", db_path=db_path)
        assert result["error"] is not None
        assert "No deck found" in result["error"]

    def test_resolve_ambiguous_returns_choices(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        for name in ("security-review", "security-audit"):
            pptx_path = str(tmp_path / f"{name}.pptx")
            prs = Presentation()
            prs.slides.add_slide(prs.slide_layouts[6])
            prs.save(pptx_path)
            catalog_deck(
                pptx_path, db_path=db_path,
                source_script_path=f"output/{name}.mjs",
                source_engine="pptxgenjs",
            )
        result = resolve_source("security", db_path=db_path)
        assert result["error"] is not None
        assert "Multiple decks" in result["error"]
        assert len(result["choices"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../venv/bin/python -m pytest tests/test_source_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aippt.source_resolver'`

- [ ] **Step 3: Implement `resolve_source()`**

Create `.worktrees/edit-deck/aippt/source_resolver.py`:

```python
"""Resolve deck identifiers to source script paths for the /edit-deck skill.

Handles three resolution strategies:
1. Direct file path — if the identifier is an existing file, use it directly
2. Catalog ID — if integer, look up deck by ID
3. Catalog name — partial name match
"""

import os
import logging
from pathlib import Path
from typing import Optional

from aippt.catalog import resolve_deck, display_name

logger = logging.getLogger(__name__)


def _detect_engine(script_path: str) -> Optional[str]:
    """Detect engine from script content. Reuses ingest detection if available."""
    try:
        from aippt.ingest import detect_source_engine
        return detect_source_engine(script_path)
    except ImportError:
        # Fallback: basic extension-based detection
        ext = Path(script_path).suffix.lower()
        if ext in (".js", ".mjs"):
            return "pptxgenjs"
        elif ext == ".py":
            return "python-pptx"
        return None


def resolve_source(
    identifier: str,
    db_path: str = "slides.db",
) -> dict:
    """Resolve a deck identifier to its source script path.

    Args:
        identifier: Script file path, deck ID (integer string), or deck name substring
        db_path: Path to the SQLite database

    Returns:
        dict with keys:
        - script_path: str (path to the source script)
        - engine: str or None ('pptxgenjs' or 'python-pptx')
        - theme: str or None
        - deck_name: str or None (display name if resolved from catalog)
        - resolved_from: 'path' or 'catalog'
        - error: str or None (set if resolution failed)
        - choices: list of dicts (set if multiple matches found)
    """
    result = {
        "script_path": None,
        "engine": None,
        "theme": None,
        "deck_name": None,
        "resolved_from": None,
        "error": None,
        "choices": [],
    }

    # Strategy 1: Direct file path
    if os.path.isfile(identifier):
        result["script_path"] = identifier
        result["engine"] = _detect_engine(identifier)
        result["resolved_from"] = "path"
        return result

    # Strategy 2 & 3: Catalog lookup (by ID or name)
    deck = resolve_deck(identifier, db_path=db_path)

    if deck is None:
        result["error"] = f"No deck found matching '{identifier}'"
        return result

    if isinstance(deck, list):
        result["error"] = f"Multiple decks match '{identifier}'"
        result["choices"] = [
            {"id": d["id"], "name": display_name(d["name"])}
            for d in deck
        ]
        return result

    # Single match — extract source info
    script_path = deck.get("source_script_path")
    if not script_path:
        deck_name = display_name(deck["name"])
        result["error"] = (
            f"No source script tracked for '{deck_name}'. "
            "Provide a direct script path instead, or re-ingest with --source."
        )
        return result

    result["script_path"] = script_path
    result["engine"] = deck.get("source_engine")
    result["theme"] = deck.get("source_theme")
    result["deck_name"] = display_name(deck["name"])
    result["resolved_from"] = "catalog"
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../venv/bin/python -m pytest tests/test_source_resolver.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add aippt/source_resolver.py tests/test_source_resolver.py
git commit -m "feat(source_resolver): resolve deck names to source script paths"
```

### Task 2: Backup Management

**Files:**
- Modify: `aippt/source_resolver.py`
- Modify: `tests/test_source_resolver.py`

- [ ] **Step 1: Write failing tests for backup functions**

Append to `tests/test_source_resolver.py`:

```python
from aippt.source_resolver import create_backup, restore_backup, has_backup


class TestBackupManagement:
    def test_create_backup(self, tmp_path):
        script = tmp_path / "deck.mjs"
        script.write_text("original content")
        bak_path = create_backup(str(script))
        assert bak_path == str(script) + ".bak"
        assert Path(bak_path).read_text() == "original content"

    def test_create_backup_skips_if_exists(self, tmp_path):
        script = tmp_path / "deck.mjs"
        script.write_text("v1")
        bak = tmp_path / "deck.mjs.bak"
        bak.write_text("original backup")
        result = create_backup(str(script))
        assert result is None  # skipped
        assert bak.read_text() == "original backup"  # not overwritten

    def test_has_backup(self, tmp_path):
        script = tmp_path / "deck.mjs"
        script.write_text("content")
        assert has_backup(str(script)) is False
        (tmp_path / "deck.mjs.bak").write_text("backup")
        assert has_backup(str(script)) is True

    def test_restore_backup(self, tmp_path):
        script = tmp_path / "deck.mjs"
        bak = tmp_path / "deck.mjs.bak"
        script.write_text("modified content")
        bak.write_text("original content")
        restored = restore_backup(str(script))
        assert restored is True
        assert script.read_text() == "original content"
        assert bak.exists()  # backup is preserved, not deleted

    def test_restore_backup_no_bak(self, tmp_path):
        script = tmp_path / "deck.mjs"
        script.write_text("content")
        restored = restore_backup(str(script))
        assert restored is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../venv/bin/python -m pytest tests/test_source_resolver.py::TestBackupManagement -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement backup functions**

Add to `aippt/source_resolver.py`:

```python
import shutil


def create_backup(script_path: str) -> Optional[str]:
    """Create a .bak backup of the script if one doesn't already exist.

    Returns the backup path if created, None if skipped (already exists).
    """
    bak_path = script_path + ".bak"
    if os.path.exists(bak_path):
        logger.info("Backup already exists at %s, skipping", bak_path)
        return None
    shutil.copy2(script_path, bak_path)
    logger.info("Created backup: %s", bak_path)
    return bak_path


def has_backup(script_path: str) -> bool:
    """Check if a .bak backup exists for this script."""
    return os.path.exists(script_path + ".bak")


def restore_backup(script_path: str) -> bool:
    """Restore the script from its .bak backup.

    Returns True if restored, False if no backup found.
    The .bak file is preserved (not deleted) so the user
    can restore again if needed.
    """
    bak_path = script_path + ".bak"
    if not os.path.exists(bak_path):
        return False
    shutil.copy2(bak_path, script_path)
    logger.info("Restored %s from backup", script_path)
    return True
```

- [ ] **Step 4: Run all source_resolver tests**

Run: `../../venv/bin/python -m pytest tests/test_source_resolver.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add aippt/source_resolver.py tests/test_source_resolver.py
git commit -m "feat(source_resolver): add backup create/restore/check functions"
```

### Task 3: Script Execution Helper

**Files:**
- Modify: `aippt/source_resolver.py`
- Modify: `tests/test_source_resolver.py`

- [ ] **Step 1: Write failing tests for `run_script()`**

Append to `tests/test_source_resolver.py`:

```python
import shutil
import subprocess
from aippt.source_resolver import run_script

node_installed = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node.js not installed",
)


class TestRunScript:
    @node_installed
    def test_run_node_script(self, tmp_path):
        script = tmp_path / "hello.mjs"
        script.write_text("console.log('hello from node');")
        result = run_script(str(script), engine="pptxgenjs")
        assert result["success"] is True
        assert "hello from node" in result["stdout"]

    def test_run_python_script(self, tmp_path):
        script = tmp_path / "hello.py"
        script.write_text("print('hello from python')")
        result = run_script(str(script), engine="python-pptx")
        assert result["success"] is True
        assert "hello from python" in result["stdout"]

    @node_installed
    def test_run_failing_script(self, tmp_path):
        script = tmp_path / "bad.mjs"
        script.write_text("throw new Error('intentional failure');")
        result = run_script(str(script), engine="pptxgenjs")
        assert result["success"] is False
        assert "intentional failure" in result["stderr"]

    def test_run_detects_file_lock_error(self, tmp_path):
        """Simulate a file-in-use error message."""
        script = tmp_path / "lock.py"
        # Script that prints a permission error message to stderr
        script.write_text(
            "import sys; sys.stderr.write('PermissionError: [Errno 13]'); sys.exit(1)"
        )
        result = run_script(str(script), engine="python-pptx")
        assert result["success"] is False
        assert result["file_locked"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `../../venv/bin/python -m pytest tests/test_source_resolver.py::TestRunScript -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement `run_script()`**

Add to `aippt/source_resolver.py`:

```python
import subprocess
import sys


def run_script(script_path: str, engine: str, timeout: int = 120) -> dict:
    """Execute a deck generation script and return the result.

    Args:
        script_path: Path to the JS or Python script
        engine: 'pptxgenjs' or 'python-pptx'
        timeout: Max execution time in seconds

    Returns:
        dict with keys:
        - success: bool
        - stdout: str
        - stderr: str
        - file_locked: bool (True if failure looks like a file-in-use error)
    """
    if engine == "pptxgenjs":
        cmd = ["node", script_path]
    else:
        cmd = [sys.executable, script_path]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(os.path.abspath(script_path)) or ".",
        )
        stderr = proc.stderr or ""
        file_locked = any(
            marker in stderr
            for marker in ("PermissionError", "EBUSY", "being used by another process")
        )
        return {
            "success": proc.returncode == 0,
            "stdout": proc.stdout or "",
            "stderr": stderr,
            "file_locked": file_locked and proc.returncode != 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Script timed out after {timeout} seconds",
            "file_locked": False,
        }
    except FileNotFoundError as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "file_locked": False,
        }
```

- [ ] **Step 4: Run all source_resolver tests**

Run: `../../venv/bin/python -m pytest tests/test_source_resolver.py -v`
Expected: All 14 tests PASS (node tests may skip if node is not installed — see skip decorators)

- [ ] **Step 5: Commit**

```bash
git add aippt/source_resolver.py tests/test_source_resolver.py
git commit -m "feat(source_resolver): add script execution with file lock detection"
```

---

## Chunk 2: Skill File — SKILL.md

### Task 4: Create the Edit-Deck SKILL.md

**Files:**
- Create: `.claude/skills/edit-deck/SKILL.md`

This is the core skill file. It follows the same structure as create-deck and create-outline. Since this is a prompt file (not executable code), there are no automated tests — verification is by manual review and diff inspection.

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p .claude/skills/edit-deck/references
```

- [ ] **Step 2: Write SKILL.md**

Create `.claude/skills/edit-deck/SKILL.md` with the following content. This is the complete skill — the LLM reads this file when `/edit-deck` is invoked.

```markdown
---
name: edit-deck
description: >
  Conversational editing of deck source code. Modifies the generating JS/Python
  script and regenerates the PPTX. Use when the user wants to edit slides by
  changing source code: fix layout issues, rewrite content, add/remove slides,
  change styling, add speaker notes, reorder sections. Accepts a script path
  directly or looks up source_script_path from the catalog by deck name.
  Trigger on: "/edit-deck", "edit the deck", "fix slide N", "change the layout",
  "update the slides", "modify the deck script", "edit output/deck.mjs".
---

# Edit Deck

Edit slides by modifying their generating code, then regenerating the PPTX. This is the third skill in the slides-as-code loop: `/create-deck` → `/deck-review` → `/edit-deck`.

## Quick Reference

| Task | Section |
|------|---------|
| Find the source script | [Step 1: Resolve Source](#step-1-resolve-source) |
| Understand the current state | [Step 2: Read Context](#step-2-read-context) |
| Make the edit | [Steps 3-5: Edit, Diff, Apply](#step-3-llm-edit) |
| Regenerate the deck | [Step 6: Regenerate](#step-6-regenerate) |
| Track the change | [Step 7: Update Metadata](#step-7-update-metadata) |
| Common edit patterns | @references/edit-patterns.md |
| Error recovery | @references/error-recovery.md |
| Example edits | @references/edit-examples.md |

## Environment Setup

```bash
# Detect platform and venv
if [ -f venv/bin/python ]; then
    VENV_PYTHON=venv/bin/python
elif [ -f venv/Scripts/python.exe ]; then
    VENV_PYTHON=venv/Scripts/python.exe
fi
```

## Invocation

Parse `$ARGUMENTS` for two parts: **target** and **edit request**.

```
/edit-deck output/deck.mjs — make slide 3 a numbered list
/edit-deck "Q1 Security Review" — add a summary slide at the end
/edit-deck output/deck.mjs — add speaker notes to every slide
/edit-deck output/deck.mjs — move compliance section before security
```

**Parsing rules:**
- If `$ARGUMENTS` contains ` — ` (space-emdash-space) or ` - ` (space-hyphen-space), split on the first occurrence: left = target, right = edit request
- If no separator, treat the entire argument as the target and ask for the edit request interactively
- If no arguments at all, ask for both target and edit request

## Workflow

### Step 1: Resolve Source

Use the `source_resolver` module to find the script:

```python
from aippt.source_resolver import resolve_source

result = resolve_source(target, db_path="slides.db")
```

**Handle each case:**

| Result | Action |
|--------|--------|
| `result["script_path"]` is set | Proceed to Step 2 |
| `result["error"]` with `"Multiple decks"` | Show `result["choices"]` and ask user to pick one (by ID) |
| `result["error"]` with `"No deck found"` | Ask user: "No deck found matching '{target}'. Provide a direct script path?" |
| `result["error"]` with `"No source script"` | Tell user: "This deck doesn't have source tracking. Provide the script path directly, or re-ingest with `--source`." |

### Step 2: Read Context

Read the source script file. This is the primary context for the edit.

**Always read:**
- The source script (the code being edited)

**Optionally read (based on the edit request):**
- **PPTX content** via `python -m markitdown <path>.pptx` — when the user references current slide content or when you need to see the rendered state
- **Slide images** via `scripts/thumbnail.py <path>.pptx` — when the edit is about visual issues (text overflow, alignment, spacing)
- **Theme YAML** at `themes/<name>.yaml` — when the edit involves colors, fonts, or styling
- **Original outline** (if `outline_path` is set in catalog) — when the edit is about content accuracy or intent

### Step 3: Plan the Edit

Identify what needs to change — do NOT modify the file yet:

1. Find the target slide(s) using the `// ═══ Slide N: Title ═══` markers
2. Determine the specific code changes needed
3. For pptxgenjs: follow the patterns in @references/edit-patterns.md
4. For python-pptx: follow standard python-pptx API patterns

**Important:** Only modify the relevant slide blocks. This keeps diffs clean and preserves the user's existing customizations.

### Step 4: Preview and Confirm

Describe the planned changes to the user: which slides will be touched, what will change in each.

Ask: "These changes look right? Apply and regenerate?"

### Step 5: Backup, Apply, and Diff

**First:** Create a backup before writing any changes:

```python
from aippt.source_resolver import create_backup
create_backup(script_path)
```

The backup is created only once (first edit in a session). If a `.bak` already exists, it's preserved — it represents the pre-edit baseline.

**Then:** Apply the edits using the Edit or Write tool.

**Finally:** Show what changed:

```bash
git diff <script-path>
```

Or if the file isn't tracked, summarize what was modified.

### Step 6: Regenerate

Run the script to produce the updated PPTX:

```python
from aippt.source_resolver import run_script
result = run_script(script_path, engine=engine)
```

**If successful:** Proceed to Step 7.

**If failed:** See @references/error-recovery.md for the full error handling flow:
1. Show the error output
2. Offer to restore from `.bak` backup
3. Offer to attempt an LLM fix of the syntax error
4. If file lock detected: ask user to close PowerPoint and retry

### Step 7: Update Metadata

After a successful edit + regeneration, update the speaker notes metadata:

```python
from pptx import Presentation
from aippt.notes_meta import parse_notes_meta, serialize_notes_meta, append_history

prs = Presentation(pptx_path)
for slide in prs.slides:
    if slide.has_notes_slide:
        notes_text = slide.notes_slide.notes_text_frame.text
        text, meta = parse_notes_meta(notes_text)
        if meta:
            append_history(meta, "<description of change>", "/edit-deck")
            slide.notes_slide.notes_text_frame.text = serialize_notes_meta(text, meta)
prs.save(pptx_path)
```

**Only update metadata for slides that were actually edited** — don't touch unchanged slides.

The change description should be concise and descriptive: "Changed to two_column layout", "Added speaker notes", "Rewrote bullets for exec audience", "Fixed text overflow".

### Step 8: Continue or Hand Off

After a successful edit, offer the user options:

```
Edit applied and deck regenerated: output/{name}.pptx

Options:
- Make another edit (describe what to change)
- /deck-review — Visual QA to verify the changes
- Done — commit the script + PPTX together
```

If the user provides another edit request, loop back to Step 3 (same script, same session). The `.bak` backup from the first edit is preserved across the session.

## Capabilities

### Single-Slide Edits
- Change layout type (bullet → two_column, etc.)
- Rewrite content / bullets
- Add/edit speaker notes
- Add/swap images
- Adjust styling (colors, fonts, spacing)
- Fix visual issues flagged by /deck-review

### Deck-Level Edits
- Add / remove / duplicate slides
- Reorder slides or sections
- Change theme or global styling
- Add section dividers
- Batch operations ("add notes to all slides")
- Insert new slides between existing ones

### Identifying Slides

Use the `// ═══ Slide N: Title ═══` comment markers to find slides in the script. Examples:

```
"slide 4" → find // ═══ Slide 4:
"the architecture slide" → find // ═══ Slide N: Architecture
"all slides" → iterate through all marker blocks
```

## Safety

- **Backup:** `.bak` created before first edit, preserved until user deletes it
- **Diff preview:** Always show changes before applying
- **Git-friendly:** Edited scripts produce clean diffs
- **File locks:** Detect PowerPoint file locks and prompt to close
- **Minimal edits:** Only modify the slide blocks that need changing

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| "No source script tracked" | Deck was ingested without `--source` | Re-ingest: `aippt ingest deck.pptx --source output/deck.mjs` |
| Script fails after edit | Syntax error introduced | Offer restore from `.bak` or LLM fix attempt |
| PPTX won't overwrite | File open in PowerPoint | Close PowerPoint, then retry |
| Wrong deck resolved | Ambiguous name match | Use deck ID instead of name |
| Script path in catalog but file missing | File was moved or deleted | See @references/error-recovery.md — offer to search output/ |
| Metadata not updating | No `---aippt-meta---` block in notes | Only present in decks created after PRD 1; older decks skip metadata |
| Node not found | Node.js not installed | Install Node.js or use python-pptx engine |
```

- [ ] **Step 3: Verify the skill file reads correctly**

Run: `wc -l .claude/skills/edit-deck/SKILL.md`
Expected: ~200-250 lines

- [ ] **Step 4: Commit**

```bash
git add -f .claude/skills/edit-deck/SKILL.md
git commit -m "feat(edit-deck): create /edit-deck skill with 8-step workflow"
```

### Task 5: Edit Patterns Reference

**Files:**
- Create: `.claude/skills/edit-deck/references/edit-patterns.md`

- [ ] **Step 1: Write the edit patterns reference**

Create `.claude/skills/edit-deck/references/edit-patterns.md`:

```markdown
# Edit Patterns for /edit-deck

Reference for common script editing patterns. The edit-deck skill modifies generating code (JS or Python), not the PPTX directly.

## Finding Slides

Scripts use comment markers to delimit slides:

```javascript
// ═══ Slide 1: Title Slide ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
// ... slide content ...

// ═══ Slide 2: Architecture Overview ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
```

Python equivalent:
```python
# ═══ Slide 1: Title Slide ═══
slide = prs.slides.add_slide(blank_layout)
```

**To edit slide N:** Find `// ═══ Slide N:` and modify everything up to the next marker.

## Single-Slide Edit Patterns (pptxgenjs)

### Change Layout Type

**Bullet → Two-Column:**
Replace the single text block with two side-by-side blocks. Split content at a logical midpoint.

### Add Speaker Notes

```javascript
slide.addNotes(`Key talking points:
- First point
- Second point

---aippt-meta---
source: outline → pptxgenjs
created: 2026-03-11
history:
  - "2026-03-11: Created from outline (bullet layout)"
  - "2026-03-13: Added speaker notes [/edit-deck]"
layout: bullet
theme: amd
---end-aippt-meta---`);
```

### Change Text Content

Edit the text strings in `addText()` calls. Preserve formatting objects (`{ fontSize, fontFace, color }`) unless the user specifically asks to change styling.

### Add/Swap Images

```javascript
slide.addImage({ path: 'images/new-diagram.png', x: 1.0, y: 1.5, w: 5, h: 3.5 });
```

## Deck-Level Edit Patterns

### Add a New Slide

Insert a new slide marker and block between existing ones. Update all subsequent slide numbers in the markers:

```javascript
// ═══ Slide 4: New Slide Title ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
// ... new slide content ...

// ═══ Slide 5: Previously Slide 4 ═══  ← renumbered
```

### Remove a Slide

Delete the entire block from marker to next marker. Renumber subsequent slides.

### Reorder Slides

Move the entire code block (marker to next marker) to the new position. Renumber all markers.

### Batch Operations

For "add notes to all slides" or "change font on all slides": iterate through each slide block and apply the change consistently. Use search-and-replace when the pattern is uniform.

## Diff Hygiene

- Only modify the slide blocks you need to change
- Don't reformat or restructure code you're not editing
- Keep the same indentation style as the original
- Preserve helper function definitions at the top of the file
- If adding imports, add them at the top with existing imports
```

- [ ] **Step 2: Commit**

```bash
git add -f .claude/skills/edit-deck/references/edit-patterns.md
git commit -m "docs(edit-deck): add edit patterns reference"
```

### Task 6: Error Recovery Reference

**Files:**
- Create: `.claude/skills/edit-deck/references/error-recovery.md`

- [ ] **Step 1: Write the error recovery reference**

Create `.claude/skills/edit-deck/references/error-recovery.md`:

```markdown
# Error Recovery for /edit-deck

## Script Execution Failure

When `run_script()` returns `success: False`:

### 1. Show the Error

```
Regeneration failed:
{stderr content}
```

### 2. Offer Recovery Options

```
The edited script failed to run. Options:
1. Restore from backup (.bak) and undo the edit
2. Let me try to fix the error
3. Show the full error output
```

### 3. Restore from Backup

```python
from aippt.source_resolver import restore_backup
restore_backup(script_path)
```

After restoring, the script is back to its pre-edit state. The `.bak` file is preserved so the user can restore again if a subsequent fix attempt also fails.

### 4. LLM Fix Attempt

Read the error output and the script. Common issues:
- **Syntax error:** Missing bracket, quote, or semicolon. Fix the specific line.
- **Undefined variable:** Typo in variable name or missing import.
- **Module not found:** Missing `require()` or `import`.

After fixing, run the script again. If it still fails, offer restore.

## File Lock Detection

When `run_script()` returns `file_locked: True`:

```
The PPTX file appears to be open in another application (likely PowerPoint).
Please close the file and try again.
```

Wait for user confirmation, then retry `run_script()`.

**Detection markers in stderr:**
- `PermissionError` (Python/Windows)
- `EBUSY` (Node/Linux)
- `being used by another process` (Windows)

## Missing Source Script

When `resolve_source()` returns an error:

| Error | User Message |
|-------|-------------|
| "No deck found" | "I couldn't find a deck matching '{name}'. Try a more specific name or provide the script path directly." |
| "Multiple decks" | Show the choices list and ask user to pick by ID |
| "No source script tracked" | "This deck doesn't have source tracking. You can: (1) provide the script path directly, (2) re-ingest with `aippt ingest deck.pptx --source output/deck.mjs`" |

## Script Not Found on Disk

If `resolve_source()` returns a `script_path` from the catalog but the file doesn't exist:

```
The catalog says the source script is at '{script_path}', but the file
doesn't exist. It may have been moved or deleted.

Options:
1. Provide the current script path
2. Search for .mjs/.py files in output/
```
```

- [ ] **Step 2: Commit**

```bash
git add -f .claude/skills/edit-deck/references/error-recovery.md
git commit -m "docs(edit-deck): add error recovery reference"
```

### Task 7: Edit Examples Reference

**Files:**
- Create: `.claude/skills/edit-deck/references/edit-examples.md`

- [ ] **Step 1: Write concrete before/after examples**

Create `.claude/skills/edit-deck/references/edit-examples.md`:

```markdown
# Edit Examples for /edit-deck

Concrete before/after examples for common edit requests.

## Example 1: Change Layout from Bullet to Two-Column

**User request:** "Make slide 3 a two-column layout"

**Before:**
```javascript
// ═══ Slide 3: Benefits Overview ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
slide.background = { fill: '000000' };
slide.addText('Benefits Overview', { x: 0.5, y: 0.3, w: 12, h: 0.8, fontSize: 28, color: 'FFFFFF', bold: true });
slide.addText([
  { text: 'Performance', options: { fontSize: 20, color: 'FFFFFF', bold: true, bullet: true } },
  { text: '  2x faster processing', options: { fontSize: 18, color: 'CCCCCC', bullet: true } },
  { text: 'Reliability', options: { fontSize: 20, color: 'FFFFFF', bold: true, bullet: true } },
  { text: '  99.9% uptime SLA', options: { fontSize: 18, color: 'CCCCCC', bullet: true } },
  { text: 'Security', options: { fontSize: 20, color: 'FFFFFF', bold: true, bullet: true } },
  { text: '  SOC 2 Type II certified', options: { fontSize: 18, color: 'CCCCCC', bullet: true } },
], { x: 0.5, y: 1.5, w: 12, h: 5, valign: 'top' });
```

**After:**
```javascript
// ═══ Slide 3: Benefits Overview ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
slide.background = { fill: '000000' };
slide.addText('Benefits Overview', { x: 0.5, y: 0.3, w: 12, h: 0.8, fontSize: 28, color: 'FFFFFF', bold: true });
// Divider line
slide.addShape(pptx.ShapeType.line, { x: 6.5, y: 1.5, w: 0, h: 4.5, line: { color: '636466', width: 1 } });
// Left column
slide.addText([
  { text: 'Performance', options: { fontSize: 20, color: '00C2DE', bold: true, bullet: true } },
  { text: '  2x faster processing', options: { fontSize: 18, color: 'CCCCCC', bullet: true } },
], { x: 0.5, y: 1.5, w: 5.5, h: 4.5, valign: 'top' });
// Right column
slide.addText([
  { text: 'Reliability', options: { fontSize: 20, color: '00C2DE', bold: true, bullet: true } },
  { text: '  99.9% uptime SLA', options: { fontSize: 18, color: 'CCCCCC', bullet: true } },
  { text: 'Security', options: { fontSize: 20, color: '00C2DE', bold: true, bullet: true } },
  { text: '  SOC 2 Type II certified', options: { fontSize: 18, color: 'CCCCCC', bullet: true } },
], { x: 7.0, y: 1.5, w: 5.5, h: 4.5, valign: 'top' });
```

## Example 2: Add Speaker Notes to All Slides

**User request:** "Add speaker notes to every slide"

**Pattern:** For each slide block, add an `addNotes()` call based on the slide content. Generate relevant talking points from the bullet text.

**Before** (each slide):
```javascript
// ═══ Slide 2: Architecture ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
// ... slide content, no addNotes() call ...
```

**After:**
```javascript
// ═══ Slide 2: Architecture ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
// ... slide content ...
slide.addNotes('Walk through the three-tier architecture. Emphasize the event bus as the key integration point. Mention that this pattern scales to 10K concurrent users.');
```

## Example 3: Fix Text Overflow

**User request:** "Slide 5 has text overflow, fix it"

**Diagnosis:** Too many bullets or font too large for the content area.

**Fixes (pick the best):**
1. Reduce font size (e.g., 20 → 18pt for body, 24 → 20pt for headers)
2. Trim verbose bullets to shorter phrases
3. Split into two slides if content is genuinely too dense
4. Increase the text area height (reduce top/bottom margins)

## Example 4: Insert a New Slide

**User request:** "Add a summary slide after slide 6"

**Pattern:** Insert a new slide block after slide 6's marker. Renumber all subsequent slides.

```javascript
// ═══ Slide 7: Summary ═══  ← NEW
slide = pptx.addSlide({ masterName: 'BLANK' });
slide.background = { fill: '000000' };
slide.addText('Summary', { x: 0.5, y: 0.3, w: 12, h: 0.8, fontSize: 28, color: 'FFFFFF', bold: true });
slide.addText([
  { text: 'Key takeaways from this section...', options: { fontSize: 20, color: 'CCCCCC' } },
], { x: 0.5, y: 1.5, w: 12, h: 5, valign: 'top' });

// ═══ Slide 8: Next Steps ═══  ← was Slide 7
```

## Example 5: Reorder Sections

**User request:** "Move the compliance section before security"

**Pattern:** Identify all slides belonging to each section (by scanning markers and content). Cut the compliance block and paste it before the security block. Renumber all markers.
```

- [ ] **Step 2: Commit**

```bash
git add -f .claude/skills/edit-deck/references/edit-examples.md
git commit -m "docs(edit-deck): add concrete edit examples reference"
```

---

## Chunk 3: Integration & Verification

### Task 8: Register the Skill and Verify Discovery

The skill is discovered automatically by Claude Code from the `.claude/skills/` directory — no explicit registration is needed. But we should verify the files are properly tracked and the skill appears in the skill list.

**Files:**
- Verify: `.claude/skills/edit-deck/SKILL.md`
- Verify: `.claude/skills/edit-deck/references/*.md`

- [ ] **Step 1: Verify all skill files are git-tracked**

```bash
git ls-files .claude/skills/edit-deck/
```

Expected output:
```
.claude/skills/edit-deck/SKILL.md
.claude/skills/edit-deck/references/edit-examples.md
.claude/skills/edit-deck/references/edit-patterns.md
.claude/skills/edit-deck/references/error-recovery.md
```

- [ ] **Step 2: Verify skill frontmatter is valid YAML**

```bash
head -5 .claude/skills/edit-deck/SKILL.md
```

Expected: Should show `---`, `name: edit-deck`, `description:`, then `---`.

- [ ] **Step 3: Run full test suite**

Run: `../../venv/bin/python -m pytest tests/ -v --timeout=30`
Expected: All existing tests PASS, plus 14 new tests from `test_source_resolver.py` (node tests may skip)

- [ ] **Step 4: Check for uncommitted changes**

```bash
git status
```

Expected: Clean working directory. If any unstaged changes remain, stage them by specific filename and commit.

### Task 9: Update CLAUDE.md Skills Section

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the Skills / Slash Commands section**

In `CLAUDE.md`, find the "## Skills / Slash Commands" section and add `/edit-deck`:

```markdown
## Skills / Slash Commands

- `/create-outline` — Generate a presentation outline from source material (docs, code, repos, URLs)
- `/create-deck` — Generate a PowerPoint deck from a markdown outline (pptxgenjs or python-pptx)
- `/deck-review` — Visual QA and full lifecycle review of generated decks
- `/edit-deck` — Conversational editing of deck source code (modify script, regenerate PPTX)
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add /edit-deck to CLAUDE.md skills section"
```

### Task 10: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `../../venv/bin/python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 2: Verify file count and structure**

```bash
find .claude/skills/edit-deck -type f | sort
```

Expected:
```
.claude/skills/edit-deck/SKILL.md
.claude/skills/edit-deck/references/edit-examples.md
.claude/skills/edit-deck/references/edit-patterns.md
.claude/skills/edit-deck/references/error-recovery.md
```

```bash
wc -l aippt/source_resolver.py tests/test_source_resolver.py
```

Expected: ~150 lines source, ~130 lines tests

- [ ] **Step 3: Review git log**

```bash
git log --oneline
```

Expected: Clean commit history on `feature/edit-deck-skill` branch with descriptive messages.

- [ ] **Step 4: Verify no regressions in existing tests**

```bash
../../venv/bin/python -m pytest tests/test_catalog.py tests/test_decks_cli.py tests/test_cli.py -v
```

Expected: All PASS — no existing test touched or broken.
