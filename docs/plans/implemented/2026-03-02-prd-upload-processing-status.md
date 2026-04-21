# PRD: Upload Processing Status

**Date:** 2026-03-02
**Author:** Matt
**Status:** Draft

---

## Summary

Display real-time, per-step processing status when a PPTX is uploaded in the web UI, and disable the upload button until processing completes. The ingest pipeline has three distinct steps (export images, catalog, generate tags) that can each take significant time — especially AI tag generation. Users currently see only a generic "Uploading & processing..." spinner with no indication of progress or which step is running.

## Motivation

- **Problem:** The current upload flow shows a single spinner with no granularity. For large decks with tag generation enabled, the process can take 30+ seconds with zero feedback. Users don't know if it's working, stuck, or failed.
- **Who benefits:** End users uploading decks via the web UI.
- **Without this:** Users may re-click the upload button (triggering duplicate ingests), close the tab thinking it's frozen, or simply have a poor experience.

## Requirements

### Must Have

- [ ] Upload button is disabled while processing is in progress
- [ ] Per-step status display showing which pipeline stage is active (exporting images, cataloging, generating tags)
- [ ] Clear completion indication with summary (slide count, what succeeded)
- [ ] Error states displayed per-step (e.g., image export failed but cataloging continued)
- [ ] File input is also disabled during processing to prevent double-uploads

### Nice to Have

- [ ] Elapsed time display per step
- [ ] Animated progress indicator (checkmarks for completed steps, spinner for active step)

### Out of Scope

- Per-slide progress within a step (e.g., "Tagging slide 3 of 20")
- Upload progress bar for the file transfer itself (browser handles this natively for small files)
- Cancellation support

---

## Design

### Approach

Use **Server-Sent Events (SSE)** to stream per-step progress from the backend to the frontend during upload processing. The ingest pipeline already accepts a `progress_callback` parameter — the new SSE endpoint will wire this callback to push events to the client.

The frontend replaces the generic spinner with a step-progress indicator and disables the upload button for the duration.

SSE is preferred over polling because the ingest pipeline is synchronous and linear — each step emits exactly one start and one done/error event. No job queue, task IDs, or polling intervals needed.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/web/routes.py` | Modified | Add `POST /api/decks/upload-stream` SSE endpoint that wraps ingest with progress streaming |
| `outline2ppt/web/static/index.html` | Modified | Replace spinner with step-progress UI; disable upload button during processing; consume SSE stream |
| `outline2ppt/ingest.py` | No change | Already supports `progress_callback` — no modifications needed |

### Data Model Changes

No data model changes.

---

## CLI Changes

No CLI changes.

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Deck list | Upload button disabled during processing | Button gets `disabled` attribute and visual indication |
| Deck list | Step-progress indicator replaces spinner | Shows pipeline steps with status icons |

### New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/decks/upload-stream` | SSE endpoint that uploads, ingests, and streams per-step progress events |

#### SSE Event Format

```
event: progress
data: {"step": "export_images", "status": "running", "detail": "Exporting slide images..."}

event: progress
data: {"step": "export_images", "status": "done", "detail": "Images exported to images/deck/"}

event: progress
data: {"step": "catalog", "status": "running", "detail": "Cataloging deck..."}

event: progress
data: {"step": "catalog", "status": "done", "detail": "Cataloged as deck_id=5"}

event: progress
data: {"step": "tags", "status": "running", "detail": "Generating AI tags..."}

event: progress
data: {"step": "tags", "status": "done", "detail": "Tags generated"}

event: complete
data: {"deck_id": 5, "deck_name": "my-deck", "slide_count": 12, "images_exported": true, "tags_generated": true}

event: error
data: {"step": "export_images", "detail": "PowerShell unavailable, continuing without images"}
```

### Wireframe / Mockup

```
┌─────────────────────────────────────────────────────────┐
│ Cataloged Decks                    [Upload Deck] (disabled) │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Processing: my-presentation.pptx                       │
│                                                         │
│  ✓ Export images          done                          │
│  ● Catalog deck           cataloging...                 │
│  ○ Generate AI tags       waiting                       │
│                                                         │
└─────────────────────────────────────────────────────────┘

Legend: ✓ = completed, ● = in progress (spinner), ○ = pending
        ✗ = failed/skipped (with detail text)
```

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_web.py` | `TestUploadStream` | SSE endpoint returns correct event sequence; button-disable logic tested via endpoint response format |

### Integration Tests

Add to `tests/test_integration.py`: upload a small PPTX via the SSE endpoint and verify the event stream contains expected step transitions (export_images → catalog → complete).

### Manual Testing

1. Upload a deck with "Generate AI tags" unchecked -- expect 2 steps (export, catalog) then completion toast
2. Upload a deck with "Generate AI tags" checked -- expect 3 steps, tag step visible with spinner
3. During processing, verify "Upload Deck" button is visually disabled and unclickable
4. Upload on WSL2 where image export may fail -- expect export step shows skipped/warning, catalog proceeds

---

## Changelog Entry

```markdown
### Added
- Real-time per-step progress display when uploading decks in the web UI
- Upload button is disabled during processing to prevent duplicate uploads
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add SSE upload endpoint with progress_callback wiring | `routes.py` | -- |
| 2 | Replace frontend spinner with step-progress UI and SSE consumer | `index.html` | 1 |
| 3 | Disable upload button and file input during processing | `index.html` | 2 |
| 4 | Add unit/integration tests for SSE endpoint | `tests/test_web.py` | 1 |
| 5 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** SSE requires the ingest pipeline to run in the request handler thread. Since FastAPI/uvicorn is async, the synchronous `ingest_deck()` call should be wrapped in `asyncio.to_thread()` or `run_in_executor()` to avoid blocking the event loop -- mitigation: use `StreamingResponse` with a background thread pushing to a queue.
- **Risk:** If the browser disconnects mid-stream, the ingest should still complete (it's server-side work) -- mitigation: the ingest runs regardless; SSE is fire-and-forget from the server perspective.

---

## References

- Existing `progress_callback` in `outline2ppt/ingest.py` (lines 29, 46, 61-63)
- Current upload endpoint: `routes.py` line 559
- Current frontend upload function: `index.html` line 779
