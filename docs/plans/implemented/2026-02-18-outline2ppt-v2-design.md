# Outline2PPT v2 — Modular Package Design

**Date**: 2026-02-18
**Status**: Approved

## Overview

Refactor Outline2PPT from two standalone scripts into a modular Python package. Add capabilities for cataloging, versioning, remixing, and AI-analyzing slide decks. Integrate with corporate Azure API Gateway for LLM access. Add a lightweight web UI.

## Principles

- **KISS**: Simple solutions over clever ones
- **YAGNI**: Only build what's needed now
- **Graceful degradation**: Preserve the existing pattern where failures don't abort the whole operation
- **Provider agnosticism**: Keep the unified LLM interface, extend it for gateway auth

## 1. Package Structure

Refactor from two standalone scripts into a Python package:

```
outline2ppt/
├── __init__.py
├── cli.py              # All CLI commands (argparse or click)
├── llm.py              # LLMClient + gateway config
├── parser.py           # Markdown <-> slide parsing
├── enhancer.py         # AI enhancement pipeline
├── layouts.py          # Layout application functions
├── images.py           # Image gen (SVG/DALL-E) + image import
├── catalog.py          # SQLite catalog, hashing, versioning
├── remix.py            # Tag search, manifest, deck assembly
├── export.py           # CSV export, metadata extraction
├── analyze.py          # Multimodal slide review (feedback, notes, tags)
├── ppt2outline.py      # Reverse conversion (moved in)
├── web/
│   ├── app.py          # FastAPI app
│   ├── routes.py       # API endpoints
│   └── static/         # HTML/JS/CSS
└── schema.sql          # SQLite schema
```

Top-level entry points become thin wrappers:

```
outline2ppt.py  -> calls outline2ppt.cli
ppt2outline.py  -> calls outline2ppt.cli
```

## 2. LLM Gateway Integration (`llm.py`)

Refactor `LLMClient` to support the corporate Azure API Gateway.

### Gateway config via YAML file (`gateway.yaml`):

```yaml
gateway:
  base_url: "https://gateway.corp.example.com"
  auth_header: "X-Corp-Api-Key"
  auth_value_env: "CORP_GATEWAY_KEY"  # reads from env var
providers:
  anthropic:
    path: "/anthropic/v1"
  openai:
    path: "/openai/v1"
  gemini:
    path: "/google/v1"
```

### Behavior

- LLMClient constructor accepts optional gateway config. If present, it builds the base URL from gateway + provider path and injects the custom auth header.
- **Fallback**: Direct API keys still work when no gateway config is present (preserves current behavior).
- Strip down `MODEL_CONFIGS` to models actually available through the gateway + a handful of common direct-access models. The current 99-model registry is maintenance burden.

## 3. Catalog & Versioning (`catalog.py`)

SQLite database (single file, no server, zero config).

### Schema

```sql
decks (id, name, file_path, file_hash, slide_count, cataloged_at, updated_at)
slides (id, deck_id, position, title, content_text, content_hash,
        notes, image_path, created_at)
tags (id, name, source TEXT CHECK(source IN ('ai','taxonomy','manual')))
slide_tags (slide_id, tag_id)
taxonomy (id, name, category)  -- pre-defined tag list
```

### Slide Identity

`content_hash = sha256(normalized_title + normalized_text)`

When re-cataloging a deck, existing slides with the same hash are recognized; changed slides get a new hash and `updated_at` timestamp.

### Versioning

The catalog tracks the latest content_hash per (title, deck). When building a remix, the tool checks if any selected slide has a newer version in any cataloged deck and warns the user.

No separate version history table. Compare hashes across decks and timestamps.

## 4. Image Import & Association (`images.py`)

Convention: `images/<deck-name>/Slide1.png`, `Slide2.png`, etc.

- When cataloging a deck, the tool checks for a matching image directory and auto-associates images to slides by position number.
- No programmatic rendering. User exports from PowerPoint directly.
- Store `image_path` on the slide record in the catalog.

## 5. Multimodal Analysis (`analyze.py`)

Three operations, each a separate CLI command and API endpoint:

- **`analyze feedback`** — Sends slide image to a vision-capable model. Returns structured feedback on design, clarity, content density.
- **`analyze notes`** — Sends slide image + title. Returns generated speaker notes. Can write directly into the PPTX notes field.
- **`analyze tags`** — Sends slide image + optional taxonomy list. Returns suggested tags. In "taxonomy mode," constrains suggestions to the provided list.

