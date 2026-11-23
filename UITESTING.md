# UI & Feature Testing Guide

Manual validation walkthrough for export, search, remix, and web UI features.
Refreshed 2026-08-03 to match the app as shipped through the AMD Theme
Tightening, Chat-with-a-Deck, and Live Script Render / Live Preview work
(all live since 07-09/07-17) — the previous "Tasks 9-16" version of this doc
described the pre-SPA dashboard/modal UI and was no longer accurate.

**Prerequisites:**
- Virtual environment activated: `source venv/Scripts/activate` (Windows Git Bash) or `source venv/bin/activate` (Linux/Mac/WSL)
- Test deck available: `decks/4Q25-Instinct-Partitioning.pptx` (61 slides)
- Slide images available: `decks/4Q25-Instinct-Partitioning/` (61 PNGs)
- Test database from prior testing: `decks/test-slides.db`
- To exercise **Chat / Create / Regen** (anything that calls the LLM gateway): either sign in via **"Sign in to Microsoft"** in the nav, or set `AIPPT_USER_NTID=<your ntid>` before starting the server. Without one of these, those actions correctly fail with a visible "User NTID is required" error in the UI — that's expected behavior, not a bug, so don't report it as one.

**Note:** All commands below assume you are in the project root directory.

**Known issue going in:** the top nav has no responsive breakpoint between roughly 945px and 1440px viewport width — nav items visibly overlap and become unclickable in that range (tracked in Linear MAT-53). Maximize your browser window, or expect to see this.

---

## 0. Unit Tests (Baseline)

Run the full test suite first to confirm everything is green.

```bash
python -m pytest tests/ -v --tb=short
```

