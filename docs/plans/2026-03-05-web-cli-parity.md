# PRD: Web UI / CLI Feature Parity for Deck Creation

**Date:** 2026-03-05
**Author:** Matt
**Status:** Draft

---

## Summary

The web UI's "Create Presentation" feature supports only a subset of the CLI's `create` command capabilities. Most critically, IMAGE: directives are silently stripped because `outline_path` is never passed to `create_deck()`. This PRD brings the web UI to feature parity with the CLI for the features that make sense in a web context.

## Motivation

- **What problem does this solve?** Users who create decks through the web UI get a degraded experience compared to the CLI. IMAGE: directives fail silently, image generation is unavailable, and there's no way to preview a subset of slides before committing to a full enhanced run.
- **Who benefits?** Web UI users — the web UI is the primary interface for non-technical users.
- **What happens if we don't do this?** Users discover features don't work in the web UI only after waiting for a full generation run, and must fall back to the CLI for anything beyond basic outlines.

## Requirements

### Must Have

- [ ] IMAGE: directives work in web-generated decks (resolve paths, embed images)
- [ ] Uploaded `.md` files are saved to disk so `outline_path` can be passed to `create_deck()`
- [ ] Images referenced by IMAGE: directives can be uploaded alongside the outline
- [ ] `outline_path` parameter passed to `create_deck()` from web route

### Nice to Have

- [ ] Test mode: optional slide count limit (equivalent to CLI `--test N`)
- [ ] Image generation mode selector (none/claude/dalle) in the create form
- [ ] Remove unused `title` form parameter from the endpoint

### Out of Scope

- Per-deck template selection (Settings-level template config is sufficient)
- Direct API key / base URL input fields (gateway config covers this)
- `--analyze-template` (CLI-only developer tool)
- Drag-and-drop image uploads (standard file input is sufficient)

---

## Design

### Approach

The core fix is saving uploaded outline files to disk and passing the path to `create_deck()`. For IMAGE: directives to work, image files must also be accessible at the paths referenced in the outline. This requires either:

1. Uploading images alongside the outline (multi-file upload), or
2. Referencing images already on the server (e.g., in `images/` or `uploads/`)

We'll support both: a multi-file upload for bundled outlines+images, and path resolution against the server's working directory for server-side images.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `aippt/web/routes.py` | Modified | Save uploaded .md to disk, accept image uploads, pass `outline_path` and `image_gen` to `create_deck()` |
| `aippt/web/static/index.html` | Modified | Add image file upload input, optional test mode field, image-gen selector |

### Data Model Changes

No data model changes.

---

## Key Changes

### 1. Save Uploaded Outline to Disk

Currently the web route reads the uploaded `.md` file content as text and discards the file. Instead, save it to `uploads/` so `outline_path` is available:

```python
# routes.py - in create_deck_stream()
if outline_file and outline_file.filename:
    content = await outline_file.read()
    md_text = content.decode("utf-8")
    # Save to disk for IMAGE: directive resolution
    outline_save_path = os.path.join(uploads_dir, f"{_short_id}_{outline_file.filename}")
    with open(outline_save_path, 'w') as f:
        f.write(md_text)
else:
    outline_save_path = None
```

Then pass to `create_deck()`:

```python
result = create_deck(
    outline_text=md_text,
    template_path=template_path,
    output_path=output_path,
    enhance=enhance,
    model=model,
    gateway_config=gateway_config,
    progress_callback=create_progress,
    outline_path=outline_save_path,  # NEW
)
```

### 2. Image File Uploads

Add a multi-file input for images. Uploaded images are saved to a subdirectory alongside the outline so relative paths resolve correctly:

```python
# routes.py - new parameter
image_files: List[UploadFile] = File([])

# Save images relative to outline
if outline_save_path and image_files:
    outline_dir = os.path.dirname(outline_save_path)
    for img in image_files:
        img_path = os.path.join(outline_dir, img.filename)
        os.makedirs(os.path.dirname(img_path), exist_ok=True)
        with open(img_path, 'wb') as f:
            f.write(await img.read())
```

For outlines that reference images in subdirectories (e.g., `IMAGE: memes/photo.jpg`), the frontend should preserve directory structure. The simplest approach: accept a `.zip` upload containing the outline and images, or accept images with path-preserving filenames.

### 3. Pasted Text with IMAGE: Directives

When users paste outline text directly (not upload a file), IMAGE: directives can only reference server-side paths. The outline text is saved to a temp file in `uploads/` so path resolution works relative to the project root:

```python
if not outline_save_path and md_text:
    # Save pasted text to temp file for IMAGE: resolution
    outline_save_path = os.path.join(uploads_dir, f"{_short_id}_pasted.md")
    with open(outline_save_path, 'w') as f:
        f.write(md_text)
```

### 4. Image Generation Selector (Nice to Have)

Add `image_gen` form parameter and UI selector:

