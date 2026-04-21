# PRD: Web UI Slide Notes Editing

**Date:** 2026-03-02
**Author:** Matt
**Status:** Draft

---

## Summary

Enable editing of slide speaker notes directly in the web UI, with change tracking via the `edit_history` table. This is the first web editing capability beyond AI-generated notes, establishing the pattern for future field-level editing (title, tags, etc.).

## Motivation

- **What problem does this solve?** The web UI can generate AI speaker notes and save them (`POST /api/slides/{id}/notes/save`), but users cannot manually write or edit notes. The only way to add custom notes is through PowerPoint or the CLI. The save endpoint also silently overwrites previous notes with no undo.
- **Who benefits?** Users who review slides in the web UI and want to add presentation-specific notes, correct AI-generated notes, or append context without leaving the browser.
- **What happens if we don't do this?** The web UI remains a read-mostly interface for notes. Users must switch to PowerPoint to edit notes, then re-catalog to see changes — a workflow that discourages iterative refinement.

## Requirements

### Must Have

- [ ] Editable notes text area in the slide detail modal
- [ ] Save button that persists edited notes to the database
- [ ] Edit history: previous notes value recorded in `edit_history` table before overwrite
- [ ] Visual indicator when notes have unsaved changes (dirty state)
- [ ] Confirmation if user navigates away with unsaved changes
- [ ] `updated_at` timestamp refreshed on save
- [ ] API: `GET /api/slides/{id}/notes/history` endpoint to retrieve edit history for a slide's notes

### Nice to Have

- [ ] Undo: restore previous notes from edit history via UI button
- [ ] Diff view: show what changed between current and previous notes
- [ ] Keyboard shortcut (Ctrl+S / Cmd+S) to save notes
- [ ] Auto-save draft to localStorage (recover from accidental close)

### Out of Scope

- Editing slide title or content text (future PRD)
- Writing notes back to the PPTX file (requires python-pptx write + re-export)
- Collaborative editing / conflict resolution
- Markdown rendering of notes (notes are plain text in PowerPoint)

---

## Design

### Approach

The existing `POST /api/slides/{id}/notes/save` endpoint already handles the write. The changes are:

1. **Backend:** Add a `read-before-write` step to the save endpoint — fetch current notes, write an `edit_history` row with old/new values, then update the slide. Add a history read endpoint.
2. **Frontend:** Replace the read-only notes display in the slide detail modal with an editable `<textarea>`. Add save/cancel controls and dirty-state tracking.

