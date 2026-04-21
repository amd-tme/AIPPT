# PPTX Notes Write-Back Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Write edited speaker notes from the SQLite database back to PPTX files, completing the round-trip from ingest → edit → export.

**Architecture:** A new `outline2ppt/writeback.py` module provides `write_notes_to_pptx()` and `create_backup()`. Three callers: CLI `write-notes` command (backup + in-place write), web `POST /api/decks/{id}/write-notes` (backup + in-place write), web `GET /api/decks/{id}/download` (temp copy with notes applied). Slide matching is by position. Slide count mismatches abort with an error.

**Tech Stack:** python-pptx (already installed), shutil (stdlib), FastAPI (existing web framework)

**PRD:** `docs/plans/2026-03-02-pptx-notes-writeback.md`

---

### Task 1: Core writeback module — tests

**Files:**
- Create: `tests/test_writeback.py`
- Create: `outline2ppt/writeback.py` (empty stub for imports)

**Step 1: Create empty writeback module**

Create `outline2ppt/writeback.py` with stubs so tests can import:

```python
"""Write speaker notes from DB back to PPTX files."""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class WritebackResult:
    deck_id: int
    slides_written: int = 0
    slides_skipped: int = 0
    slides_total: int = 0
    backup_path: Optional[str] = None
    warnings: list = field(default_factory=list)


def write_notes_to_pptx(
    deck_path: str,
    db_path: str = "slides.db",
    deck_id: Optional[int] = None,
    output_path: Optional[str] = None,
) -> WritebackResult:
    raise NotImplementedError


def create_backup(deck_path: str) -> str:
    raise NotImplementedError
```

**Step 2: Write failing tests**

Create `tests/test_writeback.py`:

