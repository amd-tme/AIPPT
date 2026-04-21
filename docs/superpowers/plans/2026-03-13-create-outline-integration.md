# Create-Outline Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the create-outline skill into the slides-as-code loop — pass `outline_path` through create-deck to ingest, update skill handoff messages to reference `/edit-deck`, and fix the heading pattern count in the create-outline spec.

**Architecture:** Minimal wiring changes: create-deck SKILL.md passes the outline path to the ingest command, create-outline and create-deck handoff messages gain `/edit-deck` as a downstream option, and a doc fix corrects "two" → "three" heading patterns. No new modules or schema changes — PRD 1 provides all infrastructure.

**Tech Stack:** Claude Code skill files (markdown), Python 3

**Spec:** `docs/superpowers/specs/2026-03-11-slides-as-code-design.md` — Component 0

**Worktree:** `.worktrees/outline-tracking/` on branch `feature/outline-source-tracking`

**Depends on:** PRD 1 (Foundation) must be merged. Specifically: `outline_path` column in `decks` table, `ingest_deck()` accepting `outline_path` parameter, `--outline` CLI flag on `aippt ingest`.

**Running commands:** All commands assume the agent is working inside the worktree directory (`.worktrees/outline-tracking/`). The venv is at the project root: `../../venv/bin/python`.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `.claude/skills/create-deck/SKILL.md` | Modify | Update Next Steps message: add `/edit-deck`, pass `--outline` and `--source` to ingest |
| `.claude/skills/create-outline/SKILL.md` | Modify | Update Step 9 handoff: add `/edit-deck` as downstream option |
| `docs/superpowers/specs/2026-03-11-create-outline-skill-design.md` | Modify | Fix "Two Heading Patterns" → "Three Heading Patterns" |
| `tests/test_outline_integration.py` | Create | Integration test: outline_path round-trip through ingest → catalog |

**Note on scope:** This PRD does NOT modify `aippt/ingest.py`, `aippt/catalog.py`, or `aippt/schema.sql` — those changes are in PRD 1. This PRD only modifies skill prompt files (SKILL.md) and a spec doc, plus adds a thin integration test that verifies PRD 1's `outline_path` wiring works end-to-end.

---

## Chunk 1: Skill Handoff Updates

### Task 1: Update Create-Deck Handoff Message

**Files:**
- Modify: `.claude/skills/create-deck/SKILL.md` (lines 408-420)

The current "Next Steps Message" section shows:

```
Next steps:
- /deck-review — Visual QA and feedback
- aippt ingest output/{name}.pptx — Catalog with notes and tags
- aippt improve output/{name}.pptx — LLM-powered refinement
```

This needs to: (1) add `/edit-deck`, (2) pass `--source` and `--outline` to the ingest command.

- [ ] **Step 1: Update the Next Steps Message**

In `.worktrees/outline-tracking/.claude/skills/create-deck/SKILL.md`, find the "Next Steps Message" section (around line 408-420). Replace the next steps block with:

```markdown
### Next Steps Message

After generating, show the user:

```
Deck created: output/{name}.pptx ({size})
Script saved: output/{name}.mjs

Next steps:
- /deck-review — Visual QA and feedback
- /edit-deck output/{name}.mjs — Conversational editing of the source script
- aippt ingest output/{name}.pptx --source output/{name}.mjs --outline outlines/{name}.md — Catalog with source tracking
```
```

**Key changes:**
- Added `/edit-deck` as a next step (second position, after deck-review)
- Updated ingest command to include `--source` and `--outline` flags
- Changed `.js` to `.mjs` to match the actual output extension for pptxgenjs

- [ ] **Step 2: Verify the edit reads correctly**

