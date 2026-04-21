# PRD: Slide Notes Metadata & LLM Action Logging

**Date:** 2026-03-08
**Author:** Matt Elliott
**Status:** Draft

---

## Summary

Adopt structured metadata blocks in PowerPoint speaker notes to track content provenance, LLM actions, and generation parameters. Inspired by the slide-creator plugin's `[SLIDE-CREATOR-SOURCE]` pattern, this adds `[AIPPT-META]` JSON blocks to speaker notes during enhance, improve, and image generation operations. This creates a machine-readable audit trail embedded directly in the PPTX file, enabling round-trip editing, content tracing, and compliance tracking for AI-generated content.

## Motivation

- **Content provenance**: When AI enhances or rewrites slide content, there's currently no record of what the LLM changed, what model was used, or what the original content was. The `improve` command appends revision text to notes, but it's unstructured and not machine-parseable.
- **Round-trip editing**: The slide-creator plugin embeds full source data (prompts, layout, content) in notes, enabling extraction and re-generation. aippt would benefit from the same -- especially for re-enhancing or iterating on slides.
- **Compliance**: AI-generated images require tracking (who generated, when, what model, what prompt). Embedding this in the PPTX itself means the audit trail travels with the file.
- **Debugging**: When slides look wrong, knowing exactly what the LLM was asked and what it returned is invaluable.

## Requirements

### Must Have

