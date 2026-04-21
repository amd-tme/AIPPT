# Design: Create Deck from Outline (Web UI)

**Date:** 2026-03-03
**PRD:** `docs/plans/2026-03-02-prd-outline-generation.md`
**Status:** Approved

---

## Architecture

### Core Pipeline Extraction

Extract reusable `create_deck()` from `cmd_create` in `cli.py`:

```python
def create_deck(
    outline_text: str,
    template_path: str,
    output_path: str,
    enhance: bool = True,
    model: str | None = None,
    gateway_config: str | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
) -> dict:
    """
    Create a PPTX from markdown outline text.

    Progress callback receives (step, detail) tuples:
      - ("parse", "Parsed 15 slides from outline")
      - ("enhance", "Enhancing slide 3/15: Introduction")
      - ("build", "Building slide 5/15")

    Returns: {'output_path': str, 'slide_count': int, 'title': str}
    """
```

`cmd_create` becomes a thin wrapper that:
1. Reads the outline file to text
2. Calls `create_deck()`
3. Handles CLI-specific concerns (exit codes, print output)

### Template Configuration

Mirror the `models.yaml` pattern in `config.py`:

- New file: `templates.yaml` with `default_template` key
- `get_template_default() -> str` — returns configured template path
- `set_template_default(path: str)` — validates and saves
- Same strict validation (no silent fallbacks)

### SSE Endpoint

`POST /api/decks/create` follows the existing upload-stream pattern:

1. **Pre-SSE validation** — check outline text/file, template exists → return JSON errors
2. **Worker thread** — `create_deck()` then `ingest_deck()`, posting events to a queue
3. **Async generator** — reads queue, yields SSE events

Steps: `parse` → `enhance` (per-slide updates) → `build` → `ingest` → `complete`

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/decks/create` | SSE: create deck from outline |
| GET | `/api/templates` | Return template config |
| PUT | `/api/templates` | Update default template path |

### UI Components

**Create Deck Panel** (deck list view):
- Collapsible panel above the deck table
- Textarea for markdown input
- File upload button for `.md` files (fills textarea on load)
- Enhanced mode checkbox (default: checked)
- Model selector dropdown (populated from `/api/models`)
- "Create Presentation" button
- Step-progress component (reuses upload pattern)

**Settings View** (template section):
- "Default Template" section following model defaults pattern
- Text input for template path + Save button
- Source file indicator

### Data Flow

```
User pastes markdown → POST /api/decks/create (SSE)
  → validate inputs
  → create_deck(outline_text, template, output, progress_callback)
    → parse slides
    → enhance each slide (if enabled)
    → build PPTX
  → ingest_deck(output_path, progress_callback)
    → export images, catalog, tags
  → SSE complete event with deck_id
→ UI refreshes deck list
```

### Out of Scope

- Image generation (`--image-gen`) — CLI only
- Multiple template management
- Outline editing/preview
- Template analysis display
