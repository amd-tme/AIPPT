# PPTX Skill Recap & Comparison with aippt

**Date:** 2026-03-10
**Skill source:** `anthropic-agent-skills/document-skills` (Claude Code plugin)

## Overview

The pptx skill provides three workflows for working with PowerPoint files:

| Workflow | When to use | Tools |
|----------|------------|-------|
| **Read/analyze** | Extract text, inspect visually | `markitdown`, `thumbnail.py`, `soffice` + `pdftoppm` |
| **Edit from template** | Modify existing presentations | `unpack.py` → XML editing → `clean.py` → `pack.py` |
| **Create from scratch** | No template available | `pptxgenjs` (Node.js) |

## Tool Inventory

### Reading & Analysis

| Tool | Purpose | Notes |
|------|---------|-------|
| `python -m markitdown file.pptx` | Text extraction to markdown | Includes slide numbers, notes |
| `scripts/thumbnail.py file.pptx` | Visual grid of slide thumbnails | Uses embedded PPTX thumbnails, max 12 per grid |
| `soffice --headless --convert-to pdf` | Convert to PDF for rendering | Via `scripts/office/soffice.py` wrapper |
| `pdftoppm -jpeg -r 150 file.pdf slide` | PDF → individual slide JPEGs | For visual QA |

### Template-Based Editing (XML pipeline)

| Tool | Purpose |
|------|---------|
| `scripts/office/unpack.py input.pptx dir/` | Extract PPTX, pretty-print XML, escape smart quotes |
| `scripts/add_slide.py dir/ slideN.xml` | Duplicate a slide (handles notes, content types, rels) |
| `scripts/clean.py dir/` | Remove slides not in sldIdLst, unreferenced media, orphaned rels |
| `scripts/office/pack.py dir/ output.pptx --original input.pptx` | Validate, repair, condense XML, re-encode smart quotes |
| `scripts/office/validate.py` | Validation checks for OOXML |

### From-Scratch Creation (pptxgenjs)

Node.js library with full programmatic control:
- Text with rich formatting (bold, italic, font, size, color, character spacing)
- Shapes (rectangles, ovals, lines, rounded rects) with fills, shadows, transparency
- Images (file, URL, base64) with sizing modes (contain, cover, crop)
- Tables with merged cells, styled headers
- Charts (bar, line, pie, doughnut, scatter, bubble, radar) with modern styling
- Slide masters for reusable templates
- Icons via react-icons → SVG → sharp → base64 PNG pipeline

## Workflows & Approaches Worth Noting

### 1. Visual QA Pipeline

The skill enforces a strict visual QA loop that aippt currently lacks:

```
Generate slides → soffice PDF → pdftoppm JPEGs → subagent inspection → fix → re-verify
```

Key principles:
- **"Assume there are problems"** — approach QA as bug hunt, not confirmation
- **Use subagents for visual inspection** — fresh eyes catch what the author misses
- **Never declare success until at least one fix-and-verify cycle**
- Specific checklist: overlapping elements, text overflow, margin violations, contrast issues, leftover placeholders

### 2. XML-Level Editing

The unpack/edit/clean/pack pipeline operates at the OOXML XML level, which gives precise control that python-pptx abstracts away:

- Direct `<p:sldIdLst>` manipulation for slide ordering
- Proper `<a:buChar>` / `<a:buAutoNum>` for bullet/number lists (not unicode bullets)
- Rich text via separate `<a:r>` runs with individual `<a:rPr>` attributes
- Separate `<a:p>` elements for each list item (never concatenated)
- Smart quote handling via XML entities (`&#x201C;` etc.)

### 3. Design Guidelines

The skill ships with opinionated design guidance that could inform aippt's LLM prompts:

**Color palettes:** 10 named themes with primary/secondary/accent hex values
**Typography:** Specific font pairings (header + body) and size ranges per element type
**Layout variety:** Explicit push against monotonous bullet slides — actively seek multi-column, image+text, callout, stat, icon grid layouts
**Visual motifs:** "Pick ONE distinctive element and repeat it"
**Anti-patterns:** No accent lines under titles ("hallmark of AI-generated slides"), don't center body text, don't repeat same layout

### 4. pptxgenjs Capabilities vs python-pptx

| Feature | python-pptx (aippt) | pptxgenjs (skill) |
|---------|---------------------|-------------------|
| Bullet lists | Via text frame manipulation | `bullet: true` with `indentLevel` |
| Numbered lists | Manual via text | `bullet: { type: "number" }` |
| Shapes with shadow | Limited | Full shadow API (type, blur, offset, angle, opacity) |
| Charts | Not used | Bar, line, pie, doughnut, scatter, bubble, radar |
| Icons | Not implemented | react-icons → sharp → base64 PNG pipeline |
| Image sizing | Manual positioning | `contain`, `cover`, `crop` modes |
| Rich text | Via runs | Array of `{ text, options }` objects |
| Slide masters | Template-dependent | `defineSlideMaster()` API |

## Potential Improvements for aippt

### High-Value / Low-Effort

1. **Visual QA integration** — Add a `--qa` flag to the create command that runs the soffice → pdftoppm → inspection pipeline after generation. The infrastructure is now installed.

2. **Content overflow detection** — Before rendering, estimate if content will overflow placeholder bounds. The skill's approach: check visually after, but aippt could proactively split slides or reduce font size.

3. **Numbered list detection** — When content has explicit "1. 2. 3." patterns, select the `numbered` layout instead of `bullet`. Avoids the redundant `• 1.` pattern seen in the visual review.

4. **Bold lead-in consistency** — The skill mandates "bold all headers, subheadings, and inline labels" with `b="1"`. aippt's `_detect_lead_in()` regex already finds these patterns but doesn't consistently apply bold formatting.

### Medium-Value / Medium-Effort

5. **Design-aware LLM prompts** — Incorporate the skill's color palette, typography, and layout variety guidelines into the enhancement SYSTEM_PROMPT. Push the LLM away from monotonous bullet slides.

6. **Footer zone awareness** — Calculate the reserved footer area (logo, slide number) and constrain content boxes to respect it. Prevents the AMD logo collision seen in dense slides.

7. **pptxgenjs as alternative renderer** — For "from scratch" decks (no template), pptxgenjs offers richer visual capabilities (charts, icons, shadows, modern styling) than python-pptx placeholder manipulation.

### Lower Priority / Higher Effort

8. **XML-level editing pipeline** — The unpack/edit/clean/pack approach gives finer control than python-pptx for post-processing. Could be useful for a "polish" pass after initial generation.

9. **Icon integration** — react-icons → sharp → base64 pipeline for embedding icons in slides. Would enhance visual quality significantly.

10. **Chart generation** — pptxgenjs chart support could power data-driven slides that aippt currently can't produce.
