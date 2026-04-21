# PRD: Slide AI Assistant (Web UI)

**Date:** 2026-02-23
**Author:** Matt Elliott
**Status:** Draft

---

## Summary

Add per-slide AI actions to the web UI so users can analyze, generate notes for, and get improvement suggestions on individual slides directly from the browser. Today these operations are CLI-only and batch-oriented (whole deck at a time). This feature adds "Analyze," "Suggest Notes," and "Suggest Improvements" buttons to the slide detail dialog, backed by new API endpoints that invoke the existing analysis and a new improvements module. Requires the model management feature so the web server knows which models to use.

## Motivation

- **Problem:** AI analysis (`analyze --mode feedback|notes|tags`) only runs from the CLI and always processes an entire deck. There is no way to get AI feedback on a single slide from the web UI, and no way to get structured improvement suggestions (splitting busy slides, reorganizing content, improving visual design).
- **Who benefits:** Users browsing their slide catalog in the web UI who want quick, on-demand AI insight without switching to the terminal.
- **What happens if we don't do this:** Users must leave the web UI, construct CLI commands with the correct slide images directory and model flags, and process an entire deck to get feedback on one slide.

## Requirements

### Must Have

- [ ] "Analyze" button in slide detail dialog -- sends slide image to the configured feedback model, displays design/content feedback inline
- [ ] "Suggest Notes" button -- sends slide image to the configured notes model, displays generated speaker notes inline, with option to save to the slide record
- [ ] "Suggest Improvements" button -- sends slide image to a new improvements analysis mode, returns structured suggestions covering visual design, technical accuracy, content organization, and splitting recommendations
- [ ] New `improvements` analysis mode in `analyze.py` with a dedicated system prompt
- [ ] All three actions use models from `models.yaml` configuration (model management PRD prerequisite)
- [ ] Results displayed in the slide detail dialog without page reload
- [ ] Loading state shown while waiting for LLM response
- [ ] Error handling for missing images, unconfigured models, or LLM failures

### Nice to Have

- [ ] Save analysis results to the database for later review
- [ ] "Re-analyze" to run analysis again with a different model (model selector dropdown)
- [ ] Side-by-side before/after view for improvement suggestions
- [ ] Export analysis results as markdown

### Out of Scope

- Applying improvements automatically (editing the PPTX from the web UI)
- Real-time streaming of LLM responses
- Batch analysis of multiple slides from the web UI (CLI already handles this)
- Image generation or slide rendering from the web UI

---

## Design

### Approach

Add three action buttons to the existing slide detail dialog. Each button calls a new API endpoint that instantiates an `LLMClient` using the model from `models.yaml`, runs `analyze_slide()` (or the new improvements analysis), and returns the result as JSON. The frontend displays the result in a collapsible section below the slide image.

The `improvements` mode is new -- it uses a dedicated system prompt that asks the LLM to evaluate the slide across multiple dimensions and return structured feedback. Unlike `feedback` mode (which gives general design feedback), `improvements` is prescriptive: it tells the user specifically what to change and why.

### New Analysis Mode: `improvements`

The `improvements` mode evaluates a slide across four dimensions:

| Dimension | What It Covers |
|-----------|---------------|
| **Visual Design** | Layout effectiveness, whitespace, font consistency, color usage, image quality |
| **Technical Accuracy** | Terminology correctness, data presentation, claim support, citation needs |
| **Flow & Organization** | Logical structure, information hierarchy, reading order, narrative coherence |
| **Splitting Recommendation** | Whether the slide tries to cover too much, and how to split it into multiple slides |

The LLM returns a structured response with sections for each dimension. The frontend renders these as separate collapsible blocks.

### Model Resolution

Each action uses a specific model from the configuration (model management PRD):

| Action | Config Key | Default |
|--------|-----------|---------|
| Analyze | `defaults.feedback` | `gpt-4o` |
| Suggest Notes | `defaults.notes` | `gpt-4o` |
| Suggest Improvements | `defaults.feedback` | `gpt-4o` |

All three require vision-capable models since they process slide images.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/analyze.py` | Modified | Add `IMPROVEMENTS_SYSTEM_PROMPT`, support `mode="improvements"` in `analyze_slide()` |
| `outline2ppt/web/routes.py` | Modified | Add `/api/slides/{id}/analyze`, `/api/slides/{id}/notes`, `/api/slides/{id}/improvements` endpoints |
| `outline2ppt/web/app.py` | Modified | Accept `gateway_config` path in `create_app()` for LLM client setup |
| `outline2ppt/web/static/index.html` | Modified | Add action buttons, result display sections, loading states to slide detail dialog |
| `outline2ppt/cli.py` | Modified | Add `--mode improvements` to `analyze` subcommand; pass `--gateway-config` and `--db` to `serve` |

### Data Model Changes

No data model changes. Analysis results are returned to the client and displayed inline. Saving results to the database is a nice-to-have for a future iteration.

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `outline2ppt analyze` | New mode `improvements` | `--mode improvements` runs the new structured improvement analysis |
| `outline2ppt serve` | New option `--gateway-config` | Passes gateway config to the web app for LLM access |

### Example Usage

```bash
# Run improvement analysis on a deck from CLI
python outline2ppt.py analyze deck.pptx --mode improvements --images-dir images/deck/

