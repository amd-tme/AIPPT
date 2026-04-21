# PRD: Enhanced Reverse (LLM-Powered Outline Generation)

**Date:** 2026-02-27
**Author:** Matt
**Status:** Draft

---

## Summary

Add an `--enhance` flag to the existing `reverse` command that uses multimodal LLM analysis to produce higher-quality markdown outlines from PowerPoint decks. The mechanical extractor already captures titles and bullet text from PPTX XML; the LLM enhancement summarizes/cleans up that text and describes visual elements (diagrams, charts, screenshots) that the mechanical pass misses entirely. The output is a markdown outline in the same format consumed by `outline2ppt create`, enabling a round-trip workflow for reviewing, updating, and regenerating decks.

## Motivation

- **Problem:** The current `reverse` command does mechanical text extraction only. Slides with diagrams, charts, or image-heavy layouts produce sparse or empty outlines. Even text-heavy slides often produce noisy output (duplicated placeholders, raw table dumps, etc.) that doesn't read well as an outline.
- **Who benefits:** Users who want to summarize existing decks to identify outdated or missing material, then edit the outline and regenerate a new deck with `create`.
- **If we don't do this:** Users must manually write outlines from scratch when working with existing decks, losing the content that's already there.

## Requirements

### Must Have

- [ ] `--enhance` flag on `reverse` command enables LLM-powered outline generation
- [ ] Per-slide LLM calls using slide images (multimodal) when available
- [ ] Text-only LLM fallback when no image is available for a slide
- [ ] Without `--enhance`, the `reverse` command behaves exactly as it does today
- [ ] Output format matches what `parse_outline()` expects (H1 sections / H2 slides / bullets)
- [ ] `--model`, `--gateway-config`, `--api-key` flags for LLM configuration
- [ ] `--images-dir` flag to specify slide image directory
- [ ] Graceful per-slide error handling (one slide's LLM failure doesn't abort the deck)

### Nice to Have

- [ ] Progress indicator showing which slide is being processed
- [ ] `--no-notes` flag still works with enhanced mode (exclude notes from output)

### Out of Scope

- Per-deck holistic pass for narrative coherence
- Automatic image export (user runs `export-images` or `ingest` first)
- Diffing original vs. generated outlines
- Round-trip fidelity testing or metrics

---

## Design

### Approach

Add LLM enhancement logic directly to `ppt2outline.py`. The existing `convert_pptx_to_outline()` function gains an optional LLM client parameter. When provided, each slide goes through a two-step process:

1. **Mechanical extraction** (existing): titles, bullets, notes, sections from PPTX XML
2. **LLM enhancement** (new): the extracted text + slide image are sent to the LLM, which returns a clean markdown outline entry

The LLM is prompted to produce markdown in the exact format `parse_outline()` expects: an H2 heading for the title followed by bullet points for content. Section headers (H1) come from PPTX section metadata, not the LLM.

The `analyze.py` module's image placeholder detection (`_is_placeholder_image`) is reused to decide whether to use multimodal or text-only prompts.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/ppt2outline.py` | Modified | Add `enhance_slide_outline()` function with system/user prompts; integrate into `convert_pptx_to_outline()` via optional `llm_client` + `images_dir` params |
| `outline2ppt/cli.py` | Modified | Add `--enhance`, `--model`, `--images-dir`, `--gateway-config`, `--api-key` args to `reverse` subparser; instantiate LLMClient when `--enhance` is set |

### Data Model Changes

No data model changes.

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `reverse` | New option `--enhance` | Enable LLM-powered outline enhancement |
| `reverse` | New option `--model` | LLM model name (required with `--enhance`) |
| `reverse` | New option `--images-dir` | Directory containing slide PNG images |
| `reverse` | New option `--gateway-config` | Path to gateway YAML config |
| `reverse` | New option `--api-key` | Explicit API key for LLM provider |

### Example Usage

```bash
# Plain reverse (unchanged behavior)
python outline2ppt.py reverse deck.pptx outline.md

# Enhanced reverse with slide images
python outline2ppt.py reverse deck.pptx outline.md --enhance --model gpt-4o --images-dir images/deck/

# Enhanced reverse via corporate gateway
python outline2ppt.py reverse deck.pptx outline.md --enhance --model gpt-4o --gateway-config gateway.yaml

# Enhanced reverse, text-only (no images available)
python outline2ppt.py reverse deck.pptx outline.md --enhance --model gpt-4o

# Typical workflow: export images first, then enhanced reverse
python outline2ppt.py export-images deck.pptx images/deck/
python outline2ppt.py reverse deck.pptx outline.md --enhance --model gpt-4o --images-dir images/deck/
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_ppt2outline.py` | `TestEnhancedReverse` | `enhance_slide_outline()` with mocked LLM, image/text-only fallback, error handling |

### Integration Tests

Add enhanced reverse test to `tests/test_integration.py` or `tests/test_e2e_pipeline.py` that runs the full round-trip: create outline -> generate PPTX -> enhanced reverse -> verify output is parseable by `parse_outline()`.

### Manual Testing

1. Run `reverse --enhance` on a deck with exported images -- verify diagrams and charts appear as descriptive bullets in the outline
2. Run `reverse --enhance` without `--images-dir` -- verify text-only fallback works and output is clean
3. Run `reverse` without `--enhance` -- verify behavior is unchanged
4. Feed the enhanced reverse output back into `create` -- verify it produces a valid PPTX
5. Run on a deck with a failing slide image -- verify other slides still complete

---

## Changelog Entry

```markdown
### Added
- `reverse --enhance` flag for LLM-powered outline generation from PowerPoint decks
- Multimodal analysis describes diagrams, charts, and visual elements as outline bullets
- Text-only fallback when slide images are not available
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add `enhance_slide_outline()` function with system/user prompts (image + text-only variants) | `ppt2outline.py` | -- |
| 2 | Integrate LLM enhancement into `convert_pptx_to_outline()` flow | `ppt2outline.py` | 1 |
| 3 | Add CLI args and wire up LLMClient in `cmd_reverse()` | `cli.py` | 2 |
| 4 | Add unit tests for enhanced reverse (mocked LLM) | `tests/test_ppt2outline.py` | 1, 2 |
| 5 | Add integration/round-trip test | `tests/test_e2e_pipeline.py` | 3 |
| 6 | Update CHANGELOG | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** LLM output may not perfectly match `parse_outline()` expected format -- mitigation: strong system prompt with explicit format instructions + post-processing to normalize markdown headers/bullets
- **Risk:** Large decks (50+ slides) will be slow/expensive with per-slide LLM calls -- mitigation: this matches the existing `analyze` pattern; users already expect this for LLM-powered features
- **Question:** Should we add a `--concurrency` flag for parallel LLM calls? -- deferring to a future enhancement to keep scope small

---

## References

- Related modules: `outline2ppt/analyze.py` (multimodal analysis pattern), `outline2ppt/parser.py` (outline format spec)
- Existing command: `outline2ppt reverse` (mechanical extraction)
