# Slides as Code: Source Tracking & Conversational Editing

**Date:** 2026-03-11
**Status:** Implemented (foundation)
**Branch:** feature/slides-as-code-foundation

## Problem Statement

aippt's create-deck skill generates JS or Python scripts that produce PowerPoint decks. These scripts are the most precise representation of a deck's content and layout — yet they're treated as disposable build artifacts. Once a deck is generated, editing requires either re-running the full create-deck pipeline or manually editing the PPTX.

This creates friction in the most common workflow: generate a deck, review it, fix a few issues, review again. Each fix cycle currently requires either regenerating from scratch (losing tweaks) or leaving the code-generation paradigm entirely.

## Goals

1. **Conversational editing** — Edit slides by modifying their generating code through natural language, then regenerating. ("Make slide 4 a two-column layout", "Add speaker notes to all slides", "Move the compliance section before security.")
2. **Source tracking** — Track the relationship between generated scripts, outlines, themes, and PPTX output so any cataloged deck can be traced back to its source code.
3. **Change history** — Maintain a lightweight edit history per slide via structured metadata in speaker notes.

## Non-Goals

- Code-based analysis (running analysis/tagging on source code instead of images) — deferred
- Reference enrichment (auto-linking slides to documentation/whitepapers) — deferred
- Web UI for conversational editing — deferred (CLI-first; web exposure later)
- Support for non-aippt-generated PPTX (arbitrary corporate decks) — out of scope
- AST-based parsing or structured edit engine — unnecessary; LLM editing of code is sufficient

## Design

### Architecture Overview

The generated JS/Python script becomes the **mutable source of truth** for a deck. The markdown outline is lineage metadata — tracked but not mutated after initial generation. The editing loop feeds back into the script, not the outline.

```
SOURCE MATERIAL
      │
  /create-outline  ← Component 0
      │
      ▼
  MARKDOWN OUTLINE  (outlines/deck-name.md)
      │               + images/{deck-name}/ (captured screenshots)
  /create-deck
      │
      ▼
  GENERATED SCRIPT  (output/deck-name.js or .py)  ★ SOURCE OF TRUTH ★
      │                         ▲
  node/python              /edit-deck
      │                  (LLM edits the script,
      ▼                   appends change history)
  PPTX OUTPUT  (output/deck-name.pptx)
      │
  aippt ingest --source
      │
      ▼
  SQLITE CATALOG  (source metadata tracked)
```

Four skills form the full loop:

1. `/create-outline` — generates a structured outline from source material (docs, code, repos, URLs)
2. `/create-deck` — generates the script and initial PPTX from the outline
3. `/deck-review` — visual QA of the PPTX, identifies issues
4. `/edit-deck` — edits the script to fix issues or make changes, regenerates

### Component 0: Create-Outline Integration

The `/create-outline` skill sits upstream of the code-generation loop. It converts raw source material into a structured markdown outline that `/create-deck` consumes. The skill has its own detailed spec (`docs/superpowers/specs/2026-03-11-create-outline-skill-design.md`); this component describes how it integrates into the slides-as-code pipeline.

**Role in the pipeline:**