# Output per slide:
# --- Slide 3: Architecture Overview ---
#
# VISUAL DESIGN:
# - The diagram uses 8 colors with no legend; reduce to 4 and add labels
# - Text in the lower-right box is below 10pt; increase or remove
#
# TECHNICAL ACCURACY:
# - "Zero-copy transfer" is described but the diagram shows a buffer stage
# - Consider adding a citation for the throughput numbers
#
# FLOW & ORGANIZATION:
# - The eye path goes left-to-right but the numbering goes top-to-bottom
# - Move the summary box from bottom-right to top-left as a lead-in
#
# SPLITTING RECOMMENDATION:
# - This slide covers both architecture and performance metrics
# - Split into: (1) Architecture diagram only, (2) Performance benchmarks table

# Launch web UI with gateway config
python outline2ppt.py serve --port 8000 --gateway-config gateway.yaml
```

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Slide detail dialog | Action buttons | Three buttons below the slide image: Analyze, Suggest Notes, Suggest Improvements |
| Slide detail dialog | Results panels | Collapsible result sections for each action, shown below the buttons |
| Slide detail dialog | Loading indicator | Spinner/progress indicator while waiting for LLM response |

### New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/slides/{slide_id}/analyze` | Run feedback analysis on a single slide; returns analysis text |
| POST | `/api/slides/{slide_id}/notes` | Generate speaker notes for a single slide; returns notes text |
| POST | `/api/slides/{slide_id}/improvements` | Run improvement analysis on a single slide; returns structured suggestions |
| POST | `/api/slides/{slide_id}/notes/save` | Save generated notes to the slide record in the database |

All POST endpoints accept an optional `{"model": "model-name"}` body to override the configured default for that request.

### Wireframe / Mockup

**Slide detail dialog with AI actions (idle state):**

```
+------------------------------------------------------+
|  [x] Slide 5: Architecture Overview                  |
|                                                       |
|  +------------------------------------------------+  |
|  |                                                |  |
|  |              [slide image]                     |  |
|  |                                                |  |
|  +------------------------------------------------+  |
|                                                       |
|  [Analyze]  [Suggest Notes]  [Suggest Improvements]   |
|                                                       |
|  Tags:                                                |
|    [security x] [architecture x]                      |
|                                                       |
|  Add tag: [______________] [Add Tag]                  |
|                                                       |
|  > Speaker Notes                                      |
+-------------------------------------------------------+
```

**After clicking "Suggest Improvements" (with results):**

```
+------------------------------------------------------+
|  [x] Slide 5: Architecture Overview                  |
|                                                       |
|  +------------------------------------------------+  |
|  |              [slide image]                     |  |
|  +------------------------------------------------+  |
|                                                       |
|  [Analyze]  [Suggest Notes]  [Suggest Improvements]   |
|                                                       |
|  Improvement Suggestions         (model: gpt-4o)     |
|                                                       |
|  v Visual Design                                      |
|    - Reduce color palette from 8 to 4 colors          |
|    - Add legend for diagram symbols                   |
|    - Increase body text to 14pt minimum               |
|                                                       |
|  v Technical Accuracy                                 |
|    - Diagram shows buffer stage but text says          |
|      "zero-copy" -- reconcile                         |
|    - Add source citation for throughput numbers        |
|                                                       |
|  v Flow & Organization                                |
|    - Reading order conflicts with numbering            |
|    - Move summary to top-left as lead-in              |
|                                                       |
|  v Splitting Recommendation                           |
|    - Split into two slides:                           |
|      1. Architecture diagram (visual focus)           |
|      2. Performance benchmarks (data focus)           |
|                                                       |
|  Tags: ...                                            |
+-------------------------------------------------------+
```

**After clicking "Suggest Notes" (with save option):**

```
+------------------------------------------------------+
|  ...                                                  |
|  [Analyze]  [Suggest Notes]  [Suggest Improvements]   |
|                                                       |
|  Suggested Notes                  (model: gpt-4o)     |
|  +------------------------------------------------+  |
|  | This slide presents the system architecture     |  |
|  | with three main components. Start by explaining  |  |
|  | the data flow from left to right. Highlight the  |  |
|  | caching layer as the key performance feature.    |  |
|  | Transition: "Now let's look at the benchmarks."  |  |
|  +------------------------------------------------+  |
|  [Save to Slide Notes]                                |
|                                                       |
|  Tags: ...                                            |
+-------------------------------------------------------+
```

**Loading state (while waiting for LLM):**

```
+------------------------------------------------------+
|  ...                                                  |
|  [Analyze]  [Suggest Notes]  [Suggest Improvements]   |
|                                                       |
|  [spinner] Analyzing slide...                         |
|                                                       |
+-------------------------------------------------------+
```