```python
# routes.py
image_gen: str = Form("none"),

# Pass through
result = create_deck(
    ...
    image_gen=image_gen,
)
```

```html
<!-- index.html -->
<select id="create-image-gen">
    <option value="none">No image generation</option>
    <option value="claude">Claude (SVG)</option>
    <option value="dalle">DALL-E</option>
</select>
```

### 5. Test Mode (Nice to Have)

Add optional slide limit:

```python
# routes.py
test_slides: int = Form(None),
```

This requires `create_deck()` to accept a `test` parameter, or the web route slices the outline before passing it (matching CLI behavior at cli.py:273-295).

---

## CLI Changes

No CLI changes.

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Create Deck form | New file input | "Attach images" multi-file upload for IMAGE: directive files |
| Create Deck form | New selector (nice to have) | Image generation mode dropdown |
| Create Deck form | New field (nice to have) | "Test: first N slides" number input |

### Wireframe

```
┌─────────────────────────────────────────────┐
│  Create Presentation                        │
├─────────────────────────────────────────────┤
│  Outline:  [textarea or .md upload]         │
│                                             │
│  Attach images: [Choose files...]           │
│  (for IMAGE: directives in your outline)    │
│                                             │
│  ☑ Enhanced mode    Model: [claude-son▾]    │
│                                             │
│  Image gen: [None ▾]   Test slides: [___]   │
│                                             │
│  [ Create Presentation ]                    │
└─────────────────────────────────────────────┘
```

### New API Endpoints

No new endpoints. The existing `POST /api/decks/create` is modified to accept additional form fields.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_web_routes.py` | `test_create_with_image_directive` | Verify IMAGE: directive resolves when outline uploaded as file |
| `tests/test_web_routes.py` | `test_create_with_image_upload` | Verify uploaded images are saved and referenced correctly |
| `tests/test_web_routes.py` | `test_create_pasted_text_with_image` | Verify pasted text saves to disk for path resolution |
| `tests/test_web_routes.py` | `test_create_passes_image_gen` | Verify image_gen parameter flows through to create_deck() |

### Manual Testing

1. Upload a `.md` file with `IMAGE: memes/photo.jpg` plus the image file — verify image appears on slide
2. Paste outline text with `IMAGE: images/diagram.png` where diagram exists on server — verify image appears
3. Upload `.md` with IMAGE: directive but no image file — verify graceful degradation (warning logged, slide created without image)
4. Test enhanced mode with IMAGE: slides — verify concise bullets and Pt(18) font in narrow text area
5. (Nice to have) Set image gen to claude/dalle — verify diagram slides get generated images

---

## Changelog Entry

```markdown
### Added
- Web UI: IMAGE: directives now work when uploading .md files with attached images
- Web UI: Image generation mode selector (none/claude/dalle)
- Web UI: Test mode - limit to first N slides for preview

### Fixed
- Web UI: Uploaded .md files are saved to disk for proper directive resolution
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Save uploaded .md files to disk, pass `outline_path` to `create_deck()` | `routes.py` | -- |
| 2 | Save pasted text to temp file for IMAGE: path resolution | `routes.py` | 1 |
| 3 | Add image file upload support (multi-file input) | `routes.py`, `index.html` | 1 |
| 4 | Add "Attach images" UI element to create form | `index.html` | 3 |
| 5 | Add unit tests for web IMAGE: directive support | `tests/test_web_routes.py` | 1, 2, 3 |
| 6 | (Nice to have) Add image_gen form parameter and UI selector | `routes.py`, `index.html` | -- |
| 7 | (Nice to have) Add test mode (slide count limit) | `routes.py`, `index.html` | -- |
| 8 | (Nice to have) Remove unused `title` form parameter | `routes.py` | -- |
| 9 | Manual validation with meme-directives-test.md via web UI | -- | 1, 3 |
| 10 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Image file path structure — outlines may reference images in subdirectories (`IMAGE: memes/photo.jpg`). Multi-file upload loses directory structure — Mitigation: accept image filenames with path prefixes, or support `.zip` upload
- **Risk:** Disk usage from saved outline/image files in `uploads/` — Mitigation: clean up temp outline files after deck creation; images are already stored in `uploads/` by design
- **Question:** Should pasted text with IMAGE: directives resolve paths relative to the project root or the uploads directory? Recommendation: resolve relative to project root (same as CLI behavior when running from project dir)
- **Question:** Is `.zip` upload support worth the complexity for bundled outline+images? Could defer to a follow-up if multi-file upload covers most use cases

---

## References

- Related PRDs: `docs/plans/2026-03-05-image-text-co-display.md`, `docs/plans/2026-03-05-enhance-content-rewriting.md`
- Web routes: `aippt/web/routes.py` (create_deck_stream, lines 710-845)
- CLI create: `aippt/cli.py` (create_deck, cmd_create)
- Frontend: `aippt/web/static/index.html` (create form, lines 464-508)
