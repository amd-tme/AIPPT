# PRD: Web UI File Management (Upload & Download Decks)

**Date:** 2026-02-26
**Author:** Matt
**Status:** Draft

---

## Summary

Add basic file management to the web UI so users can upload PowerPoint decks (triggering catalog ingest) and download previously cataloged decks — without needing the CLI. This removes the CLI as a prerequisite for getting decks into the system, making the web UI a self-contained entry point.

## Motivation

- **What problem does this solve?** Currently, the only way to ingest a deck is via `outline2ppt catalog` on the command line. Users who primarily interact through the web UI have no way to add new decks or retrieve original files.
- **Who benefits?** End users who prefer the web UI over CLI workflows.
- **What happens if we don't do this?** The web UI remains read-only for deck management, limiting adoption to CLI-comfortable users.

## Requirements

### Must Have

- [ ] Upload one or more `.pptx` files via the web UI
- [ ] Uploaded files are saved to a configurable storage directory
- [ ] Uploaded files are automatically cataloged (calls `catalog_deck()`)
- [ ] Download the original `.pptx` file for any cataloged deck
- [ ] Upload progress feedback (spinner/toast) in the UI
- [ ] Error handling for invalid files, duplicates, and missing source files

### Nice to Have

- [ ] Drag-and-drop upload zone
- [ ] Bulk upload (multiple files in one request)
- [ ] Upload slide images alongside the deck (zip or directory)

### Out of Scope

- Delete deck from web UI (remains CLI / direct DB operation per user request)
- Re-catalog / refresh deck from web UI
- Upload non-PPTX formats

---

## Design

### Approach

Add two new API endpoints to `routes.py`: one for uploading decks (multipart form POST) and one for downloading decks (file stream GET). The upload endpoint saves the file to a storage directory (`uploads/` by default, configurable), then calls the existing `catalog_deck()` function. The download endpoint reads `file_path` from the `decks` table and streams the file back.

The storage directory path is passed through `app.state` at startup, similar to how `db_path` and `gateway_config` are handled today.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/web/routes.py` | Modified | Add `POST /api/decks/upload` and `GET /api/decks/{deck_id}/download` endpoints |
| `outline2ppt/web/app.py` | Modified | Accept and store `uploads_dir` in `app.state` |
| `outline2ppt/web/static/index.html` | Modified | Add upload form to Decks view, add download button to deck list rows |
| `outline2ppt/cli.py` | Modified | Pass `--uploads-dir` to web server startup if applicable |

### Data Model Changes

No schema changes required. The existing `decks.file_path` column stores the absolute path to the source file, which will point to the uploads directory for web-uploaded decks.

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `outline2ppt web` | New option `--uploads-dir` | Directory where uploaded decks are stored (default: `uploads/`) |

### Example Usage

```bash
# Start web server with custom uploads directory
python outline2ppt.py web --uploads-dir /data/decks

# Default behavior (uploads/ in working directory)
python outline2ppt.py web
```

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Deck List | Add upload button | Opens file picker for `.pptx` files, triggers upload + ingest |
| Deck List | Add download button per row | Downloads original `.pptx` file |

### New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/decks/upload` | Accept multipart `.pptx` file, save to uploads dir, catalog, return deck metadata |
| GET | `/api/decks/{deck_id}/download` | Stream the original `.pptx` file as a download |

### Wireframe / Mockup

```
┌─────────────────────────────────────────────────────┐
│  Decks                              [Upload Deck]   │
├──────────────────┬────────┬───────────┬─────────────┤
│  Name            │ Slides │ Cataloged │ Actions     │
├──────────────────┼────────┼───────────┼─────────────┤
│  Q4 Strategy     │   12   │ 2026-02-20│ [Download]  │
│  Product Launch  │    8   │ 2026-02-25│ [Download]  │
│  Team Onboard    │   15   │ 2026-02-26│ [Download]  │
└──────────────────┴────────┴───────────┴─────────────┘
```

Upload flow: click [Upload Deck] → file picker (`.pptx` only) → spinner with "Uploading & cataloging..." → toast on success with deck name and slide count → deck list refreshes.

Download flow: click [Download] → browser download of `{deck_name}.pptx`.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_web_file_mgmt.py` | `TestUploadDeck`, `TestDownloadDeck` | Upload endpoint, download endpoint, error cases |

### Integration Tests

Add to `tests/test_integration.py`:
- Upload a `.pptx` file via API, verify it appears in deck list and slides are cataloged
- Download a deck via API, verify file contents match original
- Upload duplicate file, verify appropriate response (existing deck returned)
- Upload invalid file (non-PPTX), verify 400 error
- Download deck with missing source file, verify 404 error

### Manual Testing

1. Start web server, click Upload Deck, select a `.pptx` file — deck appears in list with correct slide count
2. Click Download on a deck — browser downloads the `.pptx` file, opens correctly in PowerPoint
3. Upload the same file again — appropriate feedback (already cataloged or re-cataloged)
4. Upload a `.txt` file — error toast displayed

---

## Changelog Entry

```markdown
### Added
- Web UI: Upload PowerPoint decks directly from the browser with automatic cataloging
- Web UI: Download original `.pptx` files from the deck list
- API: `POST /api/decks/upload` endpoint for deck upload and ingest
- API: `GET /api/decks/{deck_id}/download` endpoint for deck download
- CLI: `--uploads-dir` option for web server to configure upload storage location
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add `uploads_dir` to app.state and CLI option | `app.py`, `cli.py` | -- |
| 2 | Implement `POST /api/decks/upload` endpoint | `routes.py` | 1 |
| 3 | Implement `GET /api/decks/{deck_id}/download` endpoint | `routes.py` | -- |
| 4 | Add upload button and form to deck list UI | `index.html` | 2 |
| 5 | Add download button to deck list rows | `index.html` | 3 |
| 6 | Add tests for upload and download endpoints | `tests/test_web_file_mgmt.py` | 2, 3 |
| 7 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Uploaded files could be large — mitigate with a configurable max file size (default 100MB) enforced at the endpoint level.
- **Risk:** `file_path` in DB stores absolute paths; if the uploads directory moves, download breaks — mitigate by documenting that the uploads directory should be stable, and consider storing relative paths in a future iteration.
- **Question:** Should the upload endpoint also trigger image export (via PowerShell script) for slide thumbnails? — Recommend no for v1; image export requires PowerShell/COM automation and is a separate concern. Users can run the export script separately.
- **Question:** Should uploaded files be renamed to avoid collisions (e.g., UUID prefix)? — Recommend yes: save as `{uuid}_{original_name}.pptx` to avoid overwrites while preserving the original filename for display.

---

## References

- Related PRDs: `docs/plans/2026-02-18-outline2ppt-v2-implementation.md`
- Existing ingest flow: `outline2ppt/catalog.py:catalog_deck()`
- Web routes: `outline2ppt/web/routes.py`
- PRD Template: `docs/plans/PRD-TEMPLATE.md`
