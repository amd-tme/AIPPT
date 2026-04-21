# PRD: Enhanced Outline Generation in Web UI

**Date:** 2026-03-02
**Author:** Matt
**Status:** Draft

---

## Summary

Enable users to create PowerPoint presentations from markdown outlines directly in the web UI. Users can paste markdown text or upload a `.md` file, with enhanced mode (LLM-powered layout and notes generation) enabled by default. A configurable default template (similar to `models.yaml`) provides the PPTX template without requiring a separate upload. The generated deck is automatically ingested into the catalog.

## Motivation

- **Problem:** The outline-to-PPT generation workflow is only available via CLI (`outline2ppt create`). Web UI users have no way to create new presentations — they can only upload existing ones.
- **Who benefits:** End users who want the full creation workflow without using the command line.
- **Without this:** Users must use the CLI for deck generation, limiting the web UI to a catalog/analysis tool rather than a complete presentation workflow.

## Requirements

### Must Have

- [ ] Textarea for pasting markdown outlines in the web UI
- [ ] File upload for `.md` files as an alternative to pasting
- [ ] "Enhanced mode" toggle (default: on) for LLM-powered layout and notes
- [ ] Default template configuration via `templates.yaml` config file
- [ ] Template path configurable in Settings view
- [ ] Generated PPTX is automatically ingested (cataloged) after creation
- [ ] Progress feedback during generation (reuse SSE pattern from upload status PRD)
- [ ] Model selector for enhanced mode (populated from available models)

### Nice to Have

- [ ] Preview of parsed slide count before generation
- [ ] Download link for the generated PPTX in the completion message

### Out of Scope

- Image generation (`--image-gen` option) — keep this CLI-only for now
- Multiple template management (upload/browse templates)
- Outline editing or preview in the web UI (just input and generate)
- Template analysis display in the web UI

---

## Design

### Approach

Add a "Create Deck" panel to the web UI that wraps the existing `cmd_create` pipeline. The backend accepts markdown text + options, writes the outline to a temp file, runs the create pipeline, then ingests the output PPTX into the catalog. Progress is streamed via SSE (same pattern as the upload status feature).

A new `templates.yaml` config file stores the default template path, following the same pattern as `models.yaml`. The Settings view gets a new section for configuring the template path.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/web/routes.py` | Modified | Add `POST /api/decks/create` SSE endpoint, `GET/PUT /api/templates` endpoints |
| `outline2ppt/web/static/index.html` | Modified | Add "Create Deck" UI panel, template settings section |
| `outline2ppt/config.py` | Modified | Add `get_template_default()` / `set_template_default()` helpers (mirror model config pattern) |

### Data Model Changes

No data model changes. The generated PPTX goes through the existing ingest pipeline which creates deck/slide records normally.

---

## CLI Changes

No CLI changes. The web endpoint wraps the existing `cmd_create` logic.

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Deck list | Add "Create Deck" panel/section | Expandable panel with markdown input, options, and create button |
| Settings | Add template configuration section | Display and edit default template path |

### New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/decks/create` | SSE endpoint: accepts markdown + options, generates PPTX, ingests, streams progress |
| GET | `/api/templates` | Returns current template configuration |
| PUT | `/api/templates` | Updates default template path |

#### POST `/api/decks/create` Request

Form fields:
- `outline_text` (string, required if no file): Raw markdown text
- `outline_file` (UploadFile, required if no text): `.md` file upload
- `enhance` (bool, default: true): Enable enhanced mode
- `model` (string, optional): Override model for enhancement
- `title` (string, optional): Deck title (defaults to first H1 in outline)

#### SSE Event Stream

```
event: progress
data: {"step": "parse", "status": "done", "detail": "Parsed 15 slides from outline"}

event: progress
data: {"step": "enhance", "status": "running", "detail": "Enhancing slide 3/15: Introduction"}

event: progress
data: {"step": "enhance", "status": "done", "detail": "All slides enhanced"}

event: progress
data: {"step": "ingest", "status": "running", "detail": "Cataloging generated deck..."}

event: complete
data: {"deck_id": 8, "deck_name": "my-presentation", "slide_count": 15, "output_path": "/path/to/output.pptx"}
```