1. **Outline as lineage metadata** — When create-outline saves `outlines/{name}.md`, that path becomes `outline_path` in the catalog (Component 1's schema). The outline is lineage — tracked but not mutated after initial generation. The editing loop feeds back into the generated script, not the outline.

2. **Handoff to create-deck** — Create-outline's finalization step suggests `/create-deck` as the next step. The integration ensures create-deck receives the outline path and passes it through to ingest for catalog storage.

3. **Screenshot assets** — Images captured by create-outline in `images/{name}/` are referenced by `IMAGE:` directives in the outline. Create-deck resolves these paths when generating slides. The images are source material, not generated artifacts — they are not tracked in the catalog separately.

4. **Outline format contract** — The markdown outline is the stable interface between content generation and deck generation. All metadata (audience, goal, tone via frontmatter; layout suggestions via directives; image paths via `IMAGE:` directives) flows through the outline file. Both skills support three heading patterns (Pattern A, B, and Simple), detected automatically by create-deck.

**What Component 0 does NOT change:**
- The create-outline skill workflow — no modifications to the 3-phase process
- The outline format — already well-specified in the skill's reference docs
- Phase 3 screenshot capture — already works independently

**Implementation scope (PRD 3):**
- Create-deck passes `outline_path` to ingest so the catalog entry records which outline generated the deck
- Update create-outline `SKILL.md` Step 9 (Finalize & Handoff) to reference `/edit-deck` in the next-steps message
- Update create-deck `SKILL.md` handoff message to reference `/edit-deck` as a downstream option
- Design spec and architecture diagram updated to show the four-skill loop

**Note:** The create-outline skill spec (`docs/superpowers/specs/2026-03-11-create-outline-skill-design.md`) labels its heading patterns section as "two heading patterns" but describes three (Pattern A, B, and Simple). This inconsistency should be corrected as part of PRD 3.

### Component 1: Source Tracking in the Catalog

**Schema changes** — five new nullable columns on the `decks` table:

| Column | Type | Purpose |
|--------|------|---------|
| `source_script_path` | TEXT | Relative path to the JS/Python script |
| `source_engine` | TEXT | `pptxgenjs` or `python-pptx` |
| `source_theme` | TEXT | Theme name (`amd`, `default`, etc.) |
| `outline_path` | TEXT | Relative path to the originating markdown outline |
| `source_generated_at` | TEXT | ISO timestamp of last script generation/regeneration |

All nullable — existing decks ingested from arbitrary PPTX have NULLs. Only aippt-generated decks populate these fields. The catalog stores *paths*, not copies of the files.

**Ingest changes:**

- `aippt ingest` gains a `--source <script-path>` flag
- When provided, the ingest pipeline stores the source path and auto-detects engine from script content (`require('pptxgenjs')` → pptxgenjs, `from pptx import` → python-pptx)
- Theme is detected from theme YAML references in the script
- The `/create-deck` skill's auto-handoff to ingest passes `--source` automatically

**CLI additions:**

- `aippt decks info <name>` — shows source metadata when available (script path, engine, theme, outline, generated timestamp)
- `aippt decks source <name>` — prints the source script path; with `--cat` flag, prints the script contents. Implementation: add a `"source"` action to the `decks` subparser in `cli.py` and a corresponding branch in `cmd_decks()`

**Migration:** Add the five new columns to the existing `decks` migration tuple list in `catalog.py:get_db()`, following the same pattern as the existing `author`, `created_date`, `modified_date`, `subject`, and `description` entries. Each column is added as an `(ALTER TABLE DDL, column_name)` tuple. The migration checks `PRAGMA table_info` before adding, so it's safe to run on existing databases. Also update `schema.sql` for fresh installs.

**`catalog_deck()` changes:** Add optional keyword arguments for the source fields: `source_script_path=None, source_engine=None, source_theme=None, outline_path=None`. When provided, these are stored during the initial `INSERT`. On re-catalog (same `file_path` detected), the four path/identity fields (`source_script_path`, `source_engine`, `source_theme`, `outline_path`) are preserved unless new values are explicitly passed — this prevents re-ingest from clearing source metadata. The exception is `source_generated_at`, which auto-updates to the current timestamp on every catalog/re-catalog — but only when `source_script_path` is non-NULL (i.e., this is a source-tracked deck). When re-cataloging a deck where `source_script_path` is NULL, `source_generated_at` stays NULL.

**`ingest_deck()` changes:** Add `source_script_path=None` parameter, passed through to `catalog_deck()`. Engine and theme are auto-detected from the script (see detection rules below). The web upload endpoint (`web/routes.py`) does not pass `--source` — web-uploaded decks have NULL source fields. This is intentional; web uploads are typically pre-built PPTX files without source scripts.

**Engine auto-detection rules** (scan first 50 lines of script):
1. Scan for `require('pptxgenjs')` or `require("pptxgenjs")` or `pptxgenjs-helpers.mjs` → `pptxgenjs`
2. Scan for `from pptx import` or `import pptx` → `python-pptx`
3. If neither found → store `NULL` (unknown engine)
4. If both found (shouldn't happen) → use whichever pattern appears first by line number

`source_engine` is always auto-detected and has no CLI override flag. This is a deliberate simplification — a script is definitively one engine or the other based on its imports.

**Theme detection:** Scan for theme YAML path references matching `themes/<name>.yaml` (e.g., `themes/amd.yaml` or `themes/default.yaml`). Extract the stem (`amd`, `default`) as the theme name. If no theme reference found → store `NULL`. The `--theme <name>` flag on `aippt ingest` can override auto-detection.

**Path convention:** `source_script_path` and `outline_path` are stored as relative paths from the project root, following the same convention as `file_path` in the existing `decks` table.

**CLI argparse wiring for ingest:** Add `--source <script-path>` and `--theme <name>` optional arguments to the `ingest` subparser in `cli.py`. `cmd_ingest()` passes these through to `ingest_deck()`. The `--theme` flag is optional and overrides auto-detection when provided.

**`ingest_deck()` return value:** The existing return dict (`{deck_id, deck_name, slide_count, images_dir, images_exported, tags_generated}`) gains `source_tracked: bool` — `True` if source metadata was stored, `False` otherwise. This lets callers (including the create-deck auto-handoff) confirm that source tracking succeeded.

### Component 2: The /edit-deck Skill

A new Claude Code skill at `.claude/skills/edit-deck/` that enables conversational editing of deck source code.

**Invocation patterns:**

```bash
# By script path
/edit-deck output/deck.js — make slide 3 a numbered list

# By deck name (looks up source_script_path in catalog)
/edit-deck "Q1 Security Review" — add a summary slide at the end

# Batch operation
/edit-deck output/deck.js — add speaker notes to every slide

# Deck-level restructuring
/edit-deck output/deck.js — move compliance section before security
```

**Workflow:**

1. **Resolve source** — Accept a script path directly, or look up `source_script_path` from the catalog by deck name
2. **Read context** — Read the script file. Optionally read the PPTX via markitdown for current slide content. Optionally read slide images for visual context (e.g., when fixing visual issues)
3. **LLM edit** — Pass the script + user's request + context to the LLM. The LLM returns a modified script
4. **Diff preview** — Show the user what changed before applying
5. **Apply** — Write the updated script (after backing up the original to `.bak`)
6. **Regenerate** — Run the script (`node` or `python`) to produce the updated PPTX
7. **Update metadata** — Append change history entries to the metadata blocks in speaker notes
8. **Continue or hand off** — Accept more edits in the same session, or suggest `/deck-review` for visual QA

**Capabilities:**

Single-slide edits:
- Change layout type
- Rewrite content / bullets
- Add/edit speaker notes
- Add/swap images
- Adjust styling (colors, fonts, spacing)
- Fix visual issues flagged by /deck-review

Deck-level edits:
- Add / remove / duplicate slides
- Reorder slides or sections
- Change theme or global styling
- Add section dividers
- Batch operations ("add notes to all slides")
- Insert new slides between existing ones

**Context sources available to the LLM:**
- Script file (always — the code being edited)
- PPTX content via markitdown (current rendered state)
- Slide images (when visual context needed for fixing layout issues)
- Theme YAML (color/font definitions)
- Original outline (if available, for understanding intent)

**Safety:**
- Back up script before editing: if no `.bak` file exists for this script, create one as `<script-path>.bak` (e.g., `output/deck.js.bak`). Single backup, no timestamp. If a `.bak` already exists, skip — the earliest pre-edit state is already preserved. The user can delete the `.bak` manually when satisfied with the current state. Note: deleting the `.bak` during an active edit session resets the rollback baseline to the current script state on the next edit, not the original pre-edit state
- Show diff to user before writing changes
- Git-friendly — edited scripts produce clean diffs for version control
- If the user has the PPTX open in PowerPoint (common on Windows/WSL2), regeneration will fail due to file locks. The skill should detect the failure and prompt the user to close the file before retrying

**Error handling:**
- If the regenerated script fails to run (syntax error, missing dependency), the skill should: (1) show the error output, (2) offer to restore from the `.bak` backup, (3) offer to let the LLM attempt to fix the error. The original `.bak` is never deleted until the user explicitly confirms the edit succeeded
- If source lookup by deck name fails (no `source_script_path` in catalog), the skill should suggest providing a direct script path instead

**Skill file location:** The skill lives at `.claude/skills/edit-deck/`. Since `.claude/` is gitignored, use `git add -f` to track the skill files, consistent with existing skills (create-deck, create-outline, deck-review).

### Component 3: Change History via Speaker Notes Metadata

Each slide's speaker notes contain a structured metadata block that tracks editing lineage. This extends the existing `[AIPPT-META]` JSON format in `aippt/metadata.py` rather than introducing a new format.

**Format:**

The existing `metadata.py` module uses `[AIPPT-META]` / `[/AIPPT-META]` delimiters with a JSON list of operation entries. Each entry has `operation`, `timestamp`, and arbitrary kwargs. The slides-as-code pipeline adds new operation types and fields to this existing system:

```
[actual speaker notes content here]

---
[AIPPT-META]
[
  {
    "operation": "create",
    "timestamp": "2026-03-11T10:00:00+00:00",
    "source": "outline → pptxgenjs",
    "layout": "two_column",
    "theme": "amd"
  },
  {
    "operation": "edit",
    "timestamp": "2026-03-11T14:00:00+00:00",
    "description": "Changed to two_column layout",
    "source_skill": "/edit-deck"
  },
  {
    "operation": "edit",
    "timestamp": "2026-03-12T09:00:00+00:00",
    "description": "Rewrote bullets for executive audience",
    "source_skill": "/edit-deck"
  }
]
[/AIPPT-META]
```

**Design decisions:**

- **Extends existing format:** Reuses the `[AIPPT-META]` JSON system already used by `aippt improve` and enhance pipelines. No new delimiters, parsers, or modules needed.
- **Append-only entries:** Each edit adds a new entry to the JSON list. Capped at last 10 entries — the serializer trims oldest entries at write-time. Existing entries from other operations (improve, enhance) are preserved.
- **New operation types:** `"create"` (initial deck generation), `"edit"` (conversational edits via /edit-deck), `"review-fix"` (fixes applied from /deck-review)
- **Position:** Always at the end of speaker notes, after `---` separator. Everything before is real notes content. This is unchanged from the current behavior.
- **Graceful degradation:** If no `[AIPPT-META]` block exists, `extract_metadata()` returns an empty list — no errors. This already works.

**Relationship to `edit_history` table:** The existing `edit_history` table in the database tracks field-level changes for catalog operations (title edits, tag changes, etc.). The speaker notes metadata serves a different purpose: it travels *with* the PPTX file and is readable by the LLM during editing without a database query. The two systems are complementary — `edit_history` tracks catalog-level changes, notes metadata tracks code-generation-level changes. No changes to the existing `edit_history` table are needed.

**What writes metadata:**
- `/create-deck` — initial `"create"` entry (source, layout, theme)
- `/edit-deck` — appends `"edit"` entry describing each change
- `/deck-review` — appends `"review-fix"` entry when fixes are applied
- `aippt improve` — already uses this format via `append_metadata(slide, "improve", ...)`

**What reads metadata:**
- `/edit-deck` — reads entries to understand slide context before editing
- `/deck-review` — can see what's already been attempted/fixed
- `aippt catalog` — could optionally parse and index metadata fields

### Component 4: Changes to /create-deck

Additive changes to the create-deck skill's code generation prompts. No structural changes to the skill workflow.

**Slide markers in generated code:**

Each slide's code block gets a comment header for LLM identification:

```javascript
// ═══ Slide 1: Title Slide ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
// ... slide code ...

// ═══ Slide 2: Architecture Overview ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
// ... slide code ...
```

Python equivalent:

```python
# ═══ Slide 1: Title Slide ═══
slide = prs.slides.add_slide(blank_layout)
# ... slide code ...
```

These are visual markers — not parsed programmatically, just clear enough for an LLM to reliably find "slide 4."

**Metadata in speaker notes:**

Each slide's `addNotes()` call includes an initial `[AIPPT-META]` JSON block with a `"create"` entry containing source, layout, and theme.

**Auto-ingest with source:**

When create-deck's auto-handoff triggers ingest, it passes `--source output/deck.js` automatically so the catalog entry is born with its source lineage.

## Lifecycle: Typical User Journey

1. `/create-outline` from source material → `outlines/q1-security.md`
2. `/create-deck outlines/q1-security.md` → `output/q1-security.js` + `output/q1-security.pptx`
3. `/deck-review` → "slide 4 has text overflow, slide 7 is too dense"
4. `/edit-deck output/q1-security.js` — fix text overflow on slide 4, split slide 7 into two slides
5. `/deck-review` → "looks good, slide 7a could use speaker notes"
6. `/edit-deck output/q1-security.js` — add speaker notes to slides 7 and 8
7. Done — commit the script + PPTX together

## Testing Strategy

Each PRD includes its own unit and integration tests. A standalone test plan (`docs/plans/slides-as-code-test-plan.md`) covers cross-PRD E2E scenarios.

**Per-PRD tests:**

- **PRD 1 (Foundation):** Extended metadata operations (`"create"`, `"edit"` entries via existing `metadata.py`, history cap at 10 entries). Source detection from script content (engine, theme). Schema migration (new columns added, existing data unaffected). Ingest with `--source` flag. `decks info` and `decks source` CLI commands. Slide marker generation in create-deck output.
- **PRD 2 (Edit-deck):** Source resolution (by path and by catalog name). Backup/restore flow. Diff preview accuracy. Script regeneration (node/python). Metadata history appending. Error handling (syntax errors, file locks).
- **PRD 3 (Create-outline integration):** Outline path unit tests at each boundary (create-deck receives path → passes to ingest → ingest passes to catalog_deck → catalog stores it). Handoff message includes `/edit-deck` in both create-outline and create-deck skill files.

**Cross-PRD E2E scenarios (test plan):**

- Full cycle: create-outline → create-deck → edit-deck → regenerate → verify metadata updated
- Full cycle: create-outline → create-deck → deck-review → edit-deck (fix issues) → verify
- Source tracking round-trip: generate → ingest → `decks info` → verify all fields populated
- Manual QA checklist for the /edit-deck skill with representative edit requests

## Implementation Order (PRDs)

The work is organized into three PRDs plus a standalone test plan. PRDs 2 and 3 can be developed in parallel after PRD 1 is complete.

```
PRD 1: Foundation
  (schema + metadata + create-deck updates)
      │
      ├──→ PRD 2: Edit-Deck Skill
      │      (can start after PRD 1 merges)
      │
      └──→ PRD 3: Create-Outline Integration
             (can start after PRD 1 merges)
```

| PRD | Scope | Branch | Dependencies |
|-----|-------|--------|-------------|
| **1: Foundation** | Components 1, 3, 4 — schema migration (all 5 columns including `outline_path`), extend `metadata.py` with `"create"`/`"edit"` operation types and history cap, create-deck slide markers + auto-ingest with `--source` | `feature/slides-as-code-foundation` | None |
| **2: Edit-Deck Skill** | Component 2 — the `/edit-deck` skill for conversational editing | `feature/edit-deck-skill` | PRD 1 |
| **3: Create-Outline Integration** | Component 0 — create-deck passes `outline_path` to ingest, update create-outline `SKILL.md` Step 9 and create-deck `SKILL.md` handoff to reference `/edit-deck`, correct "Two Heading Patterns" → "Three Heading Patterns" in create-outline skill spec | `feature/outline-source-tracking` | PRD 1 |
| **Test Plan** | Cross-PRD E2E scenarios, integration test matrix, manual QA checklist | Standalone doc | Written alongside PRD 1 |

Each PRD maps to a worktree branched from `actually-useful`:

```bash
git worktree add .worktrees/slides-foundation -b feature/slides-as-code-foundation actually-useful
git worktree add .worktrees/edit-deck -b feature/edit-deck-skill actually-useful        # after PRD 1 merges
git worktree add .worktrees/outline-tracking -b feature/outline-source-tracking actually-useful  # after PRD 1 merges
```

## Competitive Context

Research confirms this approach occupies genuinely novel territory:

- **Developer slide tools** (Slidev, Marp, reveal.js) own markdown-as-source but have no PPTX round-trip
- **AI slide tools** (Gamma, PPTAgent, Beautiful.ai) generate polished slides but have no human-readable source
- **AutoPresent** (CVPR 2025, CMU) proved that code-as-intermediate-representation produces higher-quality AI-generated slides than direct image generation — validating the approach
- **No existing tool** combines: human-readable text source + PPTX round-trip + conversational editing against the source + diff/version tracking

The intersection — a system with a readable, versionable source format that round-trips through PPTX and supports conversational editing of that source — does not exist as a shipped product.

## Implementation Notes (2026-03-13)

### Metadata Format Decision

The spec originally proposed a `---aippt-meta---` YAML-ish block for change history in speaker notes. During implementation, we chose to **extend the existing `[AIPPT-META]` JSON format** instead. This avoids having two competing metadata formats in the same speaker notes field.

**What changed:**
- Source lineage fields (`source`, `created`, `layout`, `theme`, `history`) are stored as keys within the existing JSON metadata entries
- `create_lineage_entry()` helper builds the initial metadata entry with lineage fields
- `append_history_entry()` appends to the `history` array in the most recent lineage entry
- `get_slide_lineage()` extracts lineage info from metadata entries
- History is capped at 10 entries (oldest trimmed on write), matching the spec
- All existing metadata (from enhance, improve, image operations) remains backward compatible

**What stayed the same:**
- All other components (schema migration, source tracking, /edit-deck, /create-deck updates) were implemented as specified
- The conceptual model (append-only history, lineage tracking, metadata traveling with the PPTX) is identical

### Bug Fix: extract_notes_text()

During implementation, a bug was discovered in `metadata.py:extract_notes_text()` — when a slide had no human notes (only a metadata block), the function returned the entire metadata JSON as "human notes." This caused `append_metadata()` and `append_history_entry()` to nest metadata blocks incorrectly. Fixed by detecting when text starts with `[AIPPT-META]` and returning empty string.

### Components Implemented

1. **Schema migration + source tracking** (catalog.py, schema.sql, ingest.py, cli.py)
   - 5 new nullable columns on `decks`: `source_script_path`, `source_engine`, `source_theme`, `outline_path`, `source_generated_at`
   - `detect_source_engine()` and `detect_source_theme()` auto-detection helpers
   - `aippt ingest --source <script> --theme <name>` CLI flags
   - `aippt decks source <name>` and `aippt decks info` with source metadata display
   - `source_tracked: bool` in `ingest_deck()` return dict

2. **Metadata lineage helpers** (metadata.py)
   - `create_lineage_entry()`, `append_history_entry()`, `get_slide_lineage()`
   - Backward compatible with pre-lineage metadata

3. **Create-deck skill updates** (.claude/skills/create-deck/SKILL.md)
   - Slide marker comments: `// ═══ Slide N: Title ═══`
   - `[AIPPT-META]` lineage blocks in speaker notes
   - Auto-ingest with `--source` flag documentation

4. **Edit-deck skill** (.claude/skills/edit-deck/SKILL.md)
   - Full workflow: resolve source → read context → edit script → backup → regenerate → update metadata

### Testing

- 39 new tests across `test_source_tracking.py` and `test_metadata_lineage.py`
- All 1045 tests pass (no regressions)

### Deferred

- **Component 5: Improve pipeline alignment** — updating `aippt improve` to use the new metadata format (spec section "Implementation Order" item 5). The improve pipeline's existing `--- Revision ---` format in notes is left as-is; the parser treats notes without `[AIPPT-META]` as having no metadata.
