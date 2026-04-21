# Manual Testing Guide: Metadata & File Management Features

Walkthrough for the two new features added in 2026-02-26:
1. **Slide & Deck Metadata** — author, creation date, modified date
2. **Web File Management** — upload and download decks via browser

**Prerequisites:**
- Virtual environment activated
- At least one `.pptx` file available for testing (ideally one with known author/date in File Properties)
- Web server not yet running (tests start it fresh)

---

## 0. Automated Tests (Baseline)

Run the test suite first to confirm the new tests pass.

```bash
python -m pytest tests/test_catalog.py tests/test_integration.py tests/test_web_file_mgmt.py tests/test_export.py -v --tb=short
```

| Check | Expected |
|-------|----------|
| test_catalog.py metadata tests | All pass (TestCatalogMetadata, TestCatalogMetadataDefaults, TestCatalogMetadataRecatalog) |
| test_integration.py metadata API tests | All pass (TestMetadataAPIIntegration) |
| test_web_file_mgmt.py | All 6 pass (upload valid/invalid/duplicate, download existing/missing/nonexistent) |
| test_export.py | All pass (CSV columns include author, deck_created_date, slide_created_date) |

---

## 1. Metadata: Schema Migration (Existing Database)

Test that an existing database gets the new columns without errors.

```bash
# Use an existing database (or create one first)
python aippt.py catalog <your-deck.pptx> --db slides.db

# Verify new columns exist
sqlite3 slides.db "PRAGMA table_info(decks);" | grep -E "author|created_date|modified_date"
sqlite3 slides.db "PRAGMA table_info(slides);" | grep -E "author|slide_created_date"
```

| Check | Expected |
|-------|----------|
| `decks` table has `author` column | Yes, TEXT NOT NULL DEFAULT '' |
| `decks` table has `created_date` column | Yes, TEXT DEFAULT NULL |
| `decks` table has `modified_date` column | Yes, TEXT DEFAULT NULL |
| `slides` table has `author` column | Yes, TEXT NOT NULL DEFAULT '' |
| `slides` table has `slide_created_date` column | Yes, TEXT DEFAULT NULL |
| No errors on startup with old DB | Clean startup, no crashes |

---

## 2. Metadata: PPTX Core Properties Extraction

### 2a. Deck with known author

Use a PPTX file that has author set in File > Properties (or create one):

```python
# Quick script to create a test deck with properties
from pptx import Presentation
from datetime import datetime
prs = Presentation()
prs.slides.add_slide(prs.slide_layouts[0])
prs.core_properties.author = "Test Author"
prs.save("test-with-author.pptx")
```

```bash
python aippt.py catalog test-with-author.pptx --db test-meta.db
sqlite3 test-meta.db "SELECT name, author, created_date, modified_date FROM decks;"
sqlite3 test-meta.db "SELECT position, author, slide_created_date FROM slides;"
```

| Check | Expected |
|-------|----------|
| `decks.author` | "Test Author" |
| `decks.created_date` | Non-null ISO date string |
| `decks.modified_date` | Non-null ISO date string or NULL |
| `slides.author` | Same as deck author ("Test Author") |
| `slides.slide_created_date` | Same as deck created_date |

### 2b. Deck with no properties

```python
from pptx import Presentation
prs = Presentation()
prs.slides.add_slide(prs.slide_layouts[0])
prs.core_properties.author = None
prs.save("test-no-author.pptx")
```

```bash
python aippt.py catalog test-no-author.pptx --db test-meta.db
sqlite3 test-meta.db "SELECT name, author, created_date FROM decks WHERE name='test-no-author';"
```

| Check | Expected |
|-------|----------|
| `decks.author` | Empty string `''` |
| `decks.created_date` | Non-null (falls back to file mtime or PPTX default) |

### 2c. Re-catalog preserves created_date

```bash
# Catalog once
python aippt.py catalog test-with-author.pptx --db test-recatalog.db
sqlite3 test-recatalog.db "SELECT created_date FROM decks;"
# Note the created_date

# Modify the file (add a slide)
python -c "
from pptx import Presentation
prs = Presentation('test-with-author.pptx')
prs.slides.add_slide(prs.slide_layouts[0])
prs.core_properties.author = 'Updated Author'
prs.save('test-with-author.pptx')
"

# Re-catalog
python aippt.py catalog test-with-author.pptx --db test-recatalog.db
sqlite3 test-recatalog.db "SELECT author, created_date, modified_date FROM decks;"
```

| Check | Expected |
|-------|----------|
| `created_date` | Same as first catalog (preserved) |
| `author` | "Updated Author" (updated) |
| `modified_date` | Updated to new value |

---

## 3. Metadata: Web UI Display

Start the web server and check metadata is visible.

```bash
# Catalog a deck first if needed
python aippt.py catalog <your-deck.pptx> --db slides.db

# Start web server
python aippt.py serve --db slides.db
```

Open http://localhost:8000 in a browser.

### 3a. Deck list table