### Wireframe / Mockup

```
┌─────────────────────────────────────────────────────────┐
│ Cataloged Decks                          [Upload Deck]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ ▼ Create Deck from Outline                              │
│ ┌─────────────────────────────────────────────────────┐ │
│ │                                                     │ │
│ │  Paste markdown outline or upload .md file:         │ │
│ │  ┌───────────────────────────────────────────────┐  │ │
│ │  │ # My Presentation                            │  │ │
│ │  │ ## Slide 1: Introduction                     │  │ │
│ │  │ - Key point one                              │  │ │
│ │  │ - Key point two                              │  │ │
│ │  │                                              │  │ │
│ │  └───────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │  [Upload .md]  ☑ Enhanced mode  Model: [claude-v2▾] │ │
│ │                                                     │ │
│ │                            [Create Presentation]    │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ Name   │ Slides │ Author │ Created │ Updated │ Actions  │
│ ...    │ ...    │ ...    │ ...     │ ...     │ ...      │
└─────────────────────────────────────────────────────────┘
```

Settings template section:

```
┌─────────────────────────────────────────────────────────┐
│ Default Template                                        │
│                                                         │
│ Template path: [templates/default.pptx          ] [Save]│
│                                                         │
│ Source: templates.yaml                                  │
└─────────────────────────────────────────────────────────┘
```

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_web.py` | `TestCreateDeck` | Create endpoint with text input, file upload, enhance on/off |
| `tests/test_config.py` | `TestTemplateConfig` | `get_template_default()`, `set_template_default()` |

### Integration Tests

Add to `tests/test_integration.py`: submit a small markdown outline via `/api/decks/create` with `enhance=false`, verify a PPTX is generated and the deck appears in the catalog.

### Manual Testing

1. Paste a 3-slide markdown outline with enhanced mode on -- expect per-slide enhancement progress, then deck appears in catalog
2. Upload a `.md` file with enhanced mode off -- expect quick generation with no LLM calls
3. Try creating with no template configured -- expect clear error message
4. Verify generated deck appears in deck list and slides are browsable
5. Test with an empty textarea and no file -- expect validation error

---

## Changelog Entry

```markdown
### Added
- Create presentations from markdown outlines in the web UI (paste text or upload .md file)
- Enhanced mode toggle for LLM-powered layout and speaker notes generation
- Default template configuration via `templates.yaml`
- Template path configurable in Settings view
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add template config helpers to `config.py` | `config.py` | -- |
| 2 | Add `GET/PUT /api/templates` endpoints | `routes.py` | 1 |
| 3 | Add `POST /api/decks/create` SSE endpoint wrapping create pipeline | `routes.py` | 1 |
| 4 | Add "Create Deck" UI panel with textarea, file upload, options | `index.html` | 3 |
| 5 | Add template settings section to Settings view | `index.html` | 2 |
| 6 | Add unit/integration tests | `tests/test_web.py`, `tests/test_config.py` | 1, 2, 3 |
| 7 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** The `cmd_create` pipeline currently writes progress to `logger.info()` rather than a callback — may need a thin wrapper to capture per-slide enhancement progress for SSE streaming. Mitigation: wrap the enhance loop with a progress-aware function similar to `ingest_deck`'s `progress_callback`.
- **Risk:** Template path validation — the configured template must exist on the server filesystem. Mitigation: validate at generation time and return a clear error if missing.
- **Question:** Should `templates.yaml` support multiple named templates (for future expansion), or just a single `default_template` path? Recommendation: start with a single `default_template` key; the schema can be extended later.

---

## References

- CLI `create` command: `outline2ppt/cli.py` line 10 (`cmd_create`)
- CLI argparse setup: `outline2ppt/cli.py` line 1053
- Model config pattern: `outline2ppt/config.py` (`get_model_default`, `set_model_default`)
- Related PRD: `docs/plans/2026-03-02-prd-upload-processing-status.md` (SSE pattern)
