# Edit Examples for /edit-deck

Concrete before/after examples for common edit requests.

## Example 1: Change Layout from Bullet to Two-Column

**User request:** "Make slide 3 a two-column layout"

**Before:**
```javascript
// ═══ Slide 3: Benefits Overview ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
slide.background = { fill: '000000' };
slide.addText('Benefits Overview', { x: 0.5, y: 0.3, w: 12, h: 0.8, fontSize: 28, color: 'FFFFFF', bold: true });
slide.addText([
  { text: 'Performance', options: { fontSize: 20, color: 'FFFFFF', bold: true, bullet: true } },
  { text: '  2x faster processing', options: { fontSize: 18, color: 'CCCCCC', bullet: true } },
  { text: 'Reliability', options: { fontSize: 20, color: 'FFFFFF', bold: true, bullet: true } },
  { text: '  99.9% uptime SLA', options: { fontSize: 18, color: 'CCCCCC', bullet: true } },
  { text: 'Security', options: { fontSize: 20, color: 'FFFFFF', bold: true, bullet: true } },
  { text: '  SOC 2 Type II certified', options: { fontSize: 18, color: 'CCCCCC', bullet: true } },
], { x: 0.5, y: 1.5, w: 12, h: 5, valign: 'top' });
```

**After:**
```javascript
// ═══ Slide 3: Benefits Overview ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
slide.background = { fill: '000000' };
slide.addText('Benefits Overview', { x: 0.5, y: 0.3, w: 12, h: 0.8, fontSize: 28, color: 'FFFFFF', bold: true });
// Divider line
slide.addShape(pptx.ShapeType.line, { x: 6.5, y: 1.5, w: 0, h: 4.5, line: { color: '636466', width: 1 } });
// Left column
slide.addText([
  { text: 'Performance', options: { fontSize: 20, color: '00C2DE', bold: true, bullet: true } },
  { text: '  2x faster processing', options: { fontSize: 18, color: 'CCCCCC', bullet: true } },
], { x: 0.5, y: 1.5, w: 5.5, h: 4.5, valign: 'top' });
// Right column
slide.addText([
  { text: 'Reliability', options: { fontSize: 20, color: '00C2DE', bold: true, bullet: true } },
  { text: '  99.9% uptime SLA', options: { fontSize: 18, color: 'CCCCCC', bullet: true } },
  { text: 'Security', options: { fontSize: 20, color: '00C2DE', bold: true, bullet: true } },
  { text: '  SOC 2 Type II certified', options: { fontSize: 18, color: 'CCCCCC', bullet: true } },
], { x: 7.0, y: 1.5, w: 5.5, h: 4.5, valign: 'top' });
```

## Example 2: Add Speaker Notes to All Slides

**User request:** "Add speaker notes to every slide"

**Pattern:** For each slide block, add an `addNotes()` call based on the slide content. Generate relevant talking points from the bullet text.

**Before** (each slide):
```javascript
// ═══ Slide 2: Architecture ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
// ... slide content, no addNotes() call ...
```

**After:**
```javascript
// ═══ Slide 2: Architecture ═══
slide = pptx.addSlide({ masterName: 'BLANK' });
// ... slide content ...
slide.addNotes('Walk through the three-tier architecture. Emphasize the event bus as the key integration point. Mention that this pattern scales to 10K concurrent users.');
```

## Example 3: Fix Text Overflow

**User request:** "Slide 5 has text overflow, fix it"

**Diagnosis:** Too many bullets or font too large for the content area.

**Fixes (pick the best):**
1. Reduce font size (e.g., 20 → 18pt for body, 24 → 20pt for headers)
2. Trim verbose bullets to shorter phrases
3. Split into two slides if content is genuinely too dense
4. Increase the text area height (reduce top/bottom margins)

## Example 4: Insert a New Slide

**User request:** "Add a summary slide after slide 6"

**Pattern:** Insert a new slide block after slide 6's marker. Renumber all subsequent slides.

```javascript
// ═══ Slide 7: Summary ═══  ← NEW
slide = pptx.addSlide({ masterName: 'BLANK' });
slide.background = { fill: '000000' };
slide.addText('Summary', { x: 0.5, y: 0.3, w: 12, h: 0.8, fontSize: 28, color: 'FFFFFF', bold: true });
slide.addText([
  { text: 'Key takeaways from this section...', options: { fontSize: 20, color: 'CCCCCC' } },
], { x: 0.5, y: 1.5, w: 12, h: 5, valign: 'top' });

// ═══ Slide 8: Next Steps ═══  ← was Slide 7
```

## Example 5: Reorder Sections

**User request:** "Move the compliance section before security"

**Pattern:** Identify all slides belonging to each section (by scanning markers and content). Cut the compliance block and paste it before the security block. Renumber all markers.