| Check | Expected |
|-------|----------|
| Table columns | Name, Slides, Author, Created, Updated, Actions |
| Author column | Shows author name or empty for unknown |
| Created column | Shows date (YYYY-MM-DD format), not raw ISO timestamp |
| Updated column | Shows date (YYYY-MM-DD format) |
| Empty author | Cell is empty (not "null" or "None") |
| Null created_date | Falls back to cataloged_at date |

### 3b. Slide detail modal

Click on a deck, then click on a slide to open the detail modal.

| Check | Expected |
|-------|----------|
| Metadata section visible | Yes, below the slide image |
| Author field | Shows author name or em-dash (—) if blank |
| Created field | Shows date or em-dash (—) if null |
| Last Updated field | Shows date or em-dash (—) |
| Formatting | Muted text, compact layout |

---

## 4. Metadata: CSV Export

```bash
python aippt.py export --db slides.db --all -o test-export.csv
head -1 test-export.csv
```

| Check | Expected |
|-------|----------|
| CSV header includes `author` | Yes |
| CSV header includes `deck_created_date` | Yes |
| CSV header includes `slide_created_date` | Yes |
| Column order | ...tags, author, deck_created_date, slide_created_date, content_hash... |
| Values populated | Author and dates filled in for cataloged decks |
| NULL handling | Empty string in CSV (not "None") |

---

## 5. Metadata: API Responses

With the web server running:

```bash
# Decks list
curl -s http://localhost:8000/api/decks | python -m json.tool | head -20

# Single slide (replace 1 with actual slide ID)
curl -s http://localhost:8000/api/slides/1 | python -m json.tool
```

| Check | Expected |
|-------|----------|
| `/api/decks` includes `author` | Yes, string |
| `/api/decks` includes `created_date` | Yes, string or null |
| `/api/decks` includes `modified_date` | Yes, string or null |
| `/api/slides/{id}` includes `author` | Yes, string |
| `/api/slides/{id}` includes `slide_created_date` | Yes, string or null |
| `/api/slides/{id}` includes `updated_at` | Yes, string |

---

## 6. File Management: Upload Deck

Start the web server (if not already running):

```bash
python aippt.py serve --db slides.db --uploads-dir uploads
```

### 6a. Upload a valid PPTX

| Step | Action | Expected |
|------|--------|----------|
| 1 | Click [Upload Deck] button | File picker opens |
| 2 | Select a `.pptx` file | Spinner shows "Uploading & cataloging..." |
| 3 | Wait for completion | Toast: `Uploaded "DeckName" — N slides` |
| 4 | Check deck list | New deck appears in the list |
| 5 | Check uploads directory | File exists as `{uuid}_{original_name}.pptx` |

### 6b. Upload an invalid file

| Step | Action | Expected |
|------|--------|----------|
| 1 | Click [Upload Deck] | File picker opens |
| 2 | Select a `.txt` or `.pdf` file | (picker may filter; if not:) |
| 3 | Wait for response | Error toast: "Upload failed: Only .pptx files are supported" |

### 6c. Upload a duplicate

| Step | Action | Expected |
|------|--------|----------|
| 1 | Upload same `.pptx` file again | Succeeds (no error) |
| 2 | Check deck list | Same deck shown (not duplicated, or re-cataloged) |

---

## 7. File Management: Download Deck

### 7a. Download an existing deck

| Step | Action | Expected |
|------|--------|----------|
| 1 | Find a deck in the list | Actions column has [Download] button |
| 2 | Click [Download] | Browser downloads `.pptx` file |
| 3 | Check downloaded file | Opens correctly in PowerPoint/LibreOffice |
| 4 | File name | `{deck_name}.pptx` |

### 7b. Download with missing source file

```bash
# Simulate a missing file (find file_path from DB, rename it)
sqlite3 slides.db "SELECT id, file_path FROM decks LIMIT 1;"
# Temporarily rename the file
mv <file_path> <file_path>.bak
```

| Step | Action | Expected |
|------|--------|----------|
| 1 | Click [Download] for that deck | Error (browser may show JSON or blank page) |
| 2 | Check response | 404 with "Source file not found" |
| 3 | Restore the file | `mv <file_path>.bak <file_path>` |

---

## 8. File Management: CLI Option

```bash
# Start with custom uploads directory
python aippt.py serve --db slides.db --uploads-dir /tmp/my-uploads

# Upload a deck via the UI, then check the directory
ls /tmp/my-uploads/
```

| Check | Expected |
|-------|----------|
| `--uploads-dir` accepted | No errors on startup |
| Directory created automatically | Yes, even if it didn't exist |
| Uploaded files land in specified dir | Yes |
| Default (no flag) | Uses `uploads/` in working directory |

---

## 9. Integration: Both Features Together

Upload a deck via the web UI, then check metadata is populated.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Upload a PPTX with known author via web UI | Success toast |
| 2 | Check deck list | Author and Created columns populated |
| 3 | Click into the deck, click a slide | Metadata section shows author, created, updated |
| 4 | Download the deck | Downloaded file matches the original |
| 5 | Export CSV | New deck appears with metadata columns filled |

---

## Cleanup

```bash
# Remove test artifacts
rm -f test-with-author.pptx test-no-author.pptx
rm -f test-meta.db test-recatalog.db test-export.csv
rm -rf uploads/
```
