# Upload Processing Status Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stream real-time per-step progress from the ingest pipeline to the frontend during PPTX upload, replacing the generic spinner with a step-progress indicator.

**Architecture:** Add a `POST /api/decks/upload-stream` SSE endpoint that runs `ingest_deck()` in a background thread (via `asyncio.to_thread`), wiring its existing `progress_callback` to push SSE events through a `queue.Queue`. The frontend switches from a simple `fetch()` to an `EventSource`-like reader consuming the SSE stream. The original `/api/decks/upload` endpoint remains untouched as a non-streaming fallback.

**Tech Stack:** FastAPI `StreamingResponse`, Python `queue.Queue`, `asyncio.to_thread`, vanilla JS `fetch()` with `ReadableStream` for SSE consumption.

---

### Task 1: Add SSE upload-stream endpoint

**Files:**
- Modify: `outline2ppt/web/routes.py` (add new endpoint after the existing upload endpoint, ~line 613)

**Step 1: Write the failing test**

Add to `tests/test_web_file_mgmt.py`:

```python
# At the top, add to existing imports:
# (io, os, unittest.mock.patch, pytest already imported)

# ---------------------------------------------------------------------------
# TestUploadStream (SSE endpoint)
# ---------------------------------------------------------------------------


class TestUploadStream:
    """POST /api/decks/upload-stream should return SSE events."""

    @patch("outline2ppt.ingest.cmd_export_images", return_value=1)
    def test_stream_returns_sse_events(self, _mock_export, client):
        """Upload via SSE endpoint returns event stream with expected steps."""
        buf = make_pptx(num_slides=2)
        response = client.post(
            "/api/decks/upload-stream",
            files={"file": ("deck.pptx", buf, PPTX_MIME)},
            data={},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        # Parse SSE events from the response body
        body = response.text
        events = _parse_sse(body)

        # Must have at least export_images, catalog steps, and a complete event
        step_names = [e["data"].get("step") for e in events if "step" in e.get("data", {})]
        event_types = [e["event"] for e in events]
        assert "export_images" in step_names
        assert "catalog" in step_names
        assert "complete" in event_types

    @patch("outline2ppt.ingest.cmd_export_images", return_value=1)
    def test_stream_complete_has_deck_info(self, _mock_export, client):
        """The 'complete' event contains deck_id, deck_name, slide_count."""
        buf = make_pptx(num_slides=3)
        response = client.post(
            "/api/decks/upload-stream",
            files={"file": ("my_deck.pptx", buf, PPTX_MIME)},
            data={},
        )
        assert response.status_code == 200

        events = _parse_sse(response.text)
        complete_events = [e for e in events if e["event"] == "complete"]
        assert len(complete_events) == 1
        data = complete_events[0]["data"]
        assert "deck_id" in data
        assert "deck_name" in data
        assert data["slide_count"] == 3

    @patch("outline2ppt.ingest.cmd_analyze", return_value=0)
    @patch("outline2ppt.ingest.cmd_export_images", return_value=0)
    def test_stream_with_tags(self, _mock_export, _mock_analyze, client):
        """When generate_tags=true, SSE stream includes tags step."""
        buf = make_pptx(num_slides=1)
        response = client.post(
            "/api/decks/upload-stream",
            files={"file": ("deck.pptx", buf, PPTX_MIME)},
            data={"generate_tags": "true"},
        )
        assert response.status_code == 200

        events = _parse_sse(response.text)
        step_names = [e["data"].get("step") for e in events if "step" in e.get("data", {})]
        assert "tags" in step_names

    def test_stream_rejects_non_pptx(self, client):
        """Non-PPTX files should return 400 JSON error, not SSE."""
        buf = io.BytesIO(b"not a pptx")
        response = client.post(
            "/api/decks/upload-stream",
            files={"file": ("notes.txt", buf, "text/plain")},
        )
        assert response.status_code == 400
        assert "error" in response.json()


def _parse_sse(text: str) -> list:
    """Parse SSE text into a list of {event, data} dicts."""
    import json
    events = []
    current_event = "message"
    current_data = ""
    for line in text.split("\n"):
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            current_data = line[6:].strip()
        elif line == "":
            if current_data:
                try:
                    parsed = json.loads(current_data)
                except (json.JSONDecodeError, ValueError):
                    parsed = current_data
                events.append({"event": current_event, "data": parsed})
                current_event = "message"
                current_data = ""
    # Handle final event without trailing blank line
    if current_data:
        try:
            parsed = json.loads(current_data)
        except (json.JSONDecodeError, ValueError):
            parsed = current_data
        events.append({"event": current_event, "data": parsed})
    return events
```

**Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_web_file_mgmt.py::TestUploadStream -v`
Expected: FAIL — 404 for `/api/decks/upload-stream`

**Step 3: Write the SSE endpoint**

Add to `outline2ppt/web/routes.py`:

1. Add `StreamingResponse` to the imports at line 8:
```python
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
```

2. Add this endpoint after the existing `upload_deck` endpoint (after line 612):

```python
@router.post('/api/decks/upload-stream')
async def upload_deck_stream(
    request: Request,
    file: UploadFile = File(...),
    generate_tags: bool = Form(False),
):
    """API: Upload a .pptx file and stream SSE progress events during ingest."""
    import asyncio
    import json
    import queue

    from outline2ppt.ingest import ingest_deck

    # Validate file extension (return JSON error, not SSE)
    if not file.filename or not file.filename.lower().endswith('.pptx'):
        return JSONResponse({'error': 'Only .pptx files are supported'}, status_code=400)

    db_path = request.app.state.db_path
    uploads_dir = request.app.state.uploads_dir
    gateway_config = request.app.state.gateway_config

    # Save uploaded file
    unique_prefix = uuid.uuid4().hex
    safe_name = f'{unique_prefix}_{file.filename}'
    dest_path = os.path.join(uploads_dir, safe_name)
    content = await file.read()
    with open(dest_path, 'wb') as fh:
        fh.write(content)

    # Queue for progress events from the ingest thread
    event_queue = queue.Queue()

    # Map ingest progress_callback steps to SSE events
    _STEP_MAP = {
        'export_images': ('progress', 'export_images', 'running'),
        'export_images_done': ('progress', 'export_images', 'done'),
        'export_images_skipped': ('progress', 'export_images', 'skipped'),
        'catalog': ('progress', 'catalog', 'running'),
        'catalog_done': ('progress', 'catalog', 'done'),
        'tags': ('progress', 'tags', 'running'),
        'tags_done': ('progress', 'tags', 'done'),
        'tags_partial': ('progress', 'tags', 'done'),
        'tags_error': ('progress', 'tags', 'error'),
    }

    def progress_callback(step: str, detail: str):
        mapping = _STEP_MAP.get(step)
        if mapping:
            event_type, step_name, status = mapping
            event_queue.put((event_type, json.dumps({
                'step': step_name, 'status': status, 'detail': detail,
            })))

    async def event_generator():
        # Run synchronous ingest in a thread
        loop = asyncio.get_event_loop()
        ingest_task = loop.run_in_executor(
            None,
            lambda: ingest_deck(
                deck_path=dest_path,
                db_path=db_path,
                generate_tags=generate_tags,
                gateway_config=gateway_config,
                require_images=False,
                progress_callback=progress_callback,
            ),
        )

        result = None
        error = None
        while True:
            # Drain queued events
            while not event_queue.empty():
                try:
                    event_type, data = event_queue.get_nowait()
                    yield f"event: {event_type}\ndata: {data}\n\n"
                except queue.Empty:
                    break

            # Check if ingest is done
            if ingest_task.done():
                try:
                    result = ingest_task.result()
                except Exception as exc:
                    error = str(exc)
                break

            # Yield control briefly to let the thread make progress
            await asyncio.sleep(0.1)

        # Drain any remaining events
        while not event_queue.empty():
            try:
                event_type, data = event_queue.get_nowait()
                yield f"event: {event_type}\ndata: {data}\n\n"
            except queue.Empty:
                break

        # Emit final event
        if error:
            yield f"event: error\ndata: {json.dumps({'detail': error})}\n\n"
        elif result:
            yield f"event: complete\ndata: {json.dumps({
                'deck_id': result['deck_id'],
                'deck_name': result['deck_name'],
                'slide_count': result['slide_count'],
                'images_exported': result['images_exported'],
                'tags_generated': result['tags_generated'],
            })}\n\n"

    return StreamingResponse(event_generator(), media_type='text/event-stream')
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_web_file_mgmt.py::TestUploadStream -v`
Expected: All 4 tests PASS

**Step 5: Run existing upload tests to verify no regressions**

Run: `venv/bin/python -m pytest tests/test_web_file_mgmt.py -v`
Expected: All tests PASS (existing + new)

**Step 6: Commit**

```bash
git add outline2ppt/web/routes.py tests/test_web_file_mgmt.py
git commit -m "feat: add SSE upload-stream endpoint for real-time ingest progress"
```

---

### Task 2: Replace frontend spinner with step-progress UI and SSE consumer

**Files:**
- Modify: `outline2ppt/web/static/index.html`
  - CSS section (~line 8-230): add step-progress styles
  - HTML section (~line 257-259): replace spinner div
  - JS section (~line 779-811): rewrite `uploadDeck()` function

**Step 1: Add step-progress CSS styles**

After the existing `.spinner-icon` / `@keyframes spin` rules (~line 219), add:

```css
        .upload-progress {
            margin-bottom: 0.75rem;
            padding: 0.75rem 1rem;
            border: 1px solid var(--pico-muted-border-color);
            border-radius: var(--pico-border-radius);
            font-size: 0.85rem;
        }
        .upload-progress .progress-title {
            font-weight: 600;
            margin-bottom: 0.5rem;
        }
        .upload-progress .step {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.2rem 0;
        }
        .upload-progress .step .step-icon {
            width: 16px;
            text-align: center;
            flex-shrink: 0;
        }
        .upload-progress .step.done .step-icon { color: #2d8a4e; }
        .upload-progress .step.error .step-icon,
        .upload-progress .step.skipped .step-icon { color: #cf6679; }
        .upload-progress .step.running .step-icon .spinner-icon {
            display: inline-block;
        }
        .upload-progress .step.waiting { color: var(--pico-muted-color); }
        .upload-progress .step .step-detail {
            color: var(--pico-muted-color);
            margin-left: auto;
            font-size: 0.8rem;
        }
```

**Step 2: Replace spinner HTML**

Replace lines 257-259 (the `deck-upload-spinner` div) with:

```html
            <div id="deck-upload-progress" style="display:none;" class="upload-progress">
                <div class="progress-title">Processing: <span id="upload-progress-filename"></span></div>
                <div class="step waiting" id="step-export_images">
                    <span class="step-icon">○</span>
                    <span class="step-label">Export images</span>
                    <span class="step-detail"></span>
                </div>
                <div class="step waiting" id="step-catalog">
                    <span class="step-icon">○</span>
                    <span class="step-label">Catalog deck</span>
                    <span class="step-detail"></span>
                </div>
                <div class="step waiting" id="step-tags" style="display:none;">
                    <span class="step-icon">○</span>
                    <span class="step-label">Generate AI tags</span>
                    <span class="step-detail"></span>
                </div>
            </div>
```

**Step 3: Rewrite `uploadDeck()` to consume SSE stream**

Replace the `uploadDeck` function (lines 779-811) with:

```javascript
        async function uploadDeck(input) {
            if (!input.files.length) return;
            const file = input.files[0];
            const generateTags = document.getElementById('deck-generate-tags').checked;

            // Disable upload controls
            const uploadBtn = document.querySelector('#deck-list button.outline');
            uploadBtn.disabled = true;
            input.disabled = true;

            // Show progress UI
            const progressEl = document.getElementById('deck-upload-progress');
            document.getElementById('upload-progress-filename').textContent = file.name;
            const tagsStep = document.getElementById('step-tags');
            tagsStep.style.display = generateTags ? 'flex' : 'none';
            // Reset all steps to waiting
            for (const step of progressEl.querySelectorAll('.step')) {
                step.className = 'step waiting';
                step.querySelector('.step-icon').textContent = '○';
                step.querySelector('.step-detail').textContent = '';
            }
            progressEl.style.display = 'block';

            const formData = new FormData();
            formData.append('file', file);
            if (generateTags) formData.append('generate_tags', 'true');

            try {
                const resp = await fetch('/api/decks/upload-stream', {method: 'POST', body: formData});

                if (!resp.ok) {
                    const data = await resp.json();
                    toast(`Upload failed: ${data.error || resp.statusText}`);
                    progressEl.style.display = 'none';
                    uploadBtn.disabled = false;
                    input.disabled = false;
                    input.value = '';
                    return;
                }

                // Read SSE stream
                const reader = resp.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const {done, value} = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, {stream: true});

                    // Process complete SSE messages (separated by double newline)
                    const parts = buffer.split('\n\n');
                    buffer = parts.pop();  // keep incomplete part
                    for (const part of parts) {
                        if (!part.trim()) continue;
                        let eventType = 'message';
                        let eventData = '';
                        for (const line of part.split('\n')) {
                            if (line.startsWith('event: ')) eventType = line.slice(7).trim();
                            else if (line.startsWith('data: ')) eventData = line.slice(6).trim();
                        }
                        if (!eventData) continue;
                        const data = JSON.parse(eventData);
                        handleUploadEvent(eventType, data);
                    }
                }
            } catch (e) {
                toast('Upload failed: network error');
            }

            progressEl.style.display = 'none';
            uploadBtn.disabled = false;
            input.disabled = false;
            input.value = '';
            await showDecks();
        }

        function handleUploadEvent(eventType, data) {
            if (eventType === 'progress') {
                const stepEl = document.getElementById('step-' + data.step);
                if (!stepEl) return;
                stepEl.className = 'step ' + data.status;
                const icon = stepEl.querySelector('.step-icon');
                const detail = stepEl.querySelector('.step-detail');
                if (data.status === 'running') {
                    icon.innerHTML = '<div class="spinner-icon"></div>';
                } else if (data.status === 'done') {
                    icon.textContent = '✓';
                } else if (data.status === 'error' || data.status === 'skipped') {
                    icon.textContent = '✗';
                }
                detail.textContent = data.detail || '';
            } else if (eventType === 'complete') {
                const parts = [`Uploaded "${data.deck_name}" — ${data.slide_count} slide${data.slide_count !== 1 ? 's' : ''}`];
                if (data.images_exported) parts.push('images exported');
                if (data.tags_generated) parts.push('tags generated');
                toast(parts.join(', '));
            } else if (eventType === 'error') {
                toast(`Upload failed: ${data.detail}`);
            }
        }
```

**Step 4: Manual verification**

Run: `venv/bin/python outline2ppt.py serve --port 8000`
Open browser at http://localhost:8000, upload a PPTX, confirm step-progress UI appears.

**Step 5: Commit**

```bash
git add outline2ppt/web/static/index.html
git commit -m "feat: step-progress UI with SSE consumer for upload status"
```

---

### Task 3: Update changelog

**Files:**
- Modify: `CHANGELOG.md` (~line 9, under `[Unreleased]` → `### Added`)

**Step 1: Add changelog entry**

Under the `### Added` section in `## [Unreleased]`, append:

```markdown
- Real-time per-step progress display when uploading decks in the web UI (SSE streaming)
- Upload button disabled during processing to prevent duplicate uploads
- API: `POST /api/decks/upload-stream` SSE endpoint for streaming ingest progress
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for upload progress streaming feature"
```

---

### Task 4: Run full test suite to verify no regressions

**Step 1: Run all tests**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS, no regressions.