Read the modified section to confirm no markdown formatting issues.

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/create-deck/SKILL.md
git commit -m "feat(create-deck): add /edit-deck and --outline to handoff message"
```

### Task 2: Update Create-Outline Handoff Message

**Files:**
- Modify: `.claude/skills/create-outline/SKILL.md` (lines 240-255)

The current Step 9 "Next steps" block shows:

```
Next steps:
- /create-deck — Generate a polished deck (pptxgenjs or python-pptx)
- aippt create outlines/{name}.md template.pptx output/{name}.pptx --enhance
- Excalidraw — Create diagrams for placeholder slides (see TODO markers)
```

This needs to add `/edit-deck` as a downstream option after `/create-deck`.

- [ ] **Step 1: Update the Step 9 Next Steps block**

In `.worktrees/outline-tracking/.claude/skills/create-outline/SKILL.md`, find Step 9's summary block (around line 248-255). Replace the next steps with:

```
Next steps:
- /create-deck — Generate a polished deck (pptxgenjs or python-pptx)
- /edit-deck — Edit the generated deck's source script (after /create-deck)
- aippt create outlines/{name}.md template.pptx output/{name}.pptx --enhance
- Excalidraw — Create diagrams for placeholder slides (see TODO markers)
```

- [ ] **Step 2: Verify the edit**

Read the modified section to confirm formatting.

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/create-outline/SKILL.md
git commit -m "feat(create-outline): add /edit-deck to Step 9 handoff message"
```

---

## Chunk 2: Doc Fix and Integration Test

### Task 3: Fix Heading Pattern Count in Create-Outline Spec

**Files:**
- Modify: `docs/superpowers/specs/2026-03-11-create-outline-skill-design.md` (lines 253-255)

Line 253 reads: `### Structure — Two Heading Patterns`
Line 255 reads: `**The skill supports two heading patterns.**`

Both should say "Three" — the section describes Pattern A, Pattern B, and Simple mode.

- [ ] **Step 1: Fix the section header**

In `.worktrees/outline-tracking/docs/superpowers/specs/2026-03-11-create-outline-skill-design.md`:

Change line 253 from:
```markdown
### Structure — Two Heading Patterns
```
To:
```markdown
### Structure — Three Heading Patterns
```

- [ ] **Step 2: Fix the introductory sentence**

Change line 255 from:
```markdown
**The skill supports two heading patterns.**
```
To:
```markdown
**The skill supports three heading patterns: Pattern A, Pattern B, and Simple mode.**
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-03-11-create-outline-skill-design.md
git commit -m "docs(create-outline): fix heading pattern count — two → three"
```

### Task 4: Integration Test — Outline Path Round-Trip

**Files:**
- Create: `tests/test_outline_integration.py`

This test verifies that `outline_path` flows correctly through `ingest_deck()` → `catalog_deck()` → `resolve_deck()`. It requires PRD 1 to be merged.

- [ ] **Step 1: Write the integration test**

Create `.worktrees/outline-tracking/tests/test_outline_integration.py`:

