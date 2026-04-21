# PRD: Enhanced Reverse with Multimodal LLM

**Date:** 2026-03-03
**Author:** Matt
**Status:** Draft

---

## Summary

Add a `reverse --enhance` mode that uses multimodal LLMs to generate high-quality markdown outlines from PPTX files. The LLM sees each slide image alongside extracted text and produces a clean, structured outline — particularly valuable for diagram-heavy, image-rich, or visually complex slides where mechanical text extraction produces noise. Follows the same pattern as `create --enhance`.

## Motivation

- **What problem does this solve?** Mechanical text extraction (even with the quality fixes in `2026-03-03-prd-reverse-extraction-quality.md`) cannot interpret diagrams, charts, screenshots, or complex visual layouts. A slide showing a network topology diagram produces dozens of shape labels as flat bullets, but what the user needs is a concise description like "Network topology: 8 GPUs connected via Infinity Fabric to PCIe switches with 400G backend NICs."
- **Who benefits?** Users reversing visually rich decks for editing, content migration, or outline-based workflows.
- **What happens if we don't do this?** Diagram-heavy slides produce unusable outlines. Users must manually rewrite these sections, defeating the purpose of the reverse command.

## Requirements

### Must Have

- [ ] `reverse --enhance` flag triggers LLM-powered outline generation per slide
- [ ] Each slide sent to the LLM as an image + extracted text context
- [ ] LLM produces structured markdown outline (title, bullets, sub-bullets)
- [ ] Supports `--model`, `--gateway-config` flags (same as `create --enhance` and `analyze`)
- [ ] Falls back to text-only LLM analysis when no slide images are available
- [ ] Graceful degradation: if LLM call fails for a slide, fall back to mechanical extraction for that slide
- [ ] Progress output showing per-slide processing status
- [ ] `--images-dir` flag to specify pre-exported slide images (reuse existing images from `ingest`)

### Nice to Have

- [ ] Auto-export slide images when `--images-dir` is not specified (like `ingest` does)
- [ ] `--slides` flag to enhance only specific slide numbers (e.g., `--slides 5-10,15`)
- [ ] Cost/token estimate before processing (deck may have 50+ slides)

### Out of Scope

- Generating speaker notes during reverse (use `analyze --mode notes` separately)
- Layout type detection (LAYOUT directives) — that's for the forward `create --enhance` pipeline
- Automatic diagram recreation or SVG generation

---

## Design

### Approach

Add an `--enhance` code path to `convert_pptx_to_outline()` that, for each slide:

1. Loads the slide image (from `--images-dir` or auto-exported)
2. Sends the image + mechanically extracted text to the LLM
3. Parses the LLM response as structured markdown
4. Writes the LLM-generated outline instead of the mechanical extraction

The LLM prompt instructs the model to produce a concise outline with proper hierarchy, describing visual elements (diagrams, charts, screenshots) as structured bullet points rather than listing shape labels.

#### System Prompt

```
You are an expert at converting presentation slides into structured markdown outlines.
Given a slide image and its extracted text content, produce a clean markdown outline that:
- Uses the slide title as an H2 heading (## Title)
- Converts bullet points into a hierarchical list with proper indentation
- Describes diagrams, charts, and visual elements as concise bullet points
- Omits decorative text, watermarks, and slide furniture (page numbers, dates, footers)
- Preserves technical accuracy — do not invent content not present on the slide
- Keep descriptions concise: 1-2 sentences per visual element

Return ONLY the markdown outline. Do not include commentary or explanation.
```

#### Integration with Existing Patterns

The enhanced reverse reuses existing infrastructure:

- **`LLMClient`** from `outline2ppt/llm.py` — same client used by `analyze` and `enhancer`
- **`generate_text_with_image()`** — same multimodal API call used by `analyze_slide()`
- **`models.yaml` defaults** — new `reverse` operation key, defaulting to `claude-sonnet-4-6`
- **Image loading** — same `Slide{i}.PNG` convention used by `analyze` and `improve`
- **Gateway config** — same `--gateway-config` flag used everywhere

#### Processing Flow

```
For each slide in presentation:
  1. Get slide image path (--images-dir/Slide{i}.PNG)
  2. Extract text mechanically (existing extract_text_from_shape)
  3. If --enhance and image available:
       → Send image + text to LLM → use LLM output
     Elif --enhance and no image:
       → Send text-only to LLM → use LLM output
     Else:
       → Use mechanical extraction (existing behavior)
  4. Write to output markdown
```

#### Graceful Degradation