Buttons are disabled while a request is in flight. Only one result section is shown at a time (clicking a new action replaces the previous result).

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_analyze.py` | `TestImprovementsMode` | `analyze_slide` with `mode="improvements"`, prompt construction, response structure |

### Integration Tests

Add to `tests/test_integration.py`:
- `test_analyze_improvements_mode_cli` -- CLI `analyze --mode improvements` runs without error (mocked LLM)
- `test_slide_analyze_endpoint` -- POST `/api/slides/{id}/analyze` returns feedback
- `test_slide_notes_endpoint` -- POST `/api/slides/{id}/notes` returns notes
- `test_slide_improvements_endpoint` -- POST `/api/slides/{id}/improvements` returns structured result
- `test_slide_notes_save_endpoint` -- POST `/api/slides/{id}/notes/save` persists notes

### Manual Testing

1. Catalog a deck with images, launch web UI, open a slide detail dialog
2. Click "Analyze" -- verify spinner shows, then feedback appears below the buttons
3. Click "Suggest Notes" -- verify notes appear with "Save to Slide Notes" button
4. Click "Save to Slide Notes" -- verify notes are saved (check Speaker Notes section)
5. Click "Suggest Improvements" -- verify structured suggestions appear with four collapsible sections
6. Click a different action -- verify previous result is replaced
7. Test with a slide that has no image -- verify a clear error message is shown
8. Test with no model configured / no gateway -- verify error message

---

## Changelog Entry

```markdown
### Added
- AI action buttons in web UI slide detail: Analyze, Suggest Notes, Suggest Improvements
- New `improvements` analysis mode with structured feedback on visual design, technical accuracy, flow/organization, and splitting recommendations
- `/api/slides/{id}/analyze`, `/api/slides/{id}/notes`, `/api/slides/{id}/improvements` API endpoints
- `analyze --mode improvements` CLI option
- `serve --gateway-config` option to provide LLM access in the web UI
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add `IMPROVEMENTS_SYSTEM_PROMPT` and `mode="improvements"` support to `analyze_slide()` | `outline2ppt/analyze.py` | -- |
| 2 | Add `--mode improvements` to CLI `analyze` subcommand | `outline2ppt/cli.py` | 1 |
| 3 | Update `create_app()` to accept and store `gateway_config` path; add `--gateway-config` to `serve` | `outline2ppt/web/app.py`, `outline2ppt/cli.py` | -- |
| 4 | Add LLM client factory helper for web routes (load gateway, resolve model from config) | `outline2ppt/web/routes.py` | 3, model-management PRD |
| 5 | Add `/api/slides/{id}/analyze` endpoint | `outline2ppt/web/routes.py` | 4 |
| 6 | Add `/api/slides/{id}/notes` and `/api/slides/{id}/notes/save` endpoints | `outline2ppt/web/routes.py` | 4 |
| 7 | Add `/api/slides/{id}/improvements` endpoint | `outline2ppt/web/routes.py` | 4 |
| 8 | Add AI action buttons, loading state, and result display to slide detail dialog | `outline2ppt/web/static/index.html` | 5, 6, 7 |
| 9 | Add unit tests for `improvements` mode | `tests/test_analyze.py` | 1 |
| 10 | Add integration tests for API endpoints | `tests/test_integration.py` | 5, 6, 7 |
| 11 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** LLM responses can be slow (5-15 seconds for vision models) -- mitigated by clear loading state and disabling buttons during requests. Streaming is out of scope but would improve perceived performance in a future iteration.
- **Risk:** Slides without images cannot be analyzed -- the UI shows a clear message. The existing pattern of manual image export from PowerPoint is unchanged.
- **Risk:** Gateway or API key may not be available when running the web server -- mitigated by checking configuration at request time and returning a descriptive error (not at startup, since browsing/tagging don't require LLM access).
- **Prerequisite:** Model management PRD must be implemented first so the web server can resolve which model to use for each operation. Without it, models would need to be hard-coded in the route handlers.
- **Question:** Should the improvements prompt return markdown or plain text? Markdown renders better in the UI and is easy to parse into sections. Recommend markdown with `##` headers for each dimension.
- **Question:** Should analysis results be persisted to the database? Keeping it stateless (display-only) is simpler for v1. Persisting results would enable "show me the last analysis" and history tracking but adds schema changes. Recommend stateless for v1.

---

## References

- Model management PRD (prerequisite): `docs/plans/2026-02-23-model-management.md`
- Tag management PRD: `docs/plans/2026-02-23-tag-management.md`
- Current analysis module: `outline2ppt/analyze.py`
- Current enhancer module: `outline2ppt/enhancer.py`
- Design doc analysis section: `docs/plans/2026-02-18-outline2ppt-v2-design.md` (Section 5)
- LLM vision API: `outline2ppt/llm.py` (`generate_text_with_image`)