- [ ] `[AIPPT-META]` JSON block appended to speaker notes during enhance, improve, and MCP image generation
- [ ] Metadata block contains: operation, model, timestamp, and operation-specific data
- [ ] Human-readable notes remain above the metadata block (separated by `---`)
- [ ] Metadata block is hidden from casual viewing (below the fold in Notes pane)
- [ ] `extract_metadata()` function to parse `[AIPPT-META]` blocks from existing PPTX notes
- [ ] Metadata preserved across enhance/improve cycles (new entries appended, old preserved)
- [ ] Works with existing notes content (doesn't clobber manually written notes)

### Nice to Have

- [ ] CLI command `aippt metadata <deck.pptx>` to dump all embedded metadata as JSON
- [ ] Web UI indicator showing which slides have AI-generated content
- [ ] Metadata stored in catalog DB alongside slide records

### Out of Scope

- Full slide plan reconstruction from metadata (slide-creator's extract_plan.py approach). Our metadata is an audit trail, not a rebuild recipe.
- Metadata encryption or access control
- Metadata in PPTX custom properties (XML-level; notes are simpler and more portable)

---

## Design

### Approach

Add a `metadata.py` module that handles writing and reading structured metadata blocks in PPTX speaker notes. Each AI operation (enhance, improve, image generation) appends a timestamped JSON entry to the notes. The format is designed to be grep-friendly, human-ignorable, and machine-parseable.

### Metadata Format

```
Speaker notes written by the LLM or user go here.
They can be multiple paragraphs.

---
[AIPPT-META]
[
  {
    "operation": "enhance",
    "timestamp": "2026-03-08T14:30:00Z",
    "model": "claude-sonnet-4-6",
    "layout_selected": "two_column",
    "original_content_hash": "abc123...",
    "directives": {"LAYOUT": "two_column", "IMAGE": null}
  },
  {
    "operation": "image_generate",
    "timestamp": "2026-03-08T14:30:05Z",
    "model": "gemini-3.1-flash-image-preview",
    "server": "txt2img",
    "prompt_hash": "def456...",
    "classification": "internal",
    "image_path": "images/deck/slide_03_gen.png"
  },
  {
    "operation": "improve",
    "timestamp": "2026-03-08T15:00:00Z",
    "model": "claude-sonnet-4-6",
    "pass": 1,
    "focus": "brevity",
    "changes_summary": "Condensed 5 bullets to 3, removed redundant qualifier"
  }
]
[/AIPPT-META]
```

### Operation-Specific Fields

| Operation | Fields |
|-----------|--------|
| `enhance` | `model`, `layout_selected`, `original_content_hash`, `directives` |
| `improve` | `model`, `pass`, `focus`, `changes_summary` |
| `image_generate` | `model`, `server`, `prompt_hash`, `prompt` (first 200 chars), `classification`, `image_path` |
| `analyze` | `model`, `mode` (feedback/notes/tags/improvements), `result_summary` |

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `aippt/metadata.py` | **New** | `append_metadata()`, `extract_metadata()`, `format_notes_with_metadata()` |
| `aippt/enhancer.py` | Modified | Call `append_metadata()` after enhancement with operation details |
| `aippt/improve.py` | Modified | Replace unstructured revision notes with `append_metadata()` call |
| `aippt/cli.py` | Modified | Pass metadata context through `_add_slide()` |
| `aippt/images.py` | Modified | Call `append_metadata()` after MCP image generation |

### Key Functions

```python
# aippt/metadata.py

def append_metadata(slide, operation: str, **kwargs) -> None:
    """Append a metadata entry to the slide's speaker notes.

    If no [AIPPT-META] block exists, creates one after a --- separator.
    If one exists, appends to the existing JSON array.
    """

def extract_metadata(slide) -> list[dict]:
    """Extract all metadata entries from a slide's speaker notes.

    Returns an empty list if no [AIPPT-META] block is found.
    """

def extract_notes_text(slide) -> str:
    """Extract just the human-readable notes (before the --- separator)."""

def format_notes_with_metadata(
    notes_text: str, metadata_entries: list[dict]
) -> str:
    """Combine human-readable notes with a metadata block."""
```

### Data Model Changes

No schema changes required. Metadata lives in the PPTX file itself, not the database.

Future work (Nice to Have) could add a `metadata` JSON column to the `slides` table to cache extracted metadata for search/display, but that's out of scope here.

---

## CLI Changes

### New Commands

```
aippt metadata <deck.pptx>              # Dump all slide metadata as JSON
aippt metadata <deck.pptx> --slide 3    # Metadata for a specific slide
```

### Example Usage

```bash
# View all AI operations performed on a deck
aippt metadata output.pptx
# Output:
# [
#   {"slide": 1, "operations": [...]},
#   {"slide": 3, "operations": [{"operation": "enhance", ...}, {"operation": "image_generate", ...}]},
#   ...
# ]

# Check what model was used for a specific slide
aippt metadata output.pptx --slide 3
```

---

## UI Changes

No UI changes in this PRD.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_metadata.py` | `TestAppendMetadata` | Append to empty notes, append to existing notes, append to existing metadata block |
| `tests/test_metadata.py` | `TestExtractMetadata` | Extract from notes with metadata, no metadata, malformed metadata |
| `tests/test_metadata.py` | `TestExtractNotesText` | Get human notes only, ignore metadata block |
| `tests/test_metadata.py` | `TestFormatNotes` | Combine notes + metadata, empty notes + metadata |

### Integration Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_enhancer.py` | `TestEnhanceMetadata` | Verify enhance writes metadata to slide notes |
| `tests/test_improve.py` | `TestImproveMetadata` | Verify improve appends metadata entry |

### Manual Testing

1. Run `aippt create --enhance` -- verify metadata block appears in slide notes
2. Run `aippt improve` on the same deck -- verify new metadata entry appended (not overwritten)
3. Run `aippt metadata deck.pptx` -- verify JSON output shows all operations
4. Open PPTX in PowerPoint -- verify human-readable notes display correctly above the metadata

---

## Changelog Entry

```markdown
### Added
- Structured `[AIPPT-META]` blocks in speaker notes tracking AI operations (model, timestamp, parameters)
- `aippt metadata` command to extract AI operation history from PPTX files
- Content provenance tracking for enhance, improve, and image generation operations

### Changed
- `improve` command now uses structured metadata instead of unstructured revision text in notes
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Create metadata module with append/extract/format functions | `metadata.py`, `tests/test_metadata.py` | -- |
| 2 | Integrate metadata into enhance pipeline | `enhancer.py`, `cli.py`, `tests/test_enhancer.py` | 1 |
| 3 | Migrate improve revision notes to metadata | `improve.py`, `tests/test_improve.py` | 1 |
| 4 | Integrate metadata into MCP image generation | `images.py` | 1, MCP image gen PRD |
| 5 | Add `aippt metadata` CLI command | `cli.py`, `tests/test_cli.py` | 1 |

---

## Risks & Open Questions

- **Risk:** Large metadata blocks in notes could be visually distracting in PowerPoint -- mitigated by placing below `---` separator (below the fold in Notes pane)
- **Risk:** Metadata format changes between versions -- mitigated by using a JSON array that's append-only; new fields are additive
- **Question:** Should `extract_metadata()` be fault-tolerant (return partial results from malformed JSON) or strict? Starting fault-tolerant with warnings.
- **Question:** Should the improve command continue appending its human-readable revision summary in addition to the structured metadata? Leaning toward keeping both: the human summary above the fold, the structured data below.

---

## References

- Related PRDs: `docs/plans/2026-03-08-mcp-image-generation.md` (companion -- image generation metadata)
- Related PRDs: `docs/plans/2026-03-06-mcp-client-infrastructure.md` (prerequisite for MCP operations)
- Inspiration: `~/.cursor/skills-cursor/slide-creator/scripts/build_pptx.py` (`_add_notes()` function with `[SLIDE-CREATOR-SOURCE]` blocks)
- Inspiration: `~/.cursor/skills-cursor/slide-creator/scripts/extract_plan.py` (round-trip extraction from notes)