```python
"""Tests for PPTX notes write-back."""
import os

import pytest
from pptx import Presentation

from outline2ppt.catalog import catalog_deck, get_db, record_edit
from outline2ppt.writeback import write_notes_to_pptx, create_backup, WritebackResult


@pytest.fixture
def deck_with_notes(tmp_path):
    """Create a 3-slide PPTX where slide 1 has notes, slides 2-3 don't."""
    prs = Presentation()
    layout = prs.slide_layouts[0]

    s1 = prs.slides.add_slide(layout)
    s1.shapes.title.text = "Slide One"
    s1.notes_slide.notes_text_frame.text = "Original notes 1"

    s2 = prs.slides.add_slide(layout)
    s2.shapes.title.text = "Slide Two"
    # no notes

    s3 = prs.slides.add_slide(layout)
    s3.shapes.title.text = "Slide Three"
    # no notes

    path = str(tmp_path / "deck.pptx")
    prs.save(path)
    return path


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def cataloged(deck_with_notes, db_path):
    """Catalog the deck and return (deck_id, deck_path, db_path)."""
    deck_id = catalog_deck(deck_with_notes, db_path=db_path)
    return deck_id, deck_with_notes, db_path


class TestWriteNotesToPptx:
    def test_writes_edited_notes(self, cataloged):
        deck_id, deck_path, db_path = cataloged
        record_edit(1, "notes", "Edited notes for slide 1", source="web", db_path=db_path)

        result = write_notes_to_pptx(deck_path, db_path=db_path, deck_id=deck_id)

        assert isinstance(result, WritebackResult)
        assert result.deck_id == deck_id
        assert result.slides_written == 1
        assert result.slides_total == 3

        # Verify PPTX was modified
        prs = Presentation(deck_path)
        assert prs.slides[0].notes_slide.notes_text_frame.text == "Edited notes for slide 1"

    def test_skips_empty_notes(self, cataloged):
        deck_id, deck_path, db_path = cataloged
        # Slides 2 and 3 have empty notes in DB — should be skipped
        result = write_notes_to_pptx(deck_path, db_path=db_path, deck_id=deck_id)

        assert result.slides_written == 1  # only slide 1 has notes
        assert result.slides_skipped == 2

    def test_creates_notes_frame_when_missing(self, cataloged):
        deck_id, deck_path, db_path = cataloged
        # Edit notes for slide 2 which has no notes frame
        record_edit(2, "notes", "New notes for slide 2", source="web", db_path=db_path)

        write_notes_to_pptx(deck_path, db_path=db_path, deck_id=deck_id)

        prs = Presentation(deck_path)
        assert prs.slides[1].notes_slide.notes_text_frame.text == "New notes for slide 2"

    def test_output_path_leaves_original_untouched(self, cataloged, tmp_path):
        deck_id, deck_path, db_path = cataloged
        record_edit(1, "notes", "Modified notes", source="web", db_path=db_path)
        output = str(tmp_path / "copy.pptx")

        result = write_notes_to_pptx(deck_path, db_path=db_path, deck_id=deck_id, output_path=output)

        # Output file has new notes
        prs_out = Presentation(output)
        assert prs_out.slides[0].notes_slide.notes_text_frame.text == "Modified notes"

        # Original still has old notes
        prs_orig = Presentation(deck_path)
        assert prs_orig.slides[0].notes_slide.notes_text_frame.text == "Original notes 1"

    def test_lookup_by_file_path(self, cataloged):
        deck_id, deck_path, db_path = cataloged
        record_edit(1, "notes", "Via path lookup", source="web", db_path=db_path)

        # No deck_id — should find by file_path
        result = write_notes_to_pptx(deck_path, db_path=db_path)

        assert result.deck_id == deck_id
        assert result.slides_written == 1


class TestWritebackErrors:
    def test_file_not_found(self, db_path):
        with pytest.raises(FileNotFoundError):
            write_notes_to_pptx("/nonexistent/deck.pptx", db_path=db_path)

    def test_deck_not_in_db(self, deck_with_notes, db_path):
        # deck exists on disk but hasn't been cataloged
        with pytest.raises(ValueError, match="not found in database"):
            write_notes_to_pptx(deck_with_notes, db_path=db_path)

    def test_slide_count_mismatch(self, cataloged, tmp_path):
        deck_id, deck_path, db_path = cataloged
        # Add a slide to the PPTX (making it 4 slides vs 3 in DB)
        prs = Presentation(deck_path)
        prs.slides.add_slide(prs.slide_layouts[0])
        prs.save(deck_path)

        with pytest.raises(ValueError, match="Slide count mismatch"):
            write_notes_to_pptx(deck_path, db_path=db_path, deck_id=deck_id)


class TestCreateBackup:
    def test_creates_bak_file(self, deck_with_notes):
        backup_path = create_backup(deck_with_notes)

        assert os.path.exists(backup_path)
        assert backup_path.endswith(".pptx.bak")
        # Backup is alongside original
        assert os.path.dirname(backup_path) == os.path.dirname(deck_with_notes)

    def test_backup_is_valid_pptx(self, deck_with_notes):
        backup_path = create_backup(deck_with_notes)
        # Should be readable as a PPTX
        prs = Presentation(backup_path)
        assert len(prs.slides) == 3

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            create_backup("/nonexistent/deck.pptx")
```

**Step 3: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_writeback.py -v`
Expected: All tests FAIL with `NotImplementedError`

**Step 4: Commit**

```bash
git add outline2ppt/writeback.py tests/test_writeback.py
git commit -m "test: add failing tests for PPTX notes write-back"
```

---

### Task 2: Core writeback module — implementation

**Files:**
- Modify: `outline2ppt/writeback.py`

**Step 1: Implement `create_backup()`**

Replace the `create_backup` stub in `outline2ppt/writeback.py`:

```python
def create_backup(deck_path: str) -> str:
    """Copy deck to a timestamped .bak file alongside the original.

    Args:
        deck_path: Path to the PPTX file

    Returns:
        Path to the backup file

    Raises:
        FileNotFoundError: If deck_path doesn't exist
    """
    if not os.path.exists(deck_path):
        raise FileNotFoundError(f"File not found: {deck_path}")

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    backup_path = f"{deck_path}.{timestamp}.pptx.bak"
    shutil.copy2(deck_path, backup_path)
    return backup_path
