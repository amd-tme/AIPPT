# Session Prompt: Enhanced Web Upload with Ingest Pipeline

## Context

You are working on the `aippt-dev` branch of `/home/matt/git/aippt-dev`, an outline-to-PowerPoint tool with a SQLite catalog, web UI, and CLI.

Two recent features were just implemented:
1. **Web File Management** — Upload/download decks via browser (`POST /api/decks/upload`, `GET /api/decks/{deck_id}/download`)
2. **Slide Metadata** — Author, creation date, modified date extracted from PPTX core_properties

A separate branch `feature/ingest` (branched from `main`, developed independently) adds a CLI `ingest` command that orchestrates: image export (PowerShell) → catalog → optional AI tag generation — in one step. This branch has NOT been merged yet.

## What Needs to Happen

Merge the `feature/ingest` CLI work into `aippt-dev`, then enhance the web UI upload flow to use the same ingest pipeline — so uploading a deck through the browser automatically exports images and optionally generates tags.

### Specific Requirements

1. **Merge `feature/ingest` into `aippt-dev`**
   - The branch adds `cmd_ingest()` and its argparser to `cli.py`, plus tests in `test_cli.py`
   - There will likely be merge conflicts in `cli.py` and `test_cli.py` since both branches modified these files
   - Resolve conflicts preserving both sets of changes

2. **Refactor ingest logic into a reusable function**
   - Currently `cmd_ingest()` in `cli.py` is CLI-only (uses `print()`, constructs `argparse.Namespace`)
   - Extract the core orchestration into a function usable by both CLI and web API, e.g.:
     ```python
     def ingest_deck(
         deck_path: str,
         db_path: str = "slides.db",
         images_dir: str | None = None,
         generate_tags: bool = False,
         taxonomy: str | None = None,
         model: str | None = None,
         gateway_config: str | None = None,
         api_key: str | None = None,
         width: int = 1920,
         height: int = 1080,
         progress_callback: callable | None = None,
     ) -> dict:
         """Run full ingest pipeline: export images → catalog → optional tags.

         Returns dict with: deck_id, deck_name, slide_count, images_dir, tags_generated
         """
     ```
   - `cmd_ingest()` becomes a thin wrapper that calls this function with a print-based progress callback
   - The web upload endpoint calls this same function

3. **Enhance `POST /api/decks/upload` endpoint**
   - After saving the uploaded file, call `ingest_deck()` instead of just `catalog_deck()`
   - This automatically runs PowerShell image export + catalog
   - Accept an optional form field `generate_tags` (boolean, default false) — when true, runs AI tag generation as part of ingest
   - The endpoint should handle the case where PowerShell/PowerPoint is unavailable gracefully (catalog without images rather than failing entirely)
   - Return enhanced response: `{id, name, slide_count, images_exported, tags_generated, message}`

4. **Update the web UI upload form**
   - Add a checkbox: "Generate AI tags" (unchecked by default) next to the Upload Deck button
   - When checked, the upload request includes `generate_tags=true` in the FormData
   - Update the success toast to reflect what happened: "Uploaded 'DeckName' — 12 slides, images exported" or "Uploaded 'DeckName' — 12 slides, images exported, tags generated"
   - Update the spinner text to reflect progress if possible (or keep generic "Uploading & processing...")

5. **Tests**
   - Update `tests/test_web_file_mgmt.py` to cover the enhanced upload (with and without tag generation)
   - Add unit tests for the extracted `ingest_deck()` function
   - Ensure existing ingest CLI tests still pass

## Key Files to Understand

Read these before starting:

| File | Why |
|------|-----|
| `outline2ppt/cli.py` | Current `cmd_ingest()` (lines ~702-766), `cmd_export_images()` (lines ~769+), `cmd_analyze()` (line 334) |
| `outline2ppt/web/routes.py` | Current upload endpoint (lines ~495-530), analyze endpoint pattern (lines ~298-331) for LLM client setup |
| `outline2ppt/web/app.py` | App state: `db_path`, `uploads_dir`, `gateway_config` |
| `outline2ppt/web/static/index.html` | Current upload UI: search for `uploadDeck`, `deck-upload-file`, `deck-upload-spinner` |
| `outline2ppt/catalog.py` | `catalog_deck()` function — the core catalog logic |
| `tests/test_web_file_mgmt.py` | Existing upload/download tests |
| `tests/test_cli.py` | Existing ingest CLI tests (from feature/ingest merge) |
| `docs/plans/2026-02-26-prd-ingest-command.md` | Ingest command PRD |
| `docs/plans/2026-02-26-web-file-management.md` | Web file management PRD |

## Architecture Notes

- **PowerShell image export** (`cmd_export_images`) shells out to `scripts/Export-SlidesToImages.ps1` via PowerShell. It requires PowerPoint COM automation (Windows/WSL). The function returns 0 on success, non-zero on failure.
- **AI tag generation** uses `cmd_analyze()` which internally creates an `LLMClient` from the gateway config. For the web endpoint, the gateway config path is available via `request.app.state.gateway_config`.
- **Image directory convention**: `images/<deck-name>/` with files named `Slide1.png`, `Slide2.png`, etc.
- The web app runs via FastAPI/uvicorn. Long-running operations (image export, tag generation) will block the request. This is acceptable for v1 — the UI already shows a spinner during upload.
- `catalog_deck()` accepts an `images_dir` parameter to link exported images to slides in the database.

## Implementation Order

1. Merge `feature/ingest` into `aippt-dev` (resolve conflicts)
2. Extract `ingest_deck()` from `cmd_ingest()` — put it in a logical location (could stay in `cli.py` or move to a new `outline2ppt/ingest.py`)
3. Update `cmd_ingest()` to wrap `ingest_deck()`
4. Update `POST /api/decks/upload` to call `ingest_deck()`
5. Update web UI with tag generation checkbox
6. Add/update tests
7. Run full test suite, commit

## Branch State

```
aippt-dev (current):  026c279 - has metadata + file management features
feature/ingest:       faa950f - has CLI ingest command (export + catalog + optional tags)
```

Both branched from different points but share common ancestry through `actually-useful`/`main`.
