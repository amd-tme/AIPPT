# PRD: Oversized Image Handling for LLM Pipelines

**Date:** 2026-03-04
**Author:** Matt
**Status:** Draft

---

## Summary

Slide images exported as full-resolution PNGs can exceed LLM API size limits (typically 5MB for Anthropic via gateway, 20MB for OpenAI). When this happens, multimodal API calls fail and pipelines silently fall back to text-only mode, degrading output quality. This PRD adds automatic image resizing so that all vision-dependent pipelines (reverse, analyze, improve) work reliably regardless of source image size.

## Motivation

- **What problem does this solve?** Exported slide PNGs at 1920×1080 typically range 500KB–2MB, but image-heavy slides (photos, dense charts) can reach 5–7MB. The AMD gateway returned `400 Bad Request` for a 6.4MB image during enhanced reverse testing. The pipeline fell back to text-only, producing lower-quality output without the user realizing.
- **Who benefits?** End users running `reverse --enhance`, `analyze`, or `improve` — especially on decks with large embedded images or high-resolution exports.
- **What happens if we don't do this?** Multimodal analysis silently degrades to text-only on oversized slides. Users get inconsistent quality across slides in the same deck with no clear indication of why.

## Requirements

### Must Have

- [ ] Pre-transmission size check in `LLMClient.generate_text_with_image()` — resize images that exceed a configurable threshold before base64-encoding
- [ ] Resize uses Pillow (already a dependency) to scale down and/or convert PNG→JPEG to reduce file size
- [ ] Logging: INFO-level message when an image is resized, including original size, new size, and slide reference
- [ ] Configurable max size with a sensible default (4MB raw file size — stays under 5MB API limits with base64 overhead margin)
- [ ] Unit tests for the resize logic

### Nice to Have

- [ ] Post-export size check in `cmd_export_images()` / ingest pipeline — warn about images that will need resizing at API call time
- [ ] CLI flag `--max-image-size` on `reverse`, `analyze`, `improve` commands to override the default
- [ ] Dry-run mode that reports which slides would be resized without calling the API

### Out of Scope

- Changing the default export resolution (1920×1080) — that's a separate concern
- Re-architecting the export pipeline to produce JPEG by default
- Server-side image hosting / URL-based image submission (would require API changes)

---

## Design

### Approach

Add a `_prepare_image_for_api()` helper in `llm.py` that checks file size and, if needed, resizes using Pillow. This function is called inside `generate_text_with_image()` before base64 encoding, making it transparent to all callers (reverse, analyze, improve).

Resize strategy:
1. Check raw file size against threshold (default 4MB)
2. If over threshold, open with Pillow and progressively reduce:
   a. First try: save as JPEG at quality=85 (PNG→JPEG conversion alone often achieves 3–5x reduction)
   b. If still over: scale dimensions down by 50% and re-save
   c. If still over: reduce JPEG quality to 60 and re-save
3. Return the (possibly modified) image bytes and updated media type
4. Use an in-memory `BytesIO` buffer — never modify the original file on disk

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/llm.py` | Modified | Add `_prepare_image_for_api()` helper; call it in `generate_text_with_image()` before base64 encoding |

### Data Model Changes

No data model changes.

---

## CLI Changes

No new commands. The resize is automatic and transparent.

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `reverse` | New option `--max-image-size` | Max image file size in MB before resizing (default: 4) |
| `analyze` | New option `--max-image-size` | Same as above |
| `improve` | New option `--max-image-size` | Same as above |

The `--max-image-size` flag is nice-to-have. The default behavior (auto-resize at 4MB) requires no user action.

### Example Usage

```bash
# Default: auto-resizes images over 4MB
python outline2ppt.py reverse deck.pptx output.md --enhance --images-dir images/deck/

# Override threshold (e.g., stricter gateway with 2MB limit)
python outline2ppt.py reverse deck.pptx output.md --enhance --max-image-size 2
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_llm.py` | `TestPrepareImageForApi` | `_prepare_image_for_api()` — under threshold (no-op), PNG over threshold (converted to JPEG), large image (scaled down), already-JPEG (quality reduction only) |

### Integration Tests

No new integration tests. Existing `test_ppt2outline.py` enhanced-reverse tests exercise the full path with mocked LLM calls.

### Manual Testing

1. Run enhanced reverse on the TechJam Vienna deck — slide 1 (6.4MB PNG) should now succeed with image, not fall back to text-only
2. Check log output shows resize message for slide 1: `"Resized image for API: 6.4MB → X.XMB (JPEG quality=85)"`
3. Compare enhanced reverse output for slide 1 — should include visual descriptions that text-only mode misses

---

## Changelog Entry

```markdown
### Fixed
- Automatic image resizing for LLM API calls — slides with images over 4MB (e.g., photo-heavy slides) are now resized before submission instead of silently falling back to text-only mode
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add `_prepare_image_for_api()` helper with Pillow-based resize | `outline2ppt/llm.py` | -- |
| 2 | Integrate helper into `generate_text_with_image()` before base64 encoding | `outline2ppt/llm.py` | 1 |
| 3 | Add `max_image_bytes` parameter to `LLMClient.__init__()` / `generate_text_with_image()` | `outline2ppt/llm.py` | 1 |
| 4 | Add unit tests for resize logic | `tests/test_llm.py` | 1, 2 |
| 5 | (Nice-to-have) Add `--max-image-size` CLI flag to reverse/analyze/improve | `outline2ppt/cli.py` | 3 |
| 6 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** JPEG conversion loses transparency (PNG alpha channel) — mitigation: slide screenshots never use transparency, so this is a non-issue for the expected input
- **Risk:** Aggressive resizing could degrade LLM analysis quality — mitigation: the progressive strategy tries format conversion first (lossless quality), only scales dimensions as a last resort; 1920×1080→960×540 is still plenty for vision models
- **Question:** Should the default threshold be 4MB or lower? The Anthropic direct API allows up to 20MB per image, but the AMD gateway enforces 5MB. Using 4MB provides margin for both the raw file and base64 overhead (~33%). Gateway-specific limits could be read from `gateway.yaml` in the future.
- **Question:** Should we also resize images in the `analyze.py` placeholder detection path? Currently `_is_placeholder_image()` only checks for images that are too *small* (<5KB). Adding an upper-bound check there would be redundant since `generate_text_with_image()` handles it, but a warning log could be useful.

---

## References

- Related: `docs/plans/2026-03-03-enhanced-reverse-implementation.md` (enhanced reverse feature that surfaced this issue)
- Anthropic API docs: base64 image limit is 100MB per request, but gateway proxies often impose stricter limits
- Pillow docs: `Image.save()` with `quality` parameter for JPEG compression
