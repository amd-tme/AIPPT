# Edit Patterns for /edit-deck

Reference for common script editing patterns. The edit-deck skill modifies generating code (JS or Python), not the PPTX directly.

## Finding Slides

Scripts use comment markers to delimit slides:

```javascript
// ═══ Slide 1: Title Slide ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
// ... slide content ...

// ═══ Slide 2: Architecture Overview ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
```

Python equivalent:
```python
# ═══ Slide 1: Title Slide ═══
slide = prs.slides.add_slide(blank_layout)
```

**To edit slide N:** Find `// ═══ Slide N:` and modify everything up to the next marker.

## Single-Slide Edit Patterns (pptxgenjs)

### Change Layout Type

**Bullet → Two-Column:**
Replace the single text block with two side-by-side blocks. Split content at a logical midpoint.

### Add Speaker Notes

```javascript
slide.addNotes(`Key talking points:
- First point
- Second point

---aippt-meta---
source: outline → pptxgenjs
created: 2026-03-11
history:
  - "2026-03-11: Created from outline (bullet layout)"
  - "2026-03-13: Added speaker notes [/edit-deck]"
layout: bullet
theme: amd
---end-aippt-meta---`);
```

### Change Text Content

Edit the text strings in `addText()` calls. Preserve formatting objects (`{ fontSize, fontFace, color }`) unless the user specifically asks to change styling.

### Add/Swap Images

```javascript
slide.addImage({ path: 'images/new-diagram.png', x: 1.0, y: 1.5, w: 5, h: 3.5 });
```

## Deck-Level Edit Patterns

### Add a New Slide

Insert a new slide marker and block between existing ones. Update all subsequent slide numbers in the markers:

```javascript
// ═══ Slide 4: New Slide Title ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
// ... new slide content ...

// ═══ Slide 5: Previously Slide 4 ═══  ← renumbered
```

### Remove a Slide

Delete the entire block from marker to next marker. Renumber subsequent slides.

### Reorder Slides

Move the entire code block (marker to next marker) to the new position. Renumber all markers.

### Batch Operations

For "add notes to all slides" or "change font on all slides": iterate through each slide block and apply the change consistently. Use search-and-replace when the pattern is uniform.

## Diff Hygiene

- Only modify the slide blocks you need to change
- Don't reformat or restructure code you're not editing
- Keep the same indentation style as the original
- Preserve helper function definitions at the top of the file
- If adding imports, add them at the top with existing imports