- If LLM call fails for a specific slide, log a warning and fall back to mechanical extraction
- If no images are available and `--enhance` is set, use text-only LLM mode (similar to `analyze.py` text-only fallback)
- If the LLM returns empty/unparseable output, fall back to mechanical extraction

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/ppt2outline.py` | Modified | Add `enhance` parameter, LLM integration, image loading, per-slide LLM calls |
| `outline2ppt/cli.py` | Modified | Add `--enhance`, `--model`, `--gateway-config`, `--images-dir` flags to `reverse` command |
| `models.yaml` | Modified | Add `reverse` operation default (e.g., `claude-sonnet-4-6`) |

### Data Model Changes

No data model changes.

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `reverse` | New option `--enhance` | Enable LLM-powered outline generation |
| `reverse` | New option `--model` | Specify LLM model (overrides models.yaml default) |
| `reverse` | New option `--gateway-config` | Path to gateway YAML config |
| `reverse` | New option `--images-dir` | Directory containing pre-exported slide images |

### Example Usage

```bash
# Basic reverse (mechanical extraction, no change)
python outline2ppt.py reverse deck.pptx outline.md

# Enhanced reverse with default model
python outline2ppt.py reverse deck.pptx outline.md --enhance

# Enhanced reverse with specific model and pre-exported images
python outline2ppt.py reverse deck.pptx outline.md --enhance --model gpt-4o --images-dir images/deck/

# Enhanced reverse through corporate gateway
python outline2ppt.py reverse deck.pptx outline.md --enhance --gateway-config gateway.yaml

# Combine with --no-notes
python outline2ppt.py reverse deck.pptx outline.md --enhance --no-notes
```

---

## UI Changes

No UI changes in this PRD. Future work may add an "Enhanced Reverse" option to the web UI's deck actions.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_ppt2outline.py` | `TestEnhancedReverse` | LLM integration (mocked), fallback behavior, image path resolution |
| `tests/test_ppt2outline.py` | `TestEnhancedReverseFallback` | Graceful degradation on LLM failure, missing images |

### Integration Tests

- E2E test (marked `@pytest.mark.e2e`): reverse a real deck with `--enhance` using live LLM, verify output quality
- Requires `AMD_LLM_KEY` or `OPENAI_API_KEY`

### Manual Testing

1. `reverse --enhance` on "Deploying AMD Instinct" deck — verify diagram slides produce meaningful descriptions
2. `reverse --enhance` on "Instinct Partitioning" deck — verify MI300 Logical Architecture slides describe the topology instead of listing shape labels
3. `reverse --enhance` on "Networking Advantages" deck — verify Pollara 400 feature slides produce clean outlines
4. `reverse --enhance` without `--images-dir` and without pre-exported images — verify text-only fallback works
5. Kill LLM mid-request — verify graceful fallback to mechanical extraction for remaining slides

---

## Changelog Entry

```markdown
### Added
- Reverse: `--enhance` flag for LLM-powered outline generation using multimodal AI
- Reverse: `--model`, `--gateway-config`, `--images-dir` options for enhanced mode
- Enhanced reverse describes diagrams and visual elements as structured bullet points
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add `reverse` default to `models.yaml` | `models.yaml` | -- |
| 2 | Add `--enhance`, `--model`, `--gateway-config`, `--images-dir` CLI flags | `outline2ppt/cli.py` | -- |
| 3 | Define reverse enhancement system prompt | `outline2ppt/ppt2outline.py` | -- |
| 4 | Add `enhance` parameter to `convert_pptx_to_outline()` with LLM integration | `outline2ppt/ppt2outline.py` | 1, 2, 3 |
| 5 | Implement per-slide LLM call with image + text context | `outline2ppt/ppt2outline.py` | 4 |
| 6 | Implement graceful degradation (LLM failure → mechanical fallback) | `outline2ppt/ppt2outline.py` | 5 |
| 7 | Add unit tests (mocked LLM) | `tests/test_ppt2outline.py` | 4, 5, 6 |
| 8 | Add E2E test (live LLM, marked `e2e`) | `tests/test_ppt2outline.py` | 4, 5, 6 |
| 9 | Manual validation with 3 test decks | -- | 7, 8 |
| 10 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Cost — a 50-slide deck with multimodal LLM calls could be expensive. Mitigation: document expected cost per slide, consider `--slides` flag for selective enhancement.
- **Risk:** LLM hallucination — the model may invent content not on the slide. Mitigation: prompt explicitly says "do not invent content"; include extracted text as grounding context.
- **Risk:** Rate limiting — many slides in rapid succession may hit API rate limits. Mitigation: sequential processing with retry/backoff (existing pattern in `analyze.py`).
- **Question:** Should enhanced reverse also generate speaker notes? Recommendation: No — keep it focused on outline quality. Use `analyze --mode notes` for notes.
- **Question:** Should the web UI expose enhanced reverse? Recommendation: defer to a future PRD after CLI validation.

---

## References

- Related PRDs: `docs/plans/2026-03-03-prd-reverse-extraction-quality.md` (mechanical fixes, should be implemented first)
- Related PRDs: `docs/plans/2026-03-02-prd-reverse-roundtrip-fix.md` (notes format)
- Existing multimodal pattern: `outline2ppt/analyze.py` (`analyze_slide()`)
- Existing enhancement pattern: `outline2ppt/enhancer.py` (`create --enhance`)
- Test decks: 3 uploaded PPTX files in `uploads/`
