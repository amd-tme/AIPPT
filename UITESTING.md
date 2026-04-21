# UI & Feature Testing Guide - Tasks 9-16

Manual validation walkthrough for export, search, remix, and web UI features.

**Prerequisites:**
- Virtual environment activated: `source venv/Scripts/activate`
- Test deck available: `decks/4Q25-Instinct-Partitioning.pptx` (61 slides)
- Slide images available: `decks/4Q25-Instinct-Partitioning/` (61 PNGs)
- Test database from prior testing: `decks/test-slides.db`

**Note:** All commands below assume you are in the project root directory.

---

## 0. Unit Tests (Baseline)

Run the full test suite first to confirm everything is green.

```bash
python -m pytest tests/ -v --tb=short
```

| Check | Expected |
|-------|----------|
| Total tests | 211 passing |
| Skipped | 3 (gateway live tests) |
| Failures | 0 |

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

## 4. Web UI (Task 13)

### 4.1 Install web dependencies (if not already)

```bash
pip install fastapi uvicorn python-multipart
```

### 4.2 Launch the web server

```bash
python aippt.py serve --db decks/test-slides.db --port 8000
```

| Check | Expected |
|-------|----------|
| Console output | `Starting AIPPT web UI on http://127.0.0.1:8000` |
| Server running | Uvicorn logs show `Application startup complete` |

Keep this terminal open; use a separate terminal or browser for the remaining tests.

### 4.3 Dashboard (Deck List)

Open `http://127.0.0.1:8000` in a browser.

| Check | Expected |
|-------|----------|
| Page loads | "AIPPT" header visible |
| Navigation | "Decks", "Search", "Export CSV" links in nav bar |
| Deck table | Shows cataloged deck(s) with name, slide count, dates |
| Styling | Pico CSS applied (clean, modern look) |

### 4.4 Slide Browser

Click on a deck name in the table.

| Check | Expected |
|-------|----------|
| View switches | Deck list hidden, slide grid shown |
| Back link | "Back to decks" link visible at top |
| Deck name | Shown as heading |
| Slide cards | Grid of cards, one per slide |
| Thumbnails | Slide images displayed (or "No image" placeholder) |
| Card content | Shows "Slide N: Title" and any tags |

### 4.5 Slide Detail Modal

Click on any slide card.

| Check | Expected |
|-------|----------|
| Dialog opens | Modal/dialog appears over the page |
| Title | Shows "Slide N: Title" |
| Image | Full slide image displayed (or "No image available") |
| Tags section | Shows existing tags (or "none") |
| Add tag input | Text input and "Add Tag" button visible |
| Speaker Notes | Expandable "Speaker Notes" section with slide notes |
| Close button | X button in header closes the dialog |

### 4.6 Manual Tagging via Web UI

In the slide detail modal:

1. Type `test-web-tag` in the "Add tag..." input
2. Click "Add Tag"

| Check | Expected |
|-------|----------|
| Toast notification | "Tagged: test-web-tag" appears briefly at bottom-right |
| Tag display | `test-web-tag` now shows in the tags section of the modal |
| Persistence | Close and re-open the modal -- tag is still there |

**Verify in database:**
```bash
sqlite3 decks/test-slides.db "SELECT t.name, t.source FROM tags t WHERE t.name = 'test-web-tag';"
```

| Check | Expected |
|-------|----------|
| Tag record | Shows `test-web-tag|manual` |

### 4.7 Search via Web UI

Click "Search" in the nav bar.

| Check | Expected |
|-------|----------|
| View switches | Search form displayed with title and tags inputs |

**Search by title:**
1. Type a known slide title substring (e.g. "ROCm") in "Title contains"
2. Click "Search"

| Check | Expected |
|-------|----------|
| Results | Slide cards matching the title appear |
| No results | If no match, shows "No matching slides found." |

**Search by tags:**
1. Clear the title field
2. Type `test-web-tag` in "Tags" field (from step 4.6)
3. Click "Search"

| Check | Expected |
|-------|----------|
| Results | Only the slide you tagged in step 4.6 appears |

### 4.8 CSV Export via Web UI

Click "Export CSV" button in the nav bar.

| Check | Expected |
|-------|----------|
| File download | Browser downloads `slides.csv` |
| CSV content | Contains all cataloged slides with headers matching export format |

### 4.9 API Endpoints (optional, for thorough testing)

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

### 4.10 Stop the server

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