All three use the same LLM call pattern with different system prompts. Single internal function with a `mode` parameter.

## 6. Tagging System

Two modes (user picks per-run):

- **Free-form**: LLM suggests tags based on slide content/image. Tags created with `source='ai'`.
- **Taxonomy**: Load a pre-defined tag list from a CSV or the `taxonomy` table. LLM picks from that list only. Tags stored with `source='taxonomy'`.
- **Manual**: User adds tags via CLI or web UI. `source='manual'`.

Tags are stored as PPTX custom properties on the slide (via python-pptx custom XML parts) and mirrored in SQLite for querying.

## 7. Remix System (`remix.py`)

### Discovery

```bash
python -m outline2ppt search --tags "security,architecture" --title-contains "zero trust"
```

Returns matching slides across all cataloged decks.

### Manifest Generation

```bash
python -m outline2ppt search --tags "security" --export-manifest security-remix.yaml
```

Produces:

```yaml
title: "Security Overview"
template: template.pptx
slides:
  - deck: "full-technical-deck.pptx"
    position: 5
    title: "Zero Trust Architecture"
  - deck: "compliance-deck.pptx"
    position: 12
    title: "SOC2 Requirements"
```

User edits this file to reorder, remove, or add slides.

### Assembly

```bash
python -m outline2ppt remix security-remix.yaml output.pptx
```

Pulls slides from source decks, checks for newer versions, assembles the new deck. Uses python-pptx XML part copying.

## 8. CSV Export (`export.py`)

```bash
python -m outline2ppt export deck.pptx --output slides.csv
python -m outline2ppt export --all --output catalog.csv
```

Columns: `deck_name, slide_number, title, notes, tags, content_hash, image_path, last_updated`

Uses stdlib `csv.DictWriter`. No pandas dependency.

## 9. Web UI (`web/`)

**FastAPI + htmx + Pico CSS** (or similar classless CSS). No React, no build step, no npm.

### Pages

- **Dashboard**: List cataloged decks, quick stats
- **Deck viewer**: Browse slides with thumbnails, view/edit tags, view notes
- **Search**: Filter by tags, title, deck
- **Remix builder**: Select slides, generate manifest, download assembled deck
- **Analyze**: Select a deck, run feedback/notes/tags analysis, view results
- **Settings**: Gateway config, taxonomy management

Single process, uvicorn dev server. No auth needed (local dev tool).

## 10. Testing

- **pytest** with unit tests for each module
- Focus on: parsing, hashing, catalog CRUD, manifest parsing, CSV export, LLM prompt construction
- Mock LLM calls (no real API hits in tests)
- Skip: layout rendering, web UI (manual testing), PPTX XML edge cases
- Target ~80% coverage on business logic modules

## 11. Existing Solutions Leveraged

| Need | Solution | Notes |
|------|----------|-------|
| Slide-to-image | PowerPoint export (manual) | Don't fight rendering fidelity |
| PPTX manipulation | `python-pptx` | Already in use |
| SVG to PNG | `cairosvg` | Already in use |
| SQLite | Raw `sqlite3` stdlib | No ORM needed |
| Web framework | FastAPI | Lightweight, auto-docs, async |
| Web interactivity | htmx | No JS framework needed |
| CSS | Pico CSS or Simple.css | Classless, no build step |
| Slide copying | python-pptx XML part copying | Known pattern, documented |

## 12. CLI Command Summary

```
outline2ppt create    outline.md template.pptx output.pptx [--enhance] [--model] [--image-gen]
outline2ppt reverse   input.pptx output.md
outline2ppt catalog   deck.pptx [--images-dir ./images/deck-name/]
outline2ppt search    --tags "x,y" --title-contains "z" [--export-manifest out.yaml]
outline2ppt remix     manifest.yaml output.pptx
outline2ppt analyze   deck.pptx --mode feedback|notes|tags [--taxonomy tags.csv]
outline2ppt export    deck.pptx --output slides.csv
outline2ppt serve     [--port 8000]
```

Existing `outline2ppt.py` and `ppt2outline.py` scripts continue to work as aliases for `create` and `reverse`.