```

Add these imports at the top of the file:

```python
import logging
import os
import shutil
from datetime import datetime

from pptx import Presentation

from outline2ppt.catalog import get_db, get_deck_slides
```

**Step 2: Implement `write_notes_to_pptx()`**

Replace the stub:

```python
def write_notes_to_pptx(
    deck_path: str,
    db_path: str = "slides.db",
    deck_id: Optional[int] = None,
    output_path: Optional[str] = None,
) -> WritebackResult:
    """Write DB notes to a PPTX file.

    Args:
        deck_path: Path to the source PPTX file
        db_path: Path to the SQLite database
        deck_id: Deck ID in DB (if None, look up by file_path)
        output_path: Save to this path instead of deck_path (for temp copies)

    Returns:
        WritebackResult with counts and warnings

    Raises:
        FileNotFoundError: PPTX file doesn't exist
        ValueError: Deck not found in DB, or slide count mismatch
    """
    if not os.path.exists(deck_path):
        raise FileNotFoundError(f"File not found: {deck_path}")

    conn = get_db(db_path)
    try:
        # Look up deck
        if deck_id is not None:
            row = conn.execute(
                "SELECT id FROM decks WHERE id = ?", (deck_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM decks WHERE file_path = ?",
                (os.path.abspath(deck_path),),
            ).fetchone()

        if row is None:
            raise ValueError(
                f"Deck not found in database for path: {deck_path}"
            )
        deck_id = row["id"]
    finally:
        conn.close()

    # Fetch DB slides
    db_slides = get_deck_slides(deck_id, db_path=db_path)

    # Open PPTX
    prs = Presentation(deck_path)

    # Validate slide count
    if len(prs.slides) != len(db_slides):
        raise ValueError(
            f"Slide count mismatch: DB has {len(db_slides)} slides "
            f"but PPTX has {len(prs.slides)}"
        )

    written = 0
    skipped = 0
    warnings = []

    for db_slide in db_slides:
        notes = (db_slide.get("notes") or "").strip()
        position = db_slide["position"]

        if not notes:
            skipped += 1
            continue

        pptx_slide = prs.slides[position - 1]
        notes_slide = pptx_slide.notes_slide
        notes_slide.notes_text_frame.text = notes
        written += 1

    save_path = output_path if output_path else deck_path
    prs.save(save_path)

    return WritebackResult(
        deck_id=deck_id,
        slides_written=written,
        slides_skipped=skipped,
        slides_total=len(db_slides),
        warnings=warnings,
    )
```

**Step 3: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_writeback.py -v`
Expected: All tests PASS

**Step 4: Run full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All existing tests still pass

**Step 5: Commit**

```bash
git add outline2ppt/writeback.py
git commit -m "feat: implement write_notes_to_pptx and create_backup"
```

---

### Task 3: CLI `write-notes` subcommand

**Files:**
- Modify: `outline2ppt/cli.py`

**Step 1: Write a test for the CLI command**

Add to `tests/test_writeback.py`:

```python
from outline2ppt.cli import build_parser, cmd_write_notes


class TestCmdWriteNotes:
    def test_writes_notes_and_creates_backup(self, cataloged, capsys):
        deck_id, deck_path, db_path = cataloged
        record_edit(1, "notes", "CLI edited", source="web", db_path=db_path)

        parser = build_parser()
        args = parser.parse_args(["write-notes", deck_path, "--db", db_path])
        result = cmd_write_notes(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Wrote notes to 1" in captured.out
        assert ".pptx.bak" in captured.out

        # Verify PPTX was modified
        prs = Presentation(deck_path)
        assert prs.slides[0].notes_slide.notes_text_frame.text == "CLI edited"

    def test_error_on_missing_file(self, capsys):
        parser = build_parser()
        args = parser.parse_args(["write-notes", "/nonexistent.pptx"])
        result = cmd_write_notes(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower() or "not found" in captured.out.lower()
```

**Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_writeback.py::TestCmdWriteNotes -v`
Expected: FAIL (cmd_write_notes doesn't exist, parser doesn't know about write-notes)

**Step 3: Add the CLI subcommand**

In `outline2ppt/cli.py`, add the command function before `build_parser()`:

```python
def cmd_write_notes(args):
    """Write DB notes back to a PPTX file."""
    from outline2ppt.writeback import write_notes_to_pptx, create_backup

    deck_path = args.deck
    db_path = getattr(args, "db", "slides.db")

    try:
        backup_path = create_backup(deck_path)
        print(f"Backup created: {backup_path}")
    except FileNotFoundError:
        print(f"Error: file not found: {deck_path}", file=sys.stderr)
        return 1

    try:
        result = write_notes_to_pptx(deck_path, db_path=db_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote notes to {result.slides_written} of {result.slides_total} slides "
          f"({result.slides_skipped} skipped — no notes in DB)")
    for w in result.warnings:
        print(f"  Warning: {w}")
    return 0
```

In `build_parser()`, add the subparser (after the `models` subparser, before `return parser`):

```python
    p_write_notes = sub.add_parser("write-notes", help="Write DB notes back to PPTX file")
    p_write_notes.add_argument("deck", help="Path to the PPTX file")
    p_write_notes.add_argument("--db", default="slides.db", help="Path to the SQLite database")
```

In the `commands` dict inside `main()`, add:

```python
        "write-notes": cmd_write_notes,
```

**Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_writeback.py::TestCmdWriteNotes -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add outline2ppt/cli.py tests/test_writeback.py
git commit -m "feat: add write-notes CLI subcommand"
```

---

### Task 4: Web API — `POST /api/decks/{id}/write-notes` endpoint

**Files:**
- Modify: `outline2ppt/web/routes.py`
- Modify: `tests/test_web_routes.py`

**Step 1: Write failing tests**

Add to `tests/test_web_routes.py`:

```python
class TestWriteNotesEndpoint:
    def test_writes_notes_to_pptx(self, client, db_path, deck_path):
        # Edit notes in DB first
        record_edit(1, "notes", "Web write-back test", source="web", db_path=db_path)

        resp = client.post("/api/decks/1/write-notes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slides_written"] == 1
        assert data["backup_path"] is not None

        # Verify PPTX was modified
        prs = Presentation(deck_path)
        assert prs.slides[0].notes_slide.notes_text_frame.text == "Web write-back test"

    def test_deck_not_found(self, client):
        resp = client.post("/api/decks/999/write-notes")
        assert resp.status_code == 404

    def test_slide_count_mismatch(self, client, deck_path, db_path):
        # Add a slide to the PPTX without re-cataloging
        prs = Presentation(deck_path)
        prs.slides.add_slide(prs.slide_layouts[0])
        prs.save(deck_path)

        resp = client.post("/api/decks/1/write-notes")
        assert resp.status_code == 409
        assert "mismatch" in resp.json()["error"].lower()
```

Add `record_edit` to the imports at the top of `tests/test_web_routes.py`:

```python
from outline2ppt.catalog import catalog_deck, get_db, record_edit
```

Note: the existing `deck_path` fixture creates a 1-slide deck. The `client` fixture catalogs it and returns a TestClient. The `db_path` fixture returns `client.app.state.db_path`.

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_web_routes.py::TestWriteNotesEndpoint -v`
Expected: FAIL (endpoint doesn't exist, 404 or 405)

**Step 3: Add the endpoint**

In `outline2ppt/web/routes.py`, add after the `notes_history_endpoint`:

```python
@router.post("/api/decks/{deck_id}/write-notes")
async def write_notes_to_deck_endpoint(deck_id: int, request: Request):
    """API: Write DB notes back to the original PPTX file (with backup)."""
    from outline2ppt.writeback import write_notes_to_pptx, create_backup

    db_path = request.app.state.db_path
    deck = get_deck_by_id(deck_id, db_path)
    if deck is None:
        return JSONResponse({"error": "Deck not found"}, status_code=404)

    file_path = deck.get("file_path", "")
    if not file_path or not os.path.exists(file_path):
        return JSONResponse({"error": "Source file not found"}, status_code=404)

    try:
        backup_path = create_backup(file_path)
    except FileNotFoundError:
        return JSONResponse({"error": "Source file not found"}, status_code=404)

    try:
        result = write_notes_to_pptx(
            file_path, db_path=db_path, deck_id=deck_id
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)

    return {
        "status": "ok",
        "slides_written": result.slides_written,
        "slides_skipped": result.slides_skipped,
        "slides_total": result.slides_total,
        "backup_path": backup_path,
        "warnings": result.warnings,
    }
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_web_routes.py::TestWriteNotesEndpoint -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add outline2ppt/web/routes.py tests/test_web_routes.py
git commit -m "feat: add POST /api/decks/{id}/write-notes endpoint"
```

---

### Task 5: Web API — update download endpoint to apply notes

**Files:**
- Modify: `outline2ppt/web/routes.py`
- Modify: `tests/test_web_routes.py`

**Step 1: Write failing test**

Add to `tests/test_web_routes.py`:

```python
class TestDownloadWithNotes:
    def test_download_applies_db_notes(self, client, db_path, deck_path):
        # Edit notes in DB
        record_edit(1, "notes", "Download test notes", source="web", db_path=db_path)

        resp = client.get("/api/decks/1/download")
        assert resp.status_code == 200

        # Save response to a temp file and verify notes
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            f.write(resp.content)
            tmp_path = f.name

        prs = Presentation(tmp_path)
        assert prs.slides[0].notes_slide.notes_text_frame.text == "Download test notes"
        os.unlink(tmp_path)

        # Original file should be untouched
        prs_orig = Presentation(deck_path)
        assert prs_orig.slides[0].notes_slide.notes_text_frame.text == "Original PPTX notes"

    def test_download_still_works_without_edits(self, client, deck_path):
        # No edits — download should still work and contain original notes
        resp = client.get("/api/decks/1/download")
        assert resp.status_code == 200

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            f.write(resp.content)
            tmp_path = f.name

        prs = Presentation(tmp_path)
        assert prs.slides[0].notes_slide.notes_text_frame.text == "Original PPTX notes"
        os.unlink(tmp_path)
```

Add `import os` to the top of `tests/test_web_routes.py` if not already there.

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_web_routes.py::TestDownloadWithNotes -v`
Expected: FAIL (download still serves original file, notes not applied)

**Step 3: Update the download endpoint**

Replace the existing `download_deck` endpoint in `outline2ppt/web/routes.py`:

```python
@router.get('/api/decks/{deck_id}/download')
async def download_deck(deck_id: int, request: Request):
    """API: Download a .pptx file with DB notes applied (temp copy, original untouched)."""
    from outline2ppt.writeback import write_notes_to_pptx

    db_path = request.app.state.db_path

    deck = get_deck_by_id(deck_id, db_path)
    if deck is None:
        return JSONResponse({'error': 'Deck not found'}, status_code=404)

    file_path = deck.get('file_path', '')
    if not file_path or not os.path.exists(file_path):
        return JSONResponse({'error': 'Source file not found'}, status_code=404)

    # Create temp copy with DB notes applied
    tmp = tempfile.NamedTemporaryFile(suffix=".pptx", delete=False)
    tmp.close()
    try:
        write_notes_to_pptx(
            file_path, db_path=db_path, deck_id=deck_id, output_path=tmp.name
        )
    except (FileNotFoundError, ValueError):
        # If write-back fails (e.g. mismatch), fall back to original file
        os.unlink(tmp.name)
        tmp_name = file_path
    else:
        tmp_name = tmp.name

    deck_name = deck['name']
    return FileResponse(
        tmp_name,
        media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
        headers={'Content-Disposition': f'attachment; filename="{deck_name}.pptx"'},
    )
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_web_routes.py::TestDownloadWithNotes -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add outline2ppt/web/routes.py tests/test_web_routes.py
git commit -m "feat: apply DB notes to downloaded PPTX files"
```

---

### Task 6: Integration tests — round-trip

**Files:**
- Modify: `tests/test_integration.py`

**Step 1: Write integration tests**

Add to `tests/test_integration.py`:

```python
from outline2ppt.writeback import write_notes_to_pptx, create_backup


class TestNotesWritebackIntegration:
    """Integration tests for the full notes round-trip: catalog → edit → write back."""

    @pytest.fixture
    def notes_deck(self, tmp_path):
        """Create a 2-slide PPTX with notes on slide 1."""
        prs = Presentation()
        layout = prs.slide_layouts[0]

        s1 = prs.slides.add_slide(layout)
        s1.shapes.title.text = "First Slide"
        s1.notes_slide.notes_text_frame.text = "Original first"

        s2 = prs.slides.add_slide(layout)
        s2.shapes.title.text = "Second Slide"

        path = str(tmp_path / "roundtrip.pptx")
        prs.save(path)
        return path

    def test_full_round_trip(self, tmp_path, notes_deck):
        db_path = str(tmp_path / "rt.db")

        # 1. Catalog
        deck_id = catalog_deck(notes_deck, db_path=db_path)

        # 2. Edit notes via record_edit
        from outline2ppt.catalog import record_edit
        record_edit(1, "notes", "Updated first slide notes", source="web", db_path=db_path)
        record_edit(2, "notes", "Brand new second slide notes", source="web", db_path=db_path)

        # 3. Write back
        result = write_notes_to_pptx(notes_deck, db_path=db_path, deck_id=deck_id)
        assert result.slides_written == 2
        assert result.slides_skipped == 0

        # 4. Verify PPTX
        prs = Presentation(notes_deck)
        assert prs.slides[0].notes_slide.notes_text_frame.text == "Updated first slide notes"
        assert prs.slides[1].notes_slide.notes_text_frame.text == "Brand new second slide notes"

    def test_write_to_output_path(self, tmp_path, notes_deck):
        db_path = str(tmp_path / "out.db")
        output = str(tmp_path / "output_copy.pptx")

        deck_id = catalog_deck(notes_deck, db_path=db_path)
        from outline2ppt.catalog import record_edit
        record_edit(1, "notes", "Output path test", source="web", db_path=db_path)

        write_notes_to_pptx(notes_deck, db_path=db_path, deck_id=deck_id, output_path=output)

        # Output has new notes
        prs_out = Presentation(output)
        assert prs_out.slides[0].notes_slide.notes_text_frame.text == "Output path test"

        # Original unchanged
        prs_orig = Presentation(notes_deck)
        assert prs_orig.slides[0].notes_slide.notes_text_frame.text == "Original first"

    def test_round_trip_preserves_after_recatalog(self, tmp_path, notes_deck):
        db_path = str(tmp_path / "recat.db")

        # Catalog → edit → write back
        deck_id = catalog_deck(notes_deck, db_path=db_path)
        from outline2ppt.catalog import record_edit
        record_edit(1, "notes", "Persisted notes", source="web", db_path=db_path)
        write_notes_to_pptx(notes_deck, db_path=db_path, deck_id=deck_id)

        # Re-catalog (simulates re-ingest)
        deck_id_2 = catalog_deck(notes_deck, db_path=db_path)

        # Notes should be preserved from the PPTX
        conn = get_db(db_path)
        row = conn.execute(
            "SELECT notes FROM slides WHERE deck_id = ? AND position = 1",
            (deck_id_2,),
        ).fetchone()
        conn.close()
        assert row["notes"] == "Persisted notes"
```

**Step 2: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_integration.py::TestNotesWritebackIntegration -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration tests for notes write-back round-trip"
```

---

### Task 7: Web UI — "Write to Deck" button

**Files:**
- Modify: `outline2ppt/web/static/index.html`

**Step 1: Add "Write to Deck" button next to Download**

Find the download button in the deck table (around line 434). Change the `<td>` that contains the download button to also include the write-to-deck button:

Replace:
```html
<td onclick="event.stopPropagation()">
    <button class="outline" style="width:auto; padding:0.3rem 0.7rem; font-size:0.8rem;" onclick="downloadDeck(${d.id})">Download</button>
</td>
```

With:
```html
<td onclick="event.stopPropagation()">
    <button class="outline" style="width:auto; padding:0.3rem 0.7rem; font-size:0.8rem;" onclick="downloadDeck(${d.id})">Download</button>
    <button class="outline" style="width:auto; padding:0.3rem 0.7rem; font-size:0.8rem; margin-left:0.3rem;" onclick="writeNotesToDeck(${d.id})">Write Notes to Deck</button>
</td>
```

**Step 2: Add the `writeNotesToDeck()` function**

Find the `downloadDeck` function (around line 812) and add the new function after it:

```javascript
async function writeNotesToDeck(deckId) {
    if (!confirm('Write DB notes back to the PPTX file? A backup will be created.')) return;
    try {
        const resp = await fetch(`/api/decks/${deckId}/write-notes`, { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok) {
            alert('Error: ' + (data.error || 'Unknown error'));
            return;
        }
        let msg = `Wrote notes to ${data.slides_written} of ${data.slides_total} slides`;
        if (data.slides_skipped > 0) msg += ` (${data.slides_skipped} skipped — no notes)`;
        if (data.backup_path) msg += `\nBackup: ${data.backup_path}`;
        alert(msg);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}
```

**Step 3: Manual testing**

No automated tests for UI JavaScript. Verify manually:
1. Load the web UI, deck list shows "Write Notes to Deck" button next to Download
2. Click button — confirm dialog appears
3. Click OK — success alert with write count and backup path
4. Open the PPTX in PowerPoint — verify notes match DB

**Step 4: Commit**

```bash
git add outline2ppt/web/static/index.html
git commit -m "feat: add Write Notes to Deck button in web UI"
```

---

### Task 8: Update changelog

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Read current changelog**

Read `CHANGELOG.md` to see the latest entry format.

**Step 2: Add entry**

Add under the most recent version heading (or Unreleased):

```markdown
### Added
- CLI: `outline2ppt write-notes` command to write DB notes back to PPTX files
- Web UI: "Write Notes to Deck" button in deck list
- API: `POST /api/decks/{id}/write-notes` endpoint with automatic backup
- Automatic timestamped backup (`.pptx.bak`) before modifying PPTX files

### Changed
- `GET /api/decks/{id}/download` now applies DB notes to the downloaded file (original untouched)
```

**Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for PPTX notes write-back feature"
```

---

### Task 9: Final verification

**Step 1: Run full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests pass, no regressions

**Step 2: Verify new test count**

The test suite should have gained approximately 14 new tests:
- `test_writeback.py`: ~10 tests (TestWriteNotesToPptx: 5, TestWritebackErrors: 3, TestCreateBackup: 3, TestCmdWriteNotes: 2) — note TestCreateBackup.test_file_not_found will be collapsed with the similar error test
- `test_web_routes.py`: ~5 tests (TestWriteNotesEndpoint: 3, TestDownloadWithNotes: 2)
- `test_integration.py`: 3 tests (TestNotesWritebackIntegration)

**Step 3: Quick smoke test**

If a real deck and DB are available, run:
```bash
venv/bin/python outline2ppt.py write-notes <some-deck.pptx> --db slides.db
```
Verify backup is created and notes are written.
