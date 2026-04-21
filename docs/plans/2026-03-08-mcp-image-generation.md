# PRD: MCP Text-to-Image Generation

**Date:** 2026-03-08
**Author:** Matt Elliott
**Status:** Draft

---

## Summary

Integrate the internal txt2img MCP server as an image generation source in aippt's `--enhance` pipeline. When enabled, the LLM can request AI-generated images for slides via the MCP server's `generate_slide_image` tool. Generated images are placed on slides like existing IMAGE: directive images. Because AI-generated images are not yet approved for public use, any slide containing generated images automatically gets a disclaimer text box and a disclaimer note in speaker notes.

## Motivation

- ~95% of slide images come from screenshots or diagrams; the remaining 5% need custom illustrations that are currently manual work
- The internal txt2img MCP server (NanoBanana/Gemini models) produces high-quality slide-appropriate images and is already deployed
- OAuth authentication on the MCP server satisfies Legal's requirement to track who generates each image
- The MCP client infrastructure layer (Task: `feature/mcp-client-infrastructure`) provides the connection machinery; this PRD consumes it

## Requirements

### Must Have

- [ ] New image generation mode `--image-gen mcp` alongside existing `none`, `svg`, `dalle`
- [ ] LLM in enhance pipeline can request image generation by outputting `IMAGE_PROMPT: <description>` in its response (analogous to existing `LAYOUT:` directives)
- [ ] Generated images saved to the images directory with consistent naming (`slide_NN_gen.png`)
- [ ] Prompt-hash caching: identical prompts skip regeneration (same approach as colleague's `cache_key()`)
- [ ] **Disclaimer on generated slides**: any slide with an AI-generated image gets:
  - A small text box at the bottom: "AI-Generated Image -- Not Approved for External Use"
  - Speaker notes prepended with: "[AI-GENERATED] This slide contains AI-generated imagery not approved for external distribution."
- [ ] OAuth authentication via MCP client layer (browser-based, token cached at `~/.aippt/mcp-tokens/`)
- [ ] Classification parameter required (default: `internal`) -- passed through to MCP server
- [ ] Graceful fallback: if MCP server is unavailable or image generation fails, slide renders normally without image (existing behavior for `diagram` layout with no image)

### Nice to Have

- [ ] `--image-model` flag to select model (default from models.yaml `image` operation)
- [ ] `--image-aspect-ratio` flag (default: `16:9`)
- [ ] Concurrent image generation for multi-slide decks (ThreadPoolExecutor like colleague's script)
- [ ] Progress callback during image generation ("Generating image for slide 3...")

### Out of Scope

- Full-slide image rendering (colleague's approach where the image IS the slide). We generate images that are placed within template-based slides.
- Image editing/refinement after generation
- Round-trip extraction of image prompts from existing PPTX (covered by slide notes metadata PRD)
- Non-MCP image generation backends (existing SVG/DALL-E paths are unchanged)

---

## Design

### Approach

Add an MCP image generation pathway to `aippt/images.py` that uses `MCPManager` from `aippt/mcp.py` to call the txt2img server's `generate_slide_image` tool. The enhance pipeline in `enhancer.py` gains a new directive (`IMAGE_PROMPT:`) that the LLM can emit. When present, the pipeline generates an image via MCP before building the slide, then applies it using the existing `IMAGE:` code path plus a disclaimer overlay.

### Integration Points

**1. Enhancer (LLM decides when to generate images)**

The enhance system prompt gets updated to inform the LLM that image generation is available:

```
When image generation is enabled (MCP mode), you may include:
IMAGE_PROMPT: A detailed description of a diagram or illustration...

Use IMAGE_PROMPT when a slide would benefit from a custom diagram,
architecture visualization, or conceptual illustration. Do NOT use
for every slide -- only when visual content adds clear value.
```

The LLM outputs `IMAGE_PROMPT: <description>` in its response. `parse_llm_suggestions()` in `parser.py` extracts it alongside NARRATIVE/LAYOUT/VISUALS/TALKING_POINTS.

**2. Image Generation (MCP call)**

New function in `images.py`:

```python
async def generate_mcp_image(
    prompt: str,
    output_path: str,
    mcp_manager: MCPManager,
    server_name: str = "txt2img",
    model: str = "gemini-3.1-flash-image-preview",
    classification: str = "internal",
    aspect_ratio: str = "16:9",
) -> str | None:
    """Generate an image via MCP txt2img server. Returns path or None on failure."""
```

Caching: `sha256(model + prompt + aspect_ratio)` as cache key, stored in `~/.cache/aippt/mcp-images/`.

**3. Slide Building (disclaimer)**

When a slide uses an AI-generated image, `_add_slide()` in `cli.py`:
- Applies the image using existing `apply_placeholder_image()` or picture insertion
- Adds a disclaimer text box at the bottom of the slide (small, gray text)
- Prepends the disclaimer to speaker notes

**4. Configuration**

The MCP server must be configured in `mcp_servers.json`:

```json
{
  "mcpServers": {
    "txt2img": {
      "url": "https://mcp-platform.amd.com/mcp/txt2img/mcp",
      "auth": "oauth"
    }
  }
}
```

The server name `txt2img` is the default; overridable via `--mcp-server` flag.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `aippt/images.py` | Modified | Add `generate_mcp_image()`, prompt-hash caching, MCP client integration |
| `aippt/enhancer.py` | Modified | Update SYSTEM_PROMPT for image generation; add IMAGE_PROMPT to LLM instructions |
| `aippt/parser.py` | Modified | Extract `IMAGE_PROMPT:` directive from LLM response in `parse_llm_suggestions()` |
| `aippt/cli.py` | Modified | Add `--image-gen mcp` option, `--classification` flag, disclaimer overlay logic in `_add_slide()` |
| `aippt/layouts.py` | Modified | Add `add_disclaimer_textbox()` for AI-generated image disclaimer |

### Data Model Changes

No data model changes. Image generation metadata is stored in speaker notes (see slide notes metadata PRD).

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `aippt create` | New `--image-gen mcp` value | Enables MCP-based image generation during enhance |
| `aippt create` | New `--classification` flag | Required when `--image-gen mcp`; default `internal` |
| `aippt create` | New `--mcp-server` flag | MCP server name from config; default `txt2img` |

### Example Usage

```bash
# Enhanced deck with MCP image generation
aippt create outline.md template.pptx output.pptx \
  --enhance --image-gen mcp --classification internal

# With specific model
aippt create outline.md template.pptx output.pptx \
  --enhance --image-gen mcp --image-model gemini-3.1-flash-image-preview

# MCP images but non-default server name
aippt create outline.md template.pptx output.pptx \
  --enhance --image-gen mcp --mcp-server my-image-server
```

---

## UI Changes

No UI changes in this PRD. Web UI image generation would be a follow-up.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_images.py` | `TestMCPImageGeneration` | generate_mcp_image with mocked MCPManager, caching, error handling |
| `tests/test_parser.py` | `TestImagePromptParsing` | IMAGE_PROMPT extraction from LLM response |
| `tests/test_enhancer.py` | `TestMCPImagePrompt` | System prompt includes image gen guidance when mode is mcp |
| `tests/test_cli.py` | `TestDisclaimerOverlay` | Disclaimer text box and notes added for generated images |

### Manual Testing

1. Run `aippt create` with `--enhance --image-gen mcp` -- verify OAuth browser flow triggers on first use
2. Verify generated images appear on slides with disclaimer text
3. Re-run same outline -- verify prompt cache hits (no regeneration)
4. Run without MCP server configured -- verify graceful fallback with warning

---

## Changelog Entry

```markdown
### Added
- MCP text-to-image generation (`--image-gen mcp`) via internal txt2img server
- AI-generated image disclaimer on slides (required for internal compliance)
- Prompt-hash caching for MCP image generation
- `--classification` flag for image generation compliance tracking
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add IMAGE_PROMPT extraction to parser | `parser.py`, `tests/test_parser.py` | -- |
| 2 | Update enhancer system prompt for MCP image mode | `enhancer.py`, `tests/test_enhancer.py` | -- |
| 3 | Add generate_mcp_image and prompt-hash caching | `images.py`, `tests/test_images.py` | MCP infra branch |
| 4 | Add disclaimer text box helper | `layouts.py`, `tests/test_layouts.py` | -- |
| 5 | Wire up CLI: --image-gen mcp, --classification, disclaimer in _add_slide | `cli.py` | 1, 2, 3, 4 |
| 6 | Integration testing with mocked MCP server | `tests/test_cli.py` | 5 |

---

## Risks & Open Questions

- **Risk:** MCP server rate limiting during large deck generation -- mitigated by prompt-hash caching and exponential backoff (same pattern as colleague's script)
- **Risk:** OAuth token expiry mid-generation -- FastMCP Client handles token refresh automatically
- **Question:** Should the disclaimer text be configurable, or always the fixed legal text? Starting with fixed text; can be made configurable via config file later.
- **Question:** Should generated images be stored in the slide catalog DB? Deferring to the slide notes metadata PRD for provenance tracking.

---

## References

- Related PRDs: `docs/plans/2026-03-06-mcp-client-infrastructure.md` (prerequisite)
- Related PRDs: `docs/plans/2026-03-08-slide-notes-metadata.md` (companion)
- Internal: `~/.cursor/skills-cursor/slide-creator/scripts/generate_image.py` (reference implementation)
- MCP server: `https://mcp-platform.amd.com/mcp/txt2img/mcp`