The edit flow is intentionally simple: edit, save, done. No drafts, no locking, no real-time sync. This matches the single-user nature of the app.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/web/routes.py` | Modified | Update `save_notes_endpoint` to write edit history; add `GET /api/slides/{id}/notes/history` |
| `outline2ppt/web/static/index.html` | Modified | Add editable textarea, save/cancel buttons, dirty-state indicator to slide detail modal |
| `outline2ppt/catalog.py` | Modified | Add `record_edit()` helper function for writing to `edit_history` |

### Data Model Changes

No schema changes — this PRD depends on the `edit_history` table from the Data Model v2 PRD (`docs/plans/2026-03-02-data-model-v2.md`). The table is:

```sql
CREATE TABLE IF NOT EXISTS edit_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slide_id INTEGER NOT NULL REFERENCES slides(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    source TEXT NOT NULL DEFAULT 'web',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

For notes editing, rows are written with `field = 'notes'` and `source = 'web'`.

---

## CLI Changes

No CLI changes.

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Slide Detail Modal | Editable notes area | Replace static notes text with `<textarea>`, add Save/Cancel buttons |
| Slide Detail Modal | Dirty indicator | Visual cue (e.g., dot on Save button, border color change) when notes differ from saved value |
| Slide Detail Modal | History link | Small "History" link below notes area, opens history panel |

### New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/slides/{slide_id}/notes/history` | Returns list of edit history entries for notes field, newest first |

### Modified API Endpoints

| Method | Path | Change |
|--------|------|--------|
| POST | `/api/slides/{slide_id}/notes/save` | Now writes `edit_history` row before updating notes |

### Wireframe / Mockup

**Slide detail modal — notes section (view mode → edit mode):**

```
┌─────────────────────────────────────────────────┐
│  Slide 3: Key Metrics                           │
│  ─────────────────────────────────────────────  │
│  Author: J. Smith    Created: 2026-01-15        │
│  Layout: two_column  Updated: 2026-02-20 14:32  │
│  ─────────────────────────────────────────────  │
│  [slide image]                                  │
│                                                 │
│  Speaker Notes                        [History] │
│  ┌─────────────────────────────────────────┐    │
│  │ This slide shows Q4 revenue trends.     │    │
│  │ Key talking point: 23% YoY growth was   │    │
│  │ driven primarily by enterprise segment. │    │
│  │                                         │    │
│  │                                         │    │
│  └─────────────────────────────────────────┘    │
│                         [Cancel]  [Save Notes]  │
│                                                 │
│  Tags: revenue, metrics, quarterly              │
└─────────────────────────────────────────────────┘
```

**History panel (shown on click):**

```
┌──────────────────────────────────────────┐
│  Notes History                    [Close]│
│  ────────────────────────────────────── │
│  2026-02-20 14:32 (web)                 │
│  "This slide shows Q4 revenue trends.   │
│   Key talking point: 23% YoY growth..." │
│                                         │
│  2026-02-18 09:15 (ai)                  │
│  "The Q4 metrics dashboard presents..." │
│                                         │
│  2026-02-15 11:00 (ingest)              │
│  ""  (empty — no notes in PPTX)         │
└──────────────────────────────────────────┘
```

Notes area behavior:
- On modal open, notes text is loaded into a `<textarea>` (always editable, no toggle needed)
- Save button is disabled until content differs from the saved value
- Cancel resets textarea to saved value
- After successful save, saved value is updated and Save button disables
- Navigate away with unsaved changes → browser `beforeunload` or modal close confirmation

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_catalog.py` | `TestRecordEdit` | `record_edit()` writes correct row to `edit_history` |
| `tests/test_catalog.py` | `TestRecordEditNullOld` | First-time edit (old_value is empty string) recorded correctly |
| `tests/test_web_routes.py` | `TestSaveNotesWithHistory` | `POST /notes/save` creates history row with correct old/new values |
| `tests/test_web_routes.py` | `TestSaveNotesSameValue` | Saving identical notes does not create history row |
| `tests/test_web_routes.py` | `TestNotesHistory` | `GET /notes/history` returns entries in reverse chronological order |
| `tests/test_web_routes.py` | `TestNotesHistoryEmpty` | `GET /notes/history` returns empty list for slide with no edits |

### Integration Tests

Add to `tests/test_integration.py`:
- Save notes via API, verify `edit_history` row created with correct values
- Save notes twice, verify two history rows with correct old/new chains
- Fetch history via API, verify order and content
- Verify `updated_at` changes after notes save

### Manual Testing

1. Open slide detail modal — notes area is editable, Save button is disabled
2. Type in notes area — Save button enables, visual dirty indicator appears
3. Click Save — toast confirms save, Save button disables, dirty indicator clears
4. Click History — panel shows previous values with timestamps and sources
5. Edit notes, then click Cancel — text reverts to saved value
6. Edit notes, then close modal — confirmation prompt appears
7. Generate AI notes, then manually edit — history shows both the AI-generated and manual versions

---

## Changelog Entry

```markdown
### Added
- Web UI: Editable speaker notes in slide detail modal with save/cancel controls
- Web UI: Notes edit history panel showing previous versions with timestamps
- API: `GET /api/slides/{id}/notes/history` endpoint
- Database: Edit history tracking for notes changes (via `edit_history` table)

### Changed
- `POST /api/slides/{id}/notes/save` now records previous value in edit history before overwriting
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Implement `record_edit()` helper in catalog.py | `catalog.py` | Data Model v2 PRD (edit_history table exists) |
| 2 | Update `save_notes_endpoint` to read-before-write with history | `routes.py` | 1 |
| 3 | Add `GET /api/slides/{id}/notes/history` endpoint | `routes.py` | 1 |
| 4 | Replace static notes display with editable textarea + save/cancel | `index.html` | 2 |
| 5 | Add dirty-state tracking and navigation guard | `index.html` | 4 |
| 6 | Add history panel UI | `index.html` | 3 |
| 7 | Add unit tests for `record_edit()` and endpoints | `tests/test_catalog.py`, `tests/test_web_routes.py` | 2, 3 |
| 8 | Add integration tests | `tests/test_integration.py` | 2, 3 |
| 9 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Saving notes does not write back to the PPTX file — the DB and source file can diverge. This is acceptable: the DB is the live working copy; the PPTX is the archival original. A future "export to PPTX" feature could write DB notes back to the file.
- **Risk:** No conflict handling if the same slide is open in two browser tabs — mitigate with last-write-wins (acceptable for single-user app). The edit history preserves both writes regardless.
- **Risk:** `edit_history` stores full text for both old and new values, which could be large for verbose notes — acceptable at current scale. Notes are typically a few hundred characters.
- **Question:** Should the AI notes generation endpoints (`/notes`, `/notes/save`) also write to `edit_history`? — **Yes**, with `source = 'ai'`. This means the history shows the full provenance: ingest → AI generation → manual edit.
- **Question:** Should `Cancel` in the textarea undo to the last saved value, or to the value when the modal opened? — Recommend last saved value (simpler, matches user expectation of "discard my changes").

---

## References

- Depends on: `docs/plans/2026-03-02-data-model-v2.md` (edit_history table)
- Related PRDs: `docs/plans/2026-02-26-slide-metadata.md` (author/dates displayed in modal)
- Existing endpoint: `outline2ppt/web/routes.py:save_notes_endpoint()`
- Existing UI: `outline2ppt/web/static/index.html` (slide detail modal)
- PRD Template: `docs/plans/PRD-TEMPLATE.md`
