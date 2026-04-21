# Web UI Slide Notes Editing — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable editing speaker notes directly in the web UI, with change tracking via the `edit_history` table.

**Architecture:** Add a `record_edit()` helper in `catalog.py` that does read-before-write with history tracking. Update `save_notes_endpoint` to use it and add `updated_at` touch. Add `GET /notes/history` endpoint. Replace the read-only `<pre>` notes display with an editable `<textarea>` with save/cancel, dirty-state tracking, and a history panel.

**Tech Stack:** Python/FastAPI (backend), vanilla JS + Pico CSS (frontend), SQLite (data)

**Scope note:** This PRD edits notes in the **SQLite database only** — writing back to PPTX files is explicitly out of scope. No PPTX backup/atomic-write logic is needed for this feature. The `edit_history` table already exists in `schema.sql`.

---

### Task 1: `record_edit()` helper in catalog.py

**Files:**
- Modify: `outline2ppt/catalog.py` (append new function)
- Test: `tests/test_catalog.py` (append new test class)

**Step 1: Write the failing tests**

Add to `tests/test_catalog.py`:

```python
from outline2ppt.catalog import record_edit

class TestRecordEdit:
    """Tests for the record_edit() catalog helper."""

    def _make_slide(self, tmp_path):
        """Create a DB with one deck + one slide, return (db_path, slide_id)."""
        db_path = str(tmp_path / "test.db")
        conn = get_db(db_path)
        conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
            ("test", "/test.pptx", "abc", 1),
        )
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (1, 1, "Slide 1", "content", "hash1", "original notes"),
        )
        conn.commit()
        conn.close()
        return db_path, 1

    def test_record_edit_writes_history_and_updates_field(self, tmp_path):
        db_path, slide_id = self._make_slide(tmp_path)
        record_edit(slide_id, "notes", "updated notes", source="web", db_path=db_path)

        conn = get_db(db_path)
        # Field updated
        row = conn.execute("SELECT notes, updated_at FROM slides WHERE id = ?", (slide_id,)).fetchone()
        assert row["notes"] == "updated notes"

        # History row written
        hist = conn.execute(
            "SELECT * FROM edit_history WHERE slide_id = ? ORDER BY id", (slide_id,)
        ).fetchall()
        assert len(hist) == 1
        assert hist[0]["field"] == "notes"
        assert hist[0]["old_value"] == "original notes"
        assert hist[0]["new_value"] == "updated notes"
        assert hist[0]["source"] == "web"
        conn.close()

    def test_record_edit_skips_when_value_unchanged(self, tmp_path):
        db_path, slide_id = self._make_slide(tmp_path)
        record_edit(slide_id, "notes", "original notes", source="web", db_path=db_path)

        conn = get_db(db_path)
        count = conn.execute("SELECT COUNT(*) as cnt FROM edit_history").fetchone()["cnt"]
        assert count == 0
        conn.close()

    def test_record_edit_handles_empty_old_value(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = get_db(db_path)
        conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
            ("test", "/test.pptx", "abc", 1),
        )
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (1, 1, "Slide 1", "content", "hash1", ""),
        )
        conn.commit()
        conn.close()

        record_edit(1, "notes", "first notes ever", source="ai", db_path=db_path)

        conn = get_db(db_path)
        hist = conn.execute("SELECT * FROM edit_history WHERE slide_id = 1").fetchone()
        assert hist["old_value"] == ""
        assert hist["new_value"] == "first notes ever"
        assert hist["source"] == "ai"
        conn.close()

    def test_record_edit_updates_timestamp(self, tmp_path):
        db_path, slide_id = self._make_slide(tmp_path)

        conn = get_db(db_path)
        before = conn.execute("SELECT updated_at FROM slides WHERE id = ?", (slide_id,)).fetchone()["updated_at"]
        conn.close()

        import time; time.sleep(0.05)
        record_edit(slide_id, "notes", "new text", source="web", db_path=db_path)

        conn = get_db(db_path)
        after = conn.execute("SELECT updated_at FROM slides WHERE id = ?", (slide_id,)).fetchone()["updated_at"]
        conn.close()
        # updated_at should have changed (or at least not be before the original)
        assert after >= before
```

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_catalog.py::TestRecordEdit -v`
Expected: ImportError — `record_edit` not found in `catalog.py`

**Step 3: Write minimal implementation**

Add to `outline2ppt/catalog.py` (at end of file, before any `if __name__` block):

```python
def record_edit(
    slide_id: int,
    field: str,
    new_value: str,
    *,
    source: str = "web",
    db_path: str = "slides.db",
) -> bool:
    """Update a slide field and record the change in edit_history.

    Returns True if the field was changed, False if value was identical.
    Skips history write and field update when old == new.
    """
    conn = get_db(db_path)
    try:
        row = conn.execute(
            f"SELECT {field} FROM slides WHERE id = ?", (slide_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Slide {slide_id} not found")

        old_value = row[field] or ""
        if old_value == new_value:
            return False

        conn.execute(
            "INSERT INTO edit_history (slide_id, field, old_value, new_value, source) "
            "VALUES (?, ?, ?, ?, ?)",
            (slide_id, field, old_value, new_value, source),
        )
        conn.execute(
            f"UPDATE slides SET {field} = ?, updated_at = datetime('now') WHERE id = ?",
            (new_value, slide_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()
```

Note: `field` is always a hardcoded string from our own code (e.g. `"notes"`), never user input, so the f-string SQL is safe. This pattern mirrors how the codebase already handles column names.

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_catalog.py::TestRecordEdit -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add outline2ppt/catalog.py tests/test_catalog.py
git commit -m "feat: add record_edit() helper for tracked field updates"
```

---

### Task 2: Update `save_notes_endpoint` to use `record_edit()`

**Files:**
- Modify: `outline2ppt/web/routes.py:401-418` (rewrite save_notes_endpoint)
- Modify: `outline2ppt/web/routes.py:10-24` (add `record_edit` to imports)

**Step 1: Write the failing test**

Create `tests/test_web_routes.py`:

```python
"""Tests for web API route handlers."""
import pytest
from fastapi.testclient import TestClient
from pptx import Presentation

from outline2ppt.catalog import catalog_deck, get_db
from outline2ppt.web.app import create_app


@pytest.fixture
def deck_path(tmp_path):
    """Create a minimal PPTX with one slide that has notes."""
    prs = Presentation()
    layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = "Test Slide"
    notes_slide = slide.notes_slide
    notes_slide.notes_text_frame.text = "Original PPTX notes"
    path = str(tmp_path / "test.pptx")
    prs.save(path)
    return path


@pytest.fixture
def client(tmp_path, deck_path):
    """Create a TestClient with a cataloged deck."""
    db_path = str(tmp_path / "test.db")
    uploads_dir = str(tmp_path / "uploads")
    catalog_deck(deck_path, db_path=db_path)
    app = create_app(db_path=db_path, uploads_dir=uploads_dir)
    return TestClient(app)


@pytest.fixture
def db_path(client):
    """Extract db_path from the test client's app state."""
    return client.app.state.db_path


class TestSaveNotesWithHistory:
    """POST /api/slides/{id}/notes/save should record edit history."""

    def test_save_notes_creates_history_row(self, client, db_path):
        resp = client.post("/api/slides/1/notes/save", json={"notes": "New web notes"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        conn = get_db(db_path)
        hist = conn.execute(
            "SELECT * FROM edit_history WHERE slide_id = 1 AND field = 'notes'"
        ).fetchall()
        assert len(hist) == 1
        assert hist[0]["old_value"] == "Original PPTX notes"
        assert hist[0]["new_value"] == "New web notes"
        assert hist[0]["source"] == "web"
        conn.close()

    def test_save_notes_updates_slide_notes(self, client, db_path):
        client.post("/api/slides/1/notes/save", json={"notes": "Updated notes"})
        conn = get_db(db_path)
        row = conn.execute("SELECT notes FROM slides WHERE id = 1").fetchone()
        assert row["notes"] == "Updated notes"
        conn.close()

    def test_save_notes_updates_timestamp(self, client, db_path):
        conn = get_db(db_path)
        before = conn.execute("SELECT updated_at FROM slides WHERE id = 1").fetchone()["updated_at"]
        conn.close()

        client.post("/api/slides/1/notes/save", json={"notes": "Timestamped notes"})

        conn = get_db(db_path)
        after = conn.execute("SELECT updated_at FROM slides WHERE id = 1").fetchone()["updated_at"]
        conn.close()
        assert after >= before


class TestSaveNotesSameValue:
    """Saving identical notes should not create a history row."""

    def test_no_history_for_same_value(self, client, db_path):
        resp = client.post(
            "/api/slides/1/notes/save",
            json={"notes": "Original PPTX notes"},
        )
        assert resp.status_code == 200

        conn = get_db(db_path)
        count = conn.execute("SELECT COUNT(*) as cnt FROM edit_history").fetchone()["cnt"]
        assert count == 0
        conn.close()


class TestSaveNotesValidation:
    """Edge cases for notes save endpoint."""

    def test_empty_notes_rejected(self, client):
        resp = client.post("/api/slides/1/notes/save", json={"notes": ""})
        assert resp.status_code == 400

    def test_missing_slide_404(self, client):
        resp = client.post("/api/slides/9999/notes/save", json={"notes": "test"})
        assert resp.status_code == 404
```

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_web_routes.py -v`
Expected: `test_save_notes_creates_history_row` FAILS (no history row written)

**Step 3: Update the endpoint**

In `outline2ppt/web/routes.py`, add `record_edit` to the imports from `catalog`:

```python
from outline2ppt.catalog import (
    get_db,
    search_slides,
    add_tags,
    get_slide_tags,
    remove_slide_tag,
    list_taxonomy,
    add_taxonomy_tags,
    remove_taxonomy_tag,
    import_taxonomy_csv,
    export_taxonomy_csv,
    rename_tag,
    catalog_deck,
    get_deck_by_id,
    record_edit,
)
```

Replace the `save_notes_endpoint` (lines 401–418):

```python
@router.post("/api/slides/{slide_id}/notes/save")
async def save_notes_endpoint(slide_id: int, request: Request):
    """API: Save notes to the slide record with edit-history tracking."""
    db_path = request.app.state.db_path
    body = await request.json()
    notes = body.get("notes", "").strip()
    source = body.get("source", "web")
    if not notes:
        return JSONResponse({"error": "notes is required"}, status_code=400)

    try:
        changed = record_edit(slide_id, "notes", notes, source=source, db_path=db_path)
    except ValueError:
        return JSONResponse({"error": "Slide not found"}, status_code=404)

    return {"status": "ok", "changed": changed}
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_web_routes.py -v`
Expected: All tests PASS

**Step 5: Run full test suite to check for regressions**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All existing tests still PASS

**Step 6: Commit**

```bash
git add outline2ppt/web/routes.py tests/test_web_routes.py
git commit -m "feat: save_notes_endpoint writes edit history and updates timestamp"
```

---

### Task 3: Add `GET /api/slides/{id}/notes/history` endpoint

**Files:**
- Modify: `outline2ppt/web/routes.py` (add new endpoint after save_notes_endpoint)
- Modify: `tests/test_web_routes.py` (add test classes)

**Step 1: Write the failing tests**

Add to `tests/test_web_routes.py`:

```python
class TestNotesHistory:
    """GET /api/slides/{id}/notes/history returns edit history."""

    def test_history_returns_entries_reverse_chronological(self, client, db_path):
        # Create two edits
        client.post("/api/slides/1/notes/save", json={"notes": "Edit 1"})
        client.post("/api/slides/1/notes/save", json={"notes": "Edit 2"})

        resp = client.get("/api/slides/1/notes/history")
        assert resp.status_code == 200
        entries = resp.json()["history"]
        assert len(entries) == 2
        # Newest first
        assert entries[0]["new_value"] == "Edit 2"
        assert entries[0]["old_value"] == "Edit 1"
        assert entries[1]["new_value"] == "Edit 1"
        assert entries[1]["old_value"] == "Original PPTX notes"

    def test_history_includes_source_and_timestamp(self, client, db_path):
        client.post("/api/slides/1/notes/save", json={"notes": "Web edit"})
        resp = client.get("/api/slides/1/notes/history")
        entry = resp.json()["history"][0]
        assert entry["source"] == "web"
        assert "created_at" in entry


class TestNotesHistoryEmpty:
    """GET /api/slides/{id}/notes/history with no edits."""

    def test_empty_history(self, client):
        resp = client.get("/api/slides/1/notes/history")
        assert resp.status_code == 200
        assert resp.json()["history"] == []

    def test_history_missing_slide_404(self, client):
        resp = client.get("/api/slides/9999/notes/history")
        assert resp.status_code == 404
```

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_web_routes.py::TestNotesHistory -v`
Expected: 404 — endpoint doesn't exist

**Step 3: Add the endpoint**

Add to `outline2ppt/web/routes.py`, after `save_notes_endpoint`:

```python
@router.get("/api/slides/{slide_id}/notes/history")
async def notes_history_endpoint(slide_id: int, request: Request):
    """API: Return edit history for a slide's notes field, newest first."""
    db_path = request.app.state.db_path
    conn = get_db(db_path)
    row = conn.execute("SELECT id FROM slides WHERE id = ?", (slide_id,)).fetchone()
    if not row:
        conn.close()
        return JSONResponse({"error": "Slide not found"}, status_code=404)

    rows = conn.execute(
        "SELECT old_value, new_value, source, created_at FROM edit_history "
        "WHERE slide_id = ? AND field = 'notes' ORDER BY id DESC",
        (slide_id,),
    ).fetchall()
    conn.close()

    history = [
        {
            "old_value": r["old_value"],
            "new_value": r["new_value"],
            "source": r["source"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {"history": history}
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_web_routes.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add outline2ppt/web/routes.py tests/test_web_routes.py
git commit -m "feat: add GET /api/slides/{id}/notes/history endpoint"
```

---

### Task 4: Update AI notes save to include `source='ai'` in history

**Files:**
- Modify: `outline2ppt/web/static/index.html` (update `saveNotes()` to send `source`)

**Step 1: Write the failing test**

Add to `tests/test_web_routes.py`:

```python
class TestSaveNotesSource:
    """Verify source field is passed through correctly."""

    def test_ai_source_recorded(self, client, db_path):
        resp = client.post(
            "/api/slides/1/notes/save",
            json={"notes": "AI generated notes", "source": "ai"},
        )
        assert resp.status_code == 200

        conn = get_db(db_path)
        hist = conn.execute(
            "SELECT source FROM edit_history WHERE slide_id = 1"
        ).fetchone()
        assert hist["source"] == "ai"
        conn.close()

    def test_default_source_is_web(self, client, db_path):
        client.post("/api/slides/1/notes/save", json={"notes": "Manual edit"})
        conn = get_db(db_path)
        hist = conn.execute(
            "SELECT source FROM edit_history WHERE slide_id = 1"
        ).fetchone()
        assert hist["source"] == "web"
        conn.close()
```

**Step 2: Run tests — these should already pass**

The backend already accepts `source` from the request body (implemented in Task 2). These tests validate that.

Run: `venv/bin/python -m pytest tests/test_web_routes.py::TestSaveNotesSource -v`
Expected: PASS

**Step 3: Update the frontend `saveNotes()` to send `source: 'ai'`**

In `outline2ppt/web/static/index.html`, the `saveNotes()` function (line ~886) currently sends `{notes: lastNotesText}`. It's called only from the AI "Save to Slide Notes" button, so it should send `source: 'ai'`:

```javascript
async function saveNotes() {
    if (!currentSlideId || !lastNotesText) return;
    const resp = await fetch(`/api/slides/${currentSlideId}/notes/save`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({notes: lastNotesText, source: 'ai'}),
    });
    if (resp.ok) {
        document.getElementById('detail-notes').textContent = lastNotesText;
        savedNotesValue = lastNotesText;
        updateNotesDirtyState();
        document.getElementById('save-notes-btn').classList.add('hidden');
        toast('Notes saved');
    } else {
        const data = await resp.json().catch(() => ({}));
        toast(`Error saving notes: ${data.error || 'unknown error'}`);
    }
}
```

(The `savedNotesValue` and `updateNotesDirtyState()` references will be implemented in Task 5.)

**Step 4: Commit**

```bash
git add tests/test_web_routes.py outline2ppt/web/static/index.html
git commit -m "feat: pass source='ai' when saving AI-generated notes"
```

---

### Task 5: Replace static notes display with editable textarea + save/cancel

**Files:**
- Modify: `outline2ppt/web/static/index.html:394-397` (notes section HTML)
- Modify: `outline2ppt/web/static/index.html` (JS: new functions, updated `showSlideDetail`, `closeSlideDialog`)

**Step 1: Replace the notes HTML**

Replace the `<details>` block (lines 394-397) with an always-visible editable notes section:

```html
<div style="margin-top:1rem;">
    <div style="display:flex; align-items:center; justify-content:space-between;">
        <strong>Speaker Notes</strong>
        <button class="outline" id="notes-history-btn" onclick="toggleNotesHistory()" style="width:auto; padding:0.2rem 0.6rem; font-size:0.75rem;">History</button>
    </div>
    <div id="notes-history-panel" class="hidden" style="margin-top:0.5rem; margin-bottom:0.5rem; max-height:200px; overflow-y:auto; border:1px solid var(--pico-muted-border-color); border-radius:4px; padding:0.5rem; font-size:0.8rem;"></div>
    <textarea id="detail-notes" rows="5" style="width:100%; font-size:0.85rem; margin-top:0.5rem; resize:vertical;" oninput="updateNotesDirtyState()"></textarea>
    <div style="display:flex; justify-content:flex-end; gap:0.5rem; margin-top:0.25rem;">
        <button class="outline" id="notes-cancel-btn" onclick="cancelNotesEdit()" style="width:auto; padding:0.3rem 0.7rem; font-size:0.8rem;" disabled>Cancel</button>
        <button id="notes-save-btn" onclick="saveEditedNotes()" style="width:auto; padding:0.3rem 0.7rem; font-size:0.8rem;" disabled>Save Notes</button>
    </div>
</div>
```

**Step 2: Add JS state variables and functions**

Add near the top of the `<script>` block (after `let currentSlideId = null;`):

```javascript
let savedNotesValue = '';
```

**Step 3: Update `showSlideDetail()` to populate textarea**

Replace the line:
```javascript
document.getElementById('detail-notes').textContent = slide.notes || 'No notes';
```
With:
```javascript
savedNotesValue = slide.notes || '';
document.getElementById('detail-notes').value = savedNotesValue;
updateNotesDirtyState();
// Hide history panel when opening a new slide
document.getElementById('notes-history-panel').classList.add('hidden');
```

**Step 4: Add notes editing functions**

Add to the `<script>` block:

```javascript
function updateNotesDirtyState() {
    const textarea = document.getElementById('detail-notes');
    const isDirty = textarea.value !== savedNotesValue;
    document.getElementById('notes-save-btn').disabled = !isDirty;
    document.getElementById('notes-cancel-btn').disabled = !isDirty;
    // Visual indicator: border color
    textarea.style.borderColor = isDirty ? 'var(--pico-primary)' : '';
}

function cancelNotesEdit() {
    document.getElementById('detail-notes').value = savedNotesValue;
    updateNotesDirtyState();
}

async function saveEditedNotes() {
    if (!currentSlideId) return;
    const notes = document.getElementById('detail-notes').value.trim();
    if (!notes) { toast('Notes cannot be empty'); return; }

    const resp = await fetch(`/api/slides/${currentSlideId}/notes/save`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({notes: notes, source: 'web'}),
    });
    if (resp.ok) {
        savedNotesValue = notes;
        updateNotesDirtyState();
        toast('Notes saved');
    } else {
        const data = await resp.json().catch(() => ({}));
        toast(`Error saving notes: ${data.error || 'unknown error'}`);
    }
}
```

**Step 5: Update `closeSlideDialog()` with unsaved-changes guard**

Replace `closeSlideDialog`:

```javascript
function closeSlideDialog() {
    const textarea = document.getElementById('detail-notes');
    if (textarea && textarea.value !== savedNotesValue) {
        if (!confirm('You have unsaved notes changes. Discard them?')) return;
    }
    document.getElementById('slide-dialog').close();
    resetAiPanel();
}
```

**Step 6: Update `saveNotes()` (AI save) to sync with new state**

The existing `saveNotes()` function (for AI-generated notes) should also update `savedNotesValue`:

```javascript
async function saveNotes() {
    if (!currentSlideId || !lastNotesText) return;
    const resp = await fetch(`/api/slides/${currentSlideId}/notes/save`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({notes: lastNotesText, source: 'ai'}),
    });
    if (resp.ok) {
        savedNotesValue = lastNotesText;
        document.getElementById('detail-notes').value = lastNotesText;
        updateNotesDirtyState();
        document.getElementById('save-notes-btn').classList.add('hidden');
        toast('Notes saved');
    } else {
        const data = await resp.json().catch(() => ({}));
        toast(`Error saving notes: ${data.error || 'unknown error'}`);
    }
}
```

**Step 7: Add keyboard shortcut (Ctrl+S / Cmd+S)**

Add to the `<script>` block:

```javascript
document.getElementById('slide-dialog').addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        const saveBtn = document.getElementById('notes-save-btn');
        if (!saveBtn.disabled) {
            e.preventDefault();
            saveEditedNotes();
        }
    }
});
```

**Step 8: Commit**

```bash
git add outline2ppt/web/static/index.html
git commit -m "feat: editable notes textarea with save/cancel and dirty-state tracking"
```

---

### Task 6: Add history panel UI

**Files:**
- Modify: `outline2ppt/web/static/index.html` (add `toggleNotesHistory()` function)

**Step 1: Add the `toggleNotesHistory()` function**

Add to the `<script>` block:

```javascript
async function toggleNotesHistory() {
    const panel = document.getElementById('notes-history-panel');
    if (!panel.classList.contains('hidden')) {
        panel.classList.add('hidden');
        return;
    }
    if (!currentSlideId) return;

    panel.innerHTML = '<em>Loading...</em>';
    panel.classList.remove('hidden');

    const resp = await fetch(`/api/slides/${currentSlideId}/notes/history`);
    if (!resp.ok) {
        panel.innerHTML = '<em>Error loading history</em>';
        return;
    }
    const data = await resp.json();
    if (data.history.length === 0) {
        panel.innerHTML = '<em>No edit history</em>';
        return;
    }

    panel.innerHTML = data.history.map(h => {
        const date = h.created_at || 'Unknown date';
        const source = esc(h.source || 'unknown');
        const text = esc(h.new_value || '(empty)');
        // Truncate long values for display
        const preview = text.length > 200 ? text.slice(0, 200) + '...' : text;
        return `<div style="margin-bottom:0.5rem; padding-bottom:0.5rem; border-bottom:1px solid var(--pico-muted-border-color);">` +
            `<div style="font-size:0.75rem; color:var(--pico-muted-color);">${esc(date)} (${source})</div>` +
            `<div style="white-space:pre-wrap; margin-top:0.2rem;">${preview}</div>` +
            `</div>`;
    }).join('');
}
```

**Step 2: Add CSS for hidden class if not already present**

The `.hidden` class should already exist (used by `save-notes-btn`). Verify the existing CSS rule `#save-notes-btn.hidden { display: none !important; }` — we need a general `.hidden` rule. Check if one exists; if not, add:

```css
.hidden { display: none !important; }
```

**Step 3: Commit**

```bash
git add outline2ppt/web/static/index.html
git commit -m "feat: add notes history panel with toggle"
```

---

### Task 7: Integration tests

**Files:**
- Modify: `tests/test_integration.py` (add notes editing integration tests)

**Step 1: Write integration tests**

Add to `tests/test_integration.py`:

```python
class TestNotesEditingIntegration:
    """Integration tests for notes editing via the web API."""

    @pytest.fixture
    def notes_deck(self, tmp_path):
        """Create a PPTX with notes on the first slide."""
        prs = Presentation()
        layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = "Notes Test Slide"
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = "Initial notes from PPTX"
        path = str(tmp_path / "notes_deck.pptx")
        prs.save(path)
        return path

    @pytest.fixture
    def client(self, tmp_path, notes_deck):
        from fastapi.testclient import TestClient
        from outline2ppt.web.app import create_app

        db_path = str(tmp_path / "notes.db")
        uploads_dir = str(tmp_path / "uploads")
        catalog_deck(notes_deck, db_path=db_path)
        app = create_app(db_path=db_path, uploads_dir=uploads_dir)
        return TestClient(app)

    @pytest.fixture
    def db_path(self, client):
        return client.app.state.db_path

    def test_save_creates_history_row(self, client, db_path):
        resp = client.post("/api/slides/1/notes/save", json={"notes": "Edited"})
        assert resp.status_code == 200

        conn = get_db(db_path)
        hist = conn.execute(
            "SELECT * FROM edit_history WHERE slide_id = 1"
        ).fetchone()
        assert hist is not None
        assert hist["old_value"] == "Initial notes from PPTX"
        assert hist["new_value"] == "Edited"
        conn.close()

    def test_two_saves_create_chain(self, client, db_path):
        client.post("/api/slides/1/notes/save", json={"notes": "Edit 1"})
        client.post("/api/slides/1/notes/save", json={"notes": "Edit 2"})

        conn = get_db(db_path)
        rows = conn.execute(
            "SELECT old_value, new_value FROM edit_history WHERE slide_id = 1 ORDER BY id"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["old_value"] == "Initial notes from PPTX"
        assert rows[0]["new_value"] == "Edit 1"
        assert rows[1]["old_value"] == "Edit 1"
        assert rows[1]["new_value"] == "Edit 2"
        conn.close()

    def test_history_api_returns_correct_order(self, client, db_path):
        client.post("/api/slides/1/notes/save", json={"notes": "First edit"})
        client.post("/api/slides/1/notes/save", json={"notes": "Second edit"})

        resp = client.get("/api/slides/1/notes/history")
        assert resp.status_code == 200
        history = resp.json()["history"]
        assert len(history) == 2
        # Newest first
        assert history[0]["new_value"] == "Second edit"
        assert history[1]["new_value"] == "First edit"

    def test_updated_at_changes_on_save(self, client, db_path):
        conn = get_db(db_path)
        before = conn.execute(
            "SELECT updated_at FROM slides WHERE id = 1"
        ).fetchone()["updated_at"]
        conn.close()

        client.post("/api/slides/1/notes/save", json={"notes": "Timestamp test"})

        conn = get_db(db_path)
        after = conn.execute(
            "SELECT updated_at FROM slides WHERE id = 1"
        ).fetchone()["updated_at"]
        conn.close()
        assert after >= before
```

**Step 2: Run integration tests**

Run: `venv/bin/python -m pytest tests/test_integration.py::TestNotesEditingIntegration -v`
Expected: All PASS

**Step 3: Run full suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration tests for notes editing and history"
```

---

### Task 8: Update CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add changelog entry**

Add under the appropriate version heading (or `## [Unreleased]`):

```markdown
### Added
- Web UI: Editable speaker notes in slide detail modal with save/cancel controls
- Web UI: Dirty-state indicator and unsaved-changes guard for notes editing
- Web UI: Notes edit history panel showing previous versions with timestamps
- Web UI: Ctrl+S / Cmd+S keyboard shortcut to save notes
- API: `GET /api/slides/{id}/notes/history` endpoint
- Database: Edit history tracking for notes changes (via `edit_history` table)

### Changed
- `POST /api/slides/{id}/notes/save` now records previous value in edit history before overwriting
- `POST /api/slides/{id}/notes/save` now updates `updated_at` timestamp
- AI-generated notes saves now recorded with `source: 'ai'` in edit history
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for web notes editing feature"
```

---

## Task Dependency Graph

```
Task 1 (record_edit helper)
  ├── Task 2 (update save_notes_endpoint) ── Task 4 (AI source='ai')
  │     └── Task 5 (editable textarea + save/cancel)
  └── Task 3 (GET history endpoint)
        └── Task 6 (history panel UI)

Task 7 (integration tests) depends on Tasks 2 + 3
Task 8 (changelog) depends on all
```

## Summary of Changes

| File | Type | What |
|------|------|------|
| `outline2ppt/catalog.py` | Modified | Add `record_edit()` helper |
| `outline2ppt/web/routes.py` | Modified | Rewrite `save_notes_endpoint`, add `notes_history_endpoint` |
| `outline2ppt/web/static/index.html` | Modified | Editable textarea, save/cancel, dirty state, history panel, keyboard shortcut |
| `tests/test_catalog.py` | Modified | Add `TestRecordEdit` class |
| `tests/test_web_routes.py` | Created | Notes save + history endpoint tests |
| `tests/test_integration.py` | Modified | Add `TestNotesEditingIntegration` class |
| `CHANGELOG.md` | Modified | Feature changelog entry |

---

### Task 9: Create follow-up PRD stub for PPTX notes write-back

This PRD only edits notes in the **SQLite database**. To complete the full user workflow, a follow-up PRD is needed to write edited notes back to the PPTX file. That PRD should cover:

- Safe/atomic writes to PPTX files (temp file + rename pattern)
- Backup copies of decks before modification
- `python-pptx` write operations for notes
- UI trigger (e.g. "Export to Deck" button or automatic on save)
- Handling the case where the PPTX source file has moved or been deleted

**Step 1: Create the stub PRD**

Create `docs/plans/2026-03-02-pptx-notes-writeback.md` with a brief outline of the above concerns, referencing this PRD as a dependency.

**Step 2: Commit**

```bash
git add docs/plans/2026-03-02-pptx-notes-writeback.md
git commit -m "docs: add stub PRD for PPTX notes write-back (follow-up to web notes editing)"
```