| Check | Expected |
|-------|----------|
| Total tests | ~1600 passing (suite has grown substantially — don't be alarmed if the exact count has shifted) |
| Skipped | ~5 (gateway live tests + others) |
| Known failures | 4, all pre-existing test-fixture drift, not live bugs: 2 in `test_theme_tokens.py` (assert pre-theme-rewrite colors/fonts), 1 in `test_master_pptx.py` (assumes title slides never carry their own logo art, which they now intentionally do), 1 in `test_web_images_dir.py` (mock patch-target likely stale after a route refactor). See `Scratch/2026/08 - August/AIPPT Testing 2026-08-03/AIPPT Agent Testing Findings.md` for detail. |
| New/unexpected failures | Report these — they're the ones that matter |

---

## 1. Export Command (Tasks 9-10)

### 1.1 Export help

```bash
python aippt.py export --help
```

| Check | Expected |
|-------|----------|
| Help text displayed | Shows `deck`, `--all`, `--output`, `--db` options |

### 1.2 Export all cataloged decks

```bash
python aippt.py export --all --output decks/test-export-all.csv --db decks/test-slides.db
```

| Check | Expected |
|-------|----------|
| Exit code | 0 |
| Console output | `Exported N slides to decks/test-export-all.csv` (N = 61 if only one deck cataloged) |
| CSV file created | `decks/test-export-all.csv` exists |

**Inspect the CSV:**
```bash
head -3 decks/test-export-all.csv
```

| Check | Expected |
|-------|----------|
| Header row | `deck_name,slide_number,title,notes,tags,content_hash,image_path,last_updated` |
| Data rows | Slide titles, position numbers, notes content visible |

### 1.3 Export a specific deck

```bash
python aippt.py export decks/4Q25-Instinct-Partitioning.pptx --output decks/test-export-deck.csv --db decks/test-slides.db
```

| Check | Expected |
|-------|----------|
| Exit code | 0 |
| Console output | `Exported 61 slides to decks/test-export-deck.csv` |

### 1.4 Export with no args (error case)

```bash
python aippt.py export --db decks/test-slides.db
```

| Check | Expected |
|-------|----------|
| Exit code | 1 |
| Error message | `Specify a deck path or use --all` |

---

## 2. Search Command (Task 12)

### 2.1 Search help

```bash
python aippt.py search --help
```

| Check | Expected |
|-------|----------|
| Help text displayed | Shows `--tags`, `--title-contains`, `--export-manifest`, `--db` options |

### 2.2 Search by title substring

```bash
python aippt.py search --title-contains "ROCm" --db decks/test-slides.db
```

| Check | Expected |
|-------|----------|
| Exit code | 0 |
| Console output | Lists matching slides with `[deck_name] Slide N: Title` format |
| Results | Only slides with "ROCm" in the title appear |

### 2.3 Search with no results

```bash
python aippt.py search --title-contains "xyznonexistent" --db decks/test-slides.db
```

| Check | Expected |
|-------|----------|
| Exit code | 0 |
| Console output | `No matching slides found.` |

### 2.4 Search by tags (requires prior tagging)

If slides have been tagged (via `analyze --mode tags`):

```bash
python aippt.py search --tags "architecture" --db decks/test-slides.db
```

| Check | Expected |
|-------|----------|
| Results | Only slides tagged with "architecture" appear |

If no tags exist yet, this will return no results (expected).

### 2.5 Export search results as remix manifest

```bash
python aippt.py search --title-contains "Instinct" --export-manifest decks/test-manifest.yaml --db decks/test-slides.db
```

| Check | Expected |
|-------|----------|
| Console output | Lists matching slides, then `Manifest written to decks/test-manifest.yaml` |
| Manifest file | `decks/test-manifest.yaml` exists |

**Inspect the manifest:**
```bash
cat decks/test-manifest.yaml
```

| Check | Expected |
|-------|----------|
| YAML structure | Has `title`, `template`, `slides` keys |
| Each slide entry | Has `deck`, `deck_path`, `position`, `title` fields |
| `deck_path` values | Absolute paths to the source PPTX |

---

## 3. Remix Command (Task 12)

### 3.1 Remix help

```bash
python aippt.py remix --help
```

| Check | Expected |
|-------|----------|
| Help text displayed | Shows `manifest`, `output`, `--db` arguments |

### 3.2 Create a manual manifest

Create `decks/manual-manifest.yaml` with 3 cherry-picked slides:

```yaml
title: Cherry-Picked Deck
slides:
  - deck: 4Q25-Instinct-Partitioning.pptx
    deck_path: decks/4Q25-Instinct-Partitioning.pptx
    position: 1
    title: Title Slide
  - deck: 4Q25-Instinct-Partitioning.pptx
    deck_path: decks/4Q25-Instinct-Partitioning.pptx
    position: 5
    title: Fifth Slide
  - deck: 4Q25-Instinct-Partitioning.pptx
    deck_path: decks/4Q25-Instinct-Partitioning.pptx
    position: 10
    title: Tenth Slide
```

**Note:** The `deck_path` must be correct relative to where you run the command. Adjust if needed.

### 3.3 Assemble remixed deck

```bash
python aippt.py remix decks/manual-manifest.yaml decks/test-remixed.pptx --db decks/test-slides.db
```

| Check | Expected |
|-------|----------|
| Exit code | 0 |
| Console output | `Remixed deck saved to decks/test-remixed.pptx (3 slides)` |
| Output file | `decks/test-remixed.pptx` exists |

**Open `decks/test-remixed.pptx` in PowerPoint:**

| Check | Expected |
|-------|----------|
| Slide count | 3 slides |
| Slide content | Content matches slides 1, 5, 10 from the source deck |

### 3.4 Remix from search-generated manifest

If you generated `decks/test-manifest.yaml` in step 2.5:

```bash
python aippt.py remix decks/test-manifest.yaml decks/test-search-remix.pptx --db decks/test-slides.db
```

| Check | Expected |
|-------|----------|
| Exit code | 0 |
| Output file | `decks/test-search-remix.pptx` exists and can be opened |

### 3.5 Remix with missing manifest (error case)

```bash
python aippt.py remix nonexistent.yaml output.pptx
```

| Check | Expected |
|-------|----------|
| Exit code | 1 |
| Error message | `Manifest file not found` |

---

## 4. Web UI

### 4.1 Install web dependencies (if not already)

```bash
pip install fastapi uvicorn python-multipart
```

### 4.2 Launch the web server

```bash
python aippt.py serve --db decks/test-slides.db --port 8000
```

For full-mode testing (Chat/Create/Regen calling the real LLM gateway), also export `AMD_LLM_KEY` and set `AIPPT_USER_NTID` first, or plan to sign in via the nav once the server is up.

| Check | Expected |
|-------|----------|
| Console output | `Starting AIPPT web UI on http://127.0.0.1:8000 (full mode)` (or `(view-only mode)` if `AIPPT_VIEW_ONLY=1`) |
| Server running | Uvicorn logs show `Application startup complete` |

Keep this terminal open; use a separate terminal or browser for the remaining tests.

### 4.3 Dashboard (Cataloged Decks)

Open `http://127.0.0.1:8000` in a browser. **Maximize the window first** — see the known nav-overflow issue above.

| Check | Expected |
|-------|----------|
| Page loads | "AIPPT" header visible |
| Navigation | "Tags", "Decks", "Search", "Settings", "Live Preview", "Docs" in the left nav group; "Export CSV", sign-in button, appearance toggle on the right |
| Onboarding tour | A "1/6 Welcome to AIPPT" tour pops up on first load — confirm "Skip" and "Next" both work, and re-verify MAT-53's tour-restart nit (does "Tour" in the bottom-right reopen at step 1, or resume at a later step?) |
| Deck grid | Shows cataloged decks as thumbnail cards with slide count + date; "Create Deck from Outline" tile is always first |
| Card actions | Download / Notes / Chat / Regen / Delete buttons present per card (Regen/Delete only on decks with a source script) |
| Sign-in gating | Without signing in, upload/create-related actions show "Sign in to Microsoft" / "Sign in to upload" rather than failing silently |

### 4.4 Deck Detail (slide grid + Live Preview + Chat)

Click on a deck card.

| Check | Expected |
|-------|----------|
| View switches | Deck detail replaces the dashboard; "← Back to decks" link at top |
| Slide grid | One card per slide, each with thumbnail + "Slide N: Title" |
| Live Preview panel | Right-side panel, initially "No live preview — open Live Preview to render." with disabled ‹ › controls |
| Chat panel | Below Live Preview: conversation picker (defaults to "Chat"), "+ New" / "✕ Delete" conversation buttons, a Scope selector (All slides or a specific slide), Ask/Edit/★ Review mode radios, and a message box |

### 4.5 Chat with a Deck

With a deck open and either signed in or `AIPPT_USER_NTID` set:

1. Leave mode on **Ask**, type a question (e.g. "In one sentence, what is this deck about?"), send (button or Ctrl+Enter).

| Check | Expected |
|-------|----------|
| Message appears | Your question shows in the thread immediately |
| Response streams in | A coherent answer appears within a few seconds (SSE) |
| Without sign-in/NTID | Instead of a response, the thread shows "Error: User NTID is required for LLM gateway requests..." — this is correct, expected behavior, not a bug |

2. Try **Edit** mode against a single slide (Scope = one slide, describe a change) — confirm it proposes a patch rather than answering conversationally.
3. Try **★ Review** mode — confirm it produces a findings/review pass rather than a chat answer.
4. Use "+ New" to start a second conversation, confirm the picker lets you switch between them, and "✕ Delete" removes one.

### 4.6 Live Preview

From a deck's Live Preview panel, or via the **Live Preview** nav link (which opens a standalone "Script Preview" page with a script picker):

1. Pick a `.py`/`.js`/`.mjs` script from the dropdown (recently-generated decks are listed), or paste a path.
2. Click **Open**.

| Check | Expected |
|-------|----------|
| Status | Changes from "Idle" to rendering, then shows "● Updated just now" |
| Viewer | Renders the deck via PptxViewJS; "Slide 1 of N" with ‹ › navigation |
| Grid toggle | "⊞ Grid" view shows a thumbnail grid instead of the single-slide viewer |
| Force render | Re-renders on demand without reopening |
| Save to Library | Catalogs the currently-open script as a deck |
| Disclaimer | "⚠ Rendered via PptxViewJS — effects may differ from PowerPoint export" is shown — spot-check one rendered slide against the actual `.pptx` if you want to validate that claim |

### 4.7 Tags

Click **Tags** in the nav (a button, not a page link — it opens as a slide-out panel over whatever page you're on).

| Check | Expected |
|-------|----------|
| Panel opens | Left-side overlay, doesn't navigate away from the current page |
| Tag list | Grouped (e.g. "Other"), each tag shows a count |
| Clear all | Present; don't click it during testing unless you intend to wipe tags from the test db |

### 4.8 Search via Web UI

Click "Search" in the nav bar.

| Check | Expected |
|-------|----------|
| View switches | Search form with "Title contains" and "Tags (comma-separated)" inputs |

**Search by title:**
1. Type a known slide title substring (e.g. "ROCm") in "Title contains", click "Search".

| Check | Expected |
|-------|----------|
| Results | Slide cards matching the title appear, with thumbnails |
| No results | If no match, shows "No matching slides found." |

**Search by tags:** clear the title field, enter a known tag, search — confirm only matching slides return.

### 4.9 Settings (Model Defaults)

Click "Settings" in the nav.

| Check | Expected |
|-------|----------|
| Table | One row per operation (create, enhance, feedback, image, improve, notes, reverse, tags) showing current model + a dropdown to change it |
| Source line | Shows the `models.yaml` path being used |
| Save | Per-row Save button persists a model change |
| Reset All to Defaults | Present at the bottom |

### 4.10 CSV Export via Web UI

Click "Export CSV" button in the nav bar.

| Check | Expected |
|-------|----------|
| File download | Browser downloads `slides.csv` |
| CSV content | Contains all cataloged slides with headers matching export format |

### 4.11 API Endpoints (optional, for thorough testing)

Test the raw JSON endpoints in a new terminal:

```bash
# List decks
curl http://127.0.0.1:8000/api/decks

# Get slides for deck 1
curl http://127.0.0.1:8000/api/decks/1/slides

# Search
curl "http://127.0.0.1:8000/api/search?title=ROCm"

# Add tag via API
curl -X POST http://127.0.0.1:8000/api/slides/1/tags \
  -H "Content-Type: application/json" \
  -d '{"tags": ["api-test"], "source": "manual"}'
```

| Check | Expected |
|-------|----------|
| `/api/decks` | JSON array of deck objects |
| `/api/decks/1/slides` | JSON array with `id`, `position`, `title`, `tags`, `notes`, `image_path` |
| `/api/search` | JSON array of matching slides |
| POST tags | `{"status": "ok", "tags": [...]}` response |

### 4.12 Stop the server

Press `Ctrl+C` in the terminal running the server.

---

## 5. Requirements & Packaging (Task 14)

### 5.1 Check requirements.txt

```bash
cat requirements.txt
```

| Check | Expected |
|-------|----------|
| `fastapi>=0.100.0` | Present |
| `uvicorn>=0.23.0` | Present |
| `python-multipart>=0.0.6` | Present |
| Existing deps | `python-pptx`, `anthropic`, `openai`, etc. still present |

### 5.2 Check pyproject.toml

```bash
cat pyproject.toml
```

| Check | Expected |
|-------|----------|
| `[project]` section | name = "aippt", version = "2.0.0" |
| `[project.scripts]` | `aippt = "aippt.cli:main"` |
| `requires-python` | `>=3.10` |

---

## 6. CLAUDE.md (Task 15)

```bash
cat CLAUDE.md
```

| Check | Expected |
|-------|----------|
| Title | "AIPPT v2" |
| CLI commands | All 8 subcommands documented (create, reverse, catalog, analyze, search, remix, export, serve) |
| Architecture | Package structure listing with all modules |
| Gateway config | Example YAML shown |
| Database | SQLite schema tables mentioned |

---

## 7. Integration Tests (Task 16)

```bash
python -m pytest tests/test_integration.py -v
```

| Check | Expected |
|-------|----------|
| `test_full_catalog_search_tag_export_flow` | PASS |
| `test_search_and_manifest_generation` | PASS |
| `test_remix_assembly` | PASS |
| `test_recatalog_detects_same_file` | PASS |
| `test_export_specific_deck` | PASS |
| Total | 5 passed |

---

## 8. End-to-End Workflow

This is the full pipeline test, combining everything into one flow.

```bash
# Fresh database for clean test
DB=decks/e2e-test.db

# Step 1: Catalog the deck with images
python aippt.py catalog decks/4Q25-Instinct-Partitioning.pptx \
  --images-dir decks/4Q25-Instinct-Partitioning \
  --db $DB

# Step 2: Search for slides by title
python aippt.py search --title-contains "Instinct" --db $DB

# Step 3: Export all to CSV
python aippt.py export --all --output decks/e2e-export.csv --db $DB

# Step 4: Search and generate manifest
python aippt.py search --title-contains "Instinct" \
  --export-manifest decks/e2e-manifest.yaml --db $DB

# Step 5: Remix from manifest
python aippt.py remix decks/e2e-manifest.yaml \
  decks/e2e-remixed.pptx --db $DB

# Step 6: Launch web UI (manual check, then Ctrl+C)
python aippt.py serve --db $DB --port 8001
```

| Step | Check | Expected |
|------|-------|----------|
| 1 | Catalog | `Cataloged deck (id=1)` |
| 2 | Search | Matching slides listed |
| 3 | Export | CSV file created with 61 rows |
| 4 | Manifest | YAML file created with matching slides |
| 5 | Remix | PPTX created, opens in PowerPoint |
| 6 | Web UI | Dashboard shows deck, slides browsable |

---

## Cleanup

Remove test artifacts when done:

```bash
rm -f decks/test-export-all.csv decks/test-export-deck.csv
rm -f decks/test-manifest.yaml decks/manual-manifest.yaml
rm -f decks/test-remixed.pptx decks/test-search-remix.pptx
rm -f decks/e2e-test.db decks/e2e-export.csv decks/e2e-manifest.yaml decks/e2e-remixed.pptx
```
