# PRD: PPTX Notes Write-Back

**Date:** 2026-03-02
**Author:** Matt
**Status:** Draft

---

## Summary

Write edited speaker notes from the SQLite database back to the source PPTX file. This completes the round-trip for the web notes editing feature (see `docs/plans/2026-03-02-web-notes-editing.md`). Three triggers: CLI command, web "Write to Deck" button, and automatic application on download.

## Motivation

- **What problem does this solve?** The web UI can edit and save notes in the database, but these changes are not reflected in the PPTX file. Users who share or present the deck will not see their web edits.
- **Who benefits?** Users who edit notes in the web UI and then need the updated deck for presentation or distribution.
- **What happens if we don't do this?** The database becomes a dead end — edits stay trapped in the web UI. Users must manually copy notes back to PowerPoint, defeating the purpose of web editing.

## Requirements

### Must Have

- [ ] Core `write_notes_to_pptx()` function that applies DB notes to a PPTX file
- [ ] CLI command: `outline2ppt write-notes <deck.pptx> [--db slides.db]`
- [ ] Web API: `POST /api/decks/{id}/write-notes` — writes notes to original file with backup
- [ ] Web API: `GET /api/decks/{id}/download` — serves a temp copy with DB notes applied (original untouched)
- [ ] Timestamped `.bak` backup before modifying the original file
- [ ] Slide count validation: abort with error if PPTX and DB slide counts don't match
- [ ] Create notes frame on slides that lack one (when DB has notes for that position)
- [ ] Skip slides where DB notes are empty/null (don't create empty notes frames)

### Nice to Have

- [ ] Web UI "Write to Deck" button in deck detail view
- [ ] `--no-backup` CLI flag to skip backup creation

### Out of Scope

- Writing back title, tags, or other metadata to PPTX
- Creating new slides or changing slide layout
- Collaborative conflict resolution
- Partial writes when slide counts mismatch
- Backup retention policy

---

## Design

### Approach

A new module `outline2ppt/writeback.py` contains the core logic. It opens the PPTX, iterates DB slides by position, and writes the `notes` field to the corresponding slide's notes text frame. Three callers use this core with different save strategies:

1. **CLI and web write-notes:** Caller creates a backup, then calls the core function to save in-place.
2. **Download endpoint:** Caller copies to a temp file, calls the core function to save to the temp file, then serves it.

The core function validates that the PPTX slide count matches the DB slide count and aborts if they differ.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/writeback.py` | New | Core `write_notes_to_pptx()` function and `WritebackResult` dataclass |
| `outline2ppt/cli.py` | Modified | Add `write-notes` subcommand |
| `outline2ppt/web/routes.py` | Modified | Add `POST /api/decks/{id}/write-notes`; update `GET /api/decks/{id}/download` to apply notes |
| `outline2ppt/web/static/index.html` | Modified | Add "Write to Deck" button in deck detail view |

### Data Model Changes

No data model changes.

### Core Function

```python
@dataclass
class WritebackResult:
    deck_id: int
    slides_written: int       # notes actually applied
    slides_skipped: int       # DB slides with empty/null notes
    slides_total: int         # total slides (same in DB and PPTX)
    backup_path: str | None   # path to backup if one was created
    warnings: list[str]       # human-readable messages

def write_notes_to_pptx(
    deck_path: str,
    db_path: str = "slides.db",
    deck_id: int | None = None,
    output_path: str | None = None,
) -> WritebackResult:
    """Write DB notes to a PPTX file.

    Args:
        deck_path: Path to the source PPTX file
        db_path: Path to the SQLite database
        deck_id: Deck ID in DB (if None, look up by file_path)
        output_path: Save to this path instead of deck_path (for temp copies)

    Raises:
        FileNotFoundError: PPTX file doesn't exist
        ValueError: Deck not found in DB, or slide count mismatch
    """
```

**Algorithm:**
1. Validate `deck_path` exists on disk
2. Look up deck in DB by `deck_id` or by `file_path`
3. Fetch all DB slides ordered by position
4. Open PPTX with `Presentation(deck_path)`
5. Compare `len(prs.slides)` to `len(db_slides)` — raise `ValueError` if they differ
6. For each DB slide with non-empty notes:
   - Access `prs.slides[position - 1]`
   - If slide has no notes slide, create one via `slide.notes_slide`
   - Set `slide.notes_slide.notes_text_frame.text = notes`
7. Save to `output_path` if provided, else to `deck_path`
8. Return `WritebackResult`

### Backup Function

```python
def create_backup(deck_path: str) -> str:
    """Copy deck_path to deck_path.{ISO-timestamp}.pptx.bak. Returns backup path."""
```

Uses `shutil.copy2()`. Timestamp format: `%Y-%m-%dT%H-%M-%S` (filesystem-safe). Stored alongside the original.

---

## CLI Changes

### New Commands

```
outline2ppt write-notes <deck.pptx> [--db slides.db]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `deck.pptx` | Yes | — | Path to the PPTX file |
| `--db` | No | `slides.db` | Path to the SQLite database |

### Example Usage

```bash
# Write DB notes back to the deck (creates backup automatically)
python outline2ppt.py write-notes presentation.pptx

# Specify a different database
python outline2ppt.py write-notes presentation.pptx --db myslides.db
```

Output:
```
Backup created: presentation.2026-03-02T14-32-00.pptx.bak
Wrote notes to 12 of 15 slides (3 skipped — no notes in DB)
```

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Deck detail / slide grid | "Write to Deck" button | Button next to the existing download button. Calls `POST /api/decks/{id}/write-notes`. Shows toast with result summary. |
| Deck detail / slide grid | Download behavior | Download now serves a temp copy with DB notes applied |

### New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/decks/{deck_id}/write-notes` | Write DB notes to the original PPTX (with backup). Returns `WritebackResult` as JSON. |

### Modified API Endpoints

| Method | Path | Change |
|--------|------|--------|
| GET | `/api/decks/{deck_id}/download` | Now applies DB notes to a temp copy before serving. Original file untouched. |

### Wireframe

**Deck action buttons (existing download + new write-to-deck):**

```
┌──────────────────────────────────────┐
│  Deck: Q4 Revenue Review            │
│  15 slides · Cataloged 2026-03-01   │
│                                     │
│  [Download ↓]  [Write Notes to Deck]│
│                                     │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐   │
│  │  1  │ │  2  │ │  3  │ │  4  │   │
│  └─────┘ └─────┘ └─────┘ └─────┘   │
└──────────────────────────────────────┘
```

**After clicking "Write Notes to Deck":**
- Success toast: "Wrote notes to 12 of 15 slides. Backup: presentation.2026-03-02T14-32-00.pptx.bak"
- Error toast (mismatch): "Slide count mismatch: DB has 15 slides but PPTX has 16. Re-catalog the deck to sync."

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_writeback.py` | `TestWriteNotesToPptx` | Core function: writes notes to correct slides, skips empty notes |
| `tests/test_writeback.py` | `TestSlideCountMismatch` | Raises `ValueError` when DB and PPTX slide counts differ |
| `tests/test_writeback.py` | `TestNotesFrameCreation` | Creates notes frame when slide lacks one |
| `tests/test_writeback.py` | `TestOutputPath` | Saves to `output_path` when provided, leaves original untouched |
| `tests/test_writeback.py` | `TestCreateBackup` | `create_backup()` copies file with correct naming |
| `tests/test_writeback.py` | `TestDeckNotFound` | Raises `ValueError` when deck not in DB |
| `tests/test_writeback.py` | `TestFileNotFound` | Raises `FileNotFoundError` when PPTX missing |

### Integration Tests

Add to `tests/test_integration.py`:
- Catalog a deck, edit notes via `record_edit()`, write back, verify PPTX notes match
- Catalog a deck, write back with `output_path`, verify original is unchanged
- Full round-trip: catalog → edit notes → write back → re-catalog → verify notes preserved

### Route Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_web_routes.py` | `TestWriteNotesEndpoint` | `POST /api/decks/{id}/write-notes` returns result, creates backup |
| `tests/test_web_routes.py` | `TestWriteNotesMismatch` | Returns 409 when slide count mismatch |
| `tests/test_web_routes.py` | `TestDownloadWithNotes` | `GET /api/decks/{id}/download` serves file with DB notes applied |

### Manual Testing

1. Catalog a deck with existing speaker notes
2. Edit notes for several slides in the web UI
3. Click "Write Notes to Deck" — verify backup created, toast shows summary
4. Open the PPTX in PowerPoint — verify edited notes appear
5. Click Download — verify downloaded file has DB notes, original on disk is unchanged
6. CLI: run `write-notes` command — verify backup created, notes written
7. Add a slide to the PPTX in PowerPoint (without re-cataloging) — verify write-notes returns error about slide count mismatch

---

## Changelog Entry

```markdown
### Added
- CLI: `outline2ppt write-notes` command to write DB notes back to PPTX files
- Web UI: "Write Notes to Deck" button in deck detail view
- API: `POST /api/decks/{id}/write-notes` endpoint
- Automatic timestamped backup before modifying PPTX files

### Changed
- `GET /api/decks/{id}/download` now applies DB notes to the downloaded file
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Implement `write_notes_to_pptx()` and `create_backup()` | `outline2ppt/writeback.py` | — |
| 2 | Add unit tests for writeback module | `tests/test_writeback.py` | 1 |
| 3 | Add `write-notes` CLI subcommand | `outline2ppt/cli.py` | 1 |
| 4 | Add `POST /api/decks/{id}/write-notes` endpoint | `outline2ppt/web/routes.py` | 1 |
| 5 | Update `GET /api/decks/{id}/download` to apply notes | `outline2ppt/web/routes.py` | 1 |
| 6 | Add route tests | `tests/test_web_routes.py` | 4, 5 |
| 7 | Add integration tests (round-trip) | `tests/test_integration.py` | 1 |
| 8 | Add "Write to Deck" button in web UI | `outline2ppt/web/static/index.html` | 4 |
| 9 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** `python-pptx` setting `notes_text_frame.text` replaces all text formatting (bold, italic, etc.) in the notes frame with plain text. This is acceptable — notes are treated as plain text throughout the app, and the original formatted notes are preserved in the backup.
- **Risk:** Accessing `slide.notes_slide` on a slide that has no notes slide will auto-create one in python-pptx. This is the desired behavior when we have notes to write, but we skip slides with empty DB notes to avoid creating unnecessary empty notes frames.
- **Resolved:** Slide count mismatch handling → abort with error. Decks uploaded to the app should not be modified outside the app.
- **Resolved:** Backup location → alongside the original file, timestamped `.bak` suffix.
- **Resolved:** Download behavior → temp copy with notes applied, original untouched.

---

## References

- Depends on: `docs/plans/2026-03-02-web-notes-editing.md` (implemented)
- Related: `outline2ppt/catalog.py` — `catalog_deck()` reads notes from PPTX (this is the reverse)
- Related: `outline2ppt/web/routes.py` — existing download endpoint
- `python-pptx` notes API: `slide.notes_slide.notes_text_frame.text`
- PRD Template: `docs/plans/PRD-TEMPLATE.md`