```python
"""Integration tests for outline_path tracking through the pipeline.

Requires PRD 1 (Foundation) to be merged — these tests verify that
outline_path flows from ingest → catalog → resolve correctly.
"""

import os
import pytest
from pathlib import Path
from pptx import Presentation

from aippt.catalog import catalog_deck, resolve_deck, get_db


class TestOutlinePathTracking:
    @pytest.fixture
    def pipeline_setup(self, tmp_path):
        """Create a minimal outline, script, and PPTX for testing."""
        db_path = str(tmp_path / "test.db")

        # Create a fake outline
        outline_path = str(tmp_path / "outlines" / "test-outline.md")
        os.makedirs(os.path.dirname(outline_path), exist_ok=True)
        Path(outline_path).write_text(
            "---\naudience: engineers\ngoal: demo\ntone: technical\n---\n"
            "# Test Deck\n## Slide 1\n- Bullet one\n"
        )

        # Create a fake script
        script_path = str(tmp_path / "output" / "test-outline.mjs")
        os.makedirs(os.path.dirname(script_path), exist_ok=True)
        Path(script_path).write_text(
            "import { createDeck } from '../lib/pptxgenjs-helpers.mjs';\n"
        )

        # Create a minimal PPTX
        pptx_path = str(tmp_path / "output" / "test-outline.pptx")
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(pptx_path)

        return db_path, pptx_path, script_path, outline_path

    def test_outline_path_stored_in_catalog(self, pipeline_setup):
        """catalog_deck() with outline_path stores it in the database."""
        db_path, pptx_path, script_path, outline_path = pipeline_setup
        deck_id = catalog_deck(
            pptx_path,
            db_path=db_path,
            source_script_path=script_path,
            source_engine="pptxgenjs",
            outline_path=outline_path,
        )
        conn = get_db(db_path)
        row = conn.execute(
            "SELECT outline_path FROM decks WHERE id = ?", (deck_id,)
        ).fetchone()
        conn.close()
        assert row["outline_path"] == outline_path

    def test_outline_path_in_resolve_deck(self, pipeline_setup):
        """resolve_deck() includes outline_path in the returned dict."""
        db_path, pptx_path, script_path, outline_path = pipeline_setup
        deck_id = catalog_deck(
            pptx_path,
            db_path=db_path,
            source_script_path=script_path,
            outline_path=outline_path,
        )
        deck = resolve_deck(str(deck_id), db_path=db_path)
        assert deck is not None
        assert "outline_path" in deck
        assert deck["outline_path"] == outline_path

    def test_outline_path_preserved_on_recatalog(self, pipeline_setup):
        """Re-cataloging without outline_path should preserve the original."""
        db_path, pptx_path, script_path, outline_path = pipeline_setup
        deck_id = catalog_deck(
            pptx_path,
            db_path=db_path,
            source_script_path=script_path,
            outline_path=outline_path,
        )
        # Modify PPTX to trigger re-catalog (different hash)
        prs = Presentation(pptx_path)
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(pptx_path)
        # Re-catalog without outline_path
        deck_id2 = catalog_deck(pptx_path, db_path=db_path)
        assert deck_id == deck_id2
        conn = get_db(db_path)
        row = conn.execute(
            "SELECT outline_path FROM decks WHERE id = ?", (deck_id,)
        ).fetchone()
        conn.close()
        assert row["outline_path"] == outline_path

    def test_ingest_with_outline_path(self, pipeline_setup):
        """ingest_deck() passes outline_path through to catalog."""
        db_path, pptx_path, script_path, outline_path = pipeline_setup
        from aippt.ingest import ingest_deck
        result = ingest_deck(
            pptx_path,
            db_path=db_path,
            source_script_path=script_path,
            outline_path=outline_path,
            require_images=False,
        )
        assert result["source_tracked"] is True
        conn = get_db(db_path)
        row = conn.execute(
            "SELECT outline_path FROM decks WHERE id = ?", (result["deck_id"],)
        ).fetchone()
        conn.close()
        assert row["outline_path"] == outline_path

    def test_no_outline_path_is_null(self, pipeline_setup):
        """Decks ingested without outline_path have NULL in the column."""
        db_path, pptx_path, _, _ = pipeline_setup
        deck_id = catalog_deck(pptx_path, db_path=db_path)
        conn = get_db(db_path)
        row = conn.execute(
            "SELECT outline_path FROM decks WHERE id = ?", (deck_id,)
        ).fetchone()
        conn.close()
        assert row["outline_path"] is None
```

- [ ] **Step 2: Run tests to verify they pass**

These tests depend on PRD 1 being merged. If PRD 1 is not yet merged, they will fail with `TypeError` on the `catalog_deck()` kwargs or missing `outline_path` column.

Run: `../../venv/bin/python -m pytest tests/test_outline_integration.py -v`
Expected: All 5 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_outline_integration.py
git commit -m "test: add outline_path integration tests for pipeline round-trip"
```

### Task 5: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `../../venv/bin/python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 2: Verify skill files are tracked**

```bash
git ls-files .claude/skills/create-deck/SKILL.md .claude/skills/create-outline/SKILL.md
```

Expected: Both files listed.

- [ ] **Step 3: Review git log**

```bash
git log --oneline
```

Expected: 4 commits on `feature/outline-source-tracking`:
1. `feat(create-deck): add /edit-deck and --outline to handoff message`
2. `feat(create-outline): add /edit-deck to Step 9 handoff message`
3. `docs(create-outline): fix heading pattern count — two → three`
4. `test: add outline_path integration tests for pipeline round-trip`

- [ ] **Step 4: Check for uncommitted changes**

```bash
git status
```

Expected: Clean working directory.
