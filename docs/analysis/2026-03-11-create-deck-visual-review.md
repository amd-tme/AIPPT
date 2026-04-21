# Create-Deck Skill — Visual Review & Enhancement Guide

**Date:** 2026-03-11
**Decks Reviewed:**
- `output/quarterly-review-sections.pptx` — pptxgenjs + AMD theme (16 slides)
- `output/meme-directives-test.pptx` — python-pptx + corp.pptx template (11 slides, reference)

---

## Critical Bug: Layout Dimension Mismatch

**This is the root cause of ALL right-edge and bottom-edge clipping across every layout.**

The theme YAML specifies `layout: "LAYOUT_16x9"` and the pptxgenjs guide uses coordinates designed for a 13.33" × 7.5" canvas. But `LAYOUT_16x9` in pptxgenjs is actually **10" × 5.625"** — not 13.33" × 7.5".

| Layout Name | Actual Width | Actual Height | Guide Assumes |
|---|---|---|---|
| `LAYOUT_16x9` | **10.0"** | **5.625"** | 13.33" × 7.5" |
| `LAYOUT_WIDE` | 13.33" | 7.5" | — |

Every coordinate in the skill guide and theme YAML is wrong by ~33%. Content placed at x=10+ or y=5.625+ is off-canvas.

### Fix Options

**Option A (Recommended): Change layout to `LAYOUT_WIDE`**
- Update `amd.yaml`: `slide.layout: "LAYOUT_WIDE"` (was `"LAYOUT_16x9"`)
- All existing guide coordinates (designed for 13.33" × 7.5") become correct immediately
- Both layouts are 16:9 aspect ratio — `LAYOUT_WIDE` is just the larger EMU size
- PowerPoint will display identically on-screen; the difference is internal coordinate units

**Option B: Recalculate all coordinates for 10" × 5.625"**
- Multiply all x values by 0.75 (10/13.33)
- Multiply all y values by 0.75 (5.625/7.5)
- Much more work, higher risk of introducing new bugs

### Theme YAML Change

```yaml
slide:
  layout: "LAYOUT_WIDE"     # was "LAYOUT_16x9" — LAYOUT_WIDE = 13.33" × 7.5"
  margin_inches: 0.64
```

### Guide Update

Add a prominent warning to `pptxgenjs-guide.md`:

```
## IMPORTANT: Slide Dimensions

All coordinates in this guide use LAYOUT_WIDE (13.33" × 7.5").
Do NOT use LAYOUT_16x9 — it is 10" × 5.625" and all coordinates will be wrong.
Always set: pptx.layout = "LAYOUT_WIDE";
```

---

## Design Gap: pptxgenjs vs. Corporate Template

The reference deck (python-pptx + corp.pptx) reveals the actual AMD corporate aesthetic. The pptxgenjs output deviates significantly.

### What the Corporate Template Actually Looks Like

Analyzed from `meme-directives-test.pptx` (11 slides):

| Element | Corporate Template | Current pptxgenjs Output |
|---|---|---|
| **Background** | Pure black, no decoration | Black with teal bars, gray cards, icon circles |
| **Accent colors on content** | None — zero teal/gold on body slides | Heavy use of teal bars, gold accents, colored shapes |
| **Title slide** | AMD arrow logo (left half), title (right), logo+tagline (bottom-right) | Teal accent line, centered title, no logo visible |
| **Content slides** | White text on black, no visual embellishment | Gray card panels, icon circles, accent bars |
| **Footer** | Slide number (bottom-left), "AMD↗ together we advance_" (bottom-right), no line | Thin gray line, "[AMD Proprietary]" (top-left), logo from file |
| **Typography** | All white, bold titles ~28-32pt, body ~18-20pt | Mixed colors (teal for stats, gray for sub-text) |
| **Column headers** | White, bold, centered | Teal left header, gold right header |
| **Visual density** | Minimalist — content in upper 40%, rest is breathing room | Dense — fills entire slide with cards, shapes, icons |

### Key Insight

The AMD corporate template is **extremely minimalist**. Content slides are just:
1. Bold white title (top-left)
2. White bullet text (below title, in upper portion)
3. Slide number (bottom-left corner, plain)
4. AMD wordmark + tagline (bottom-right corner)
5. Black everywhere else

There are **no colored bars, no card backgrounds, no icon circles, no accent shapes** on any content slide. The only visual flourish is on the cover slide (the large AMD architectural arrow graphic).

### What This Means for the Skill

The pptxgenjs engine should support two distinct visual modes:

1. **"Creative/Rich" mode** (current default) — Cards, icons, stat callouts, process flows. Good for standalone presentations without a corporate template.

2. **"Corporate Match" mode** — Matches the actual corp.pptx template output. Minimalist. White on black. No decorative shapes. This is what users expect when they select "AMD corporate theme."

When the user selects the AMD theme, the skill should default to Corporate Match mode unless they explicitly request rich visuals.

---

## Slide-by-Slide Issues (pptxgenjs deck)

### Slides Affected by Dimension Bug (right/bottom clipping)

These are all fixed by switching to `LAYOUT_WIDE`:

| Slide | Layout | Clipping |
|---|---|---|
| 1 (Title) | Title slide | Subtitle text clips at right edge |
| 3 (Revenue) | Stat callout | 3rd stat column ($800K) fully clipped |
| 4 (Expenses) | Card grid | Right-column cards clip; bottom row clips |
| 7 (Platform) | Card grid | Same as slide 4 |
| 8 (Roadmap) | Process flow | 4th step entirely off-canvas; 3rd partially clipped |
| 10 (Metrics) | Stat callout | 4th stat (4.2h) fully clipped |
| 13 (Pipeline) | Two-column | Right column text clipped mid-sentence |
| 14 (Marketing) | Icon rows | 4th item clipped at bottom |

### Layout-Specific Issues (independent of dimension bug)

**Section Dividers (slides 2, 6, 9, 12):**
- Title positioned at y≈2.0" with upper 60% empty — feels bottom-heavy
- Corporate template doesn't have section divider slides at all; it just uses normal content slides
- The full-width teal bar is not part of the corporate aesthetic
- Fix: Either remove section dividers entirely (corp template doesn't use them) or vertically center the title text

**Stat Callout (slides 3, 10):**
- Large empty zone below stats (~35% of slide)
- 60pt font is impactful but too large — the values overflow their containers
- Corp template would show these as bullet text, not giant numbers
- Fix: Reduce stat font to 48pt; add supporting content below or reduce vertical space

**Card Grid (slides 4, 7):**
- Gray card backgrounds with accent bars are not part of corp aesthetic
- Cards fill too much vertical space — bottom row gets cut
- Fix: In corp-match mode, render as plain bullet lists with bold lead-ins

**Process Flow (slide 8):**
- 4 items with arrows need more than 10" of horizontal space
- Fix: Process flow should auto-detect item count and use 2 rows if > 3 items, or shrink card width

**Icon Rows (slides 5, 11, 14):**
- This is actually the strongest layout — icons add visual interest without over-designing
- But with 4 items, row height × 4 exceeds slide height
- Fix: When items > 3, reduce per-row height from 1.4" to 1.1" (adaptive)

**Closing Slide (slide 16):**
- Bullet hierarchy bug — second item renders as indented sub-bullet
- Left 40% of slide is unused dead space
- Fix: Normalize bullet indent levels; center the content block

---

## Footer Specification (from Corp Template)

The current footer implementation doesn't match the corporate template. Here's what it should be:

### Corporate Template Footer

```
Position: Bottom strip, ~0.5" tall
Slide number: Bottom-left, plain integer, ~12pt, white
              Position: x≈0.2", y≈bottom-0.3"
Logo: "AMD↗ together we advance_" bottom-right
      Position: x≈right-1.5", y≈bottom-0.4"
      AMD symbol + text, all white, ~10-12pt for tagline
No separator line
No "[AMD Proprietary]" label
No colored footer bar
```

### Current pptxgenjs Footer (Incorrect)

```
- Thin gray separator line at y=7.18" (off-canvas with LAYOUT_16x9!)
- "[AMD Proprietary]" label at top-left corner (not in corp template)
- Slide number at bottom-left (correct concept, wrong position)
- Logo from themes/assets/amd-wordmark.png (file exists but not rendering visibly)
```

### Recommended Footer Fix

```javascript
function addFooter(slide, pptx, slideNum) {
  const SW = 13.33; // slide width (LAYOUT_WIDE)
  const SH = 7.5;   // slide height (LAYOUT_WIDE)

  // Slide number — bottom-left, plain integer
  slide.addText(`${slideNum}`, {
    x: 0.2, y: SH - 0.45, w: 0.5, h: 0.3,
    fontSize: 10, fontFace: "Arial",
    color: "FFFFFF",
  });

  // AMD logo — bottom-right
  if (fs.existsSync("themes/assets/amd-wordmark.png")) {
    slide.addImage({
      path: "themes/assets/amd-wordmark.png",
      x: SW - 1.5, y: SH - 0.5, w: 1.26, h: 0.36,
    });
  }

  // NO separator line
  // NO "[AMD Proprietary]" label
}
```

### Logo File Note

The file `themes/assets/amd-wordmark.png` exists (264 KB) but it's the AMD text wordmark only — not the "AMD↗ together we advance_" composite. The corp template embeds the full logo+tagline as a single image in its slide master. To match the corp template exactly, a combined logo+tagline image is needed.

---

## Coordinate Reference (LAYOUT_WIDE = 13.33" × 7.5")

Safe area boundaries for all layouts:

```
Slide width:     13.33"
Slide height:     7.50"
Left margin:      0.64" (from theme)
Right margin:     0.64"
Top margin:       0.50" (clear of any header elements)
Bottom margin:    0.60" (clear of footer zone)

Content area:
  x: 0.64"
  y: 0.50"
  w: 12.05" (13.33 - 0.64 - 0.64)
  h: 6.40"  (7.50 - 0.50 - 0.60)
  right edge: 12.69"
  bottom edge: 6.90"

Title position:
  x: 0.64"
  y: 0.30"
  w: 11.50"
  h: 0.70"

Content start (below title):
  y: 1.20"
```

### Column Calculations

Always validate: `x + w <= 12.69"` (right safe boundary)

```
Two columns:
  col1: x=0.64, w=5.70
  col2: x=6.70, w=5.99
  gutter: 0.36"

Three columns (stats):
  colW = 11.50 / 3 = 3.83"
  col1: x=0.64
  col2: x=4.64
  col3: x=8.64
  right edge of col3: 8.64 + 3.83 = 12.47" ✓ (< 12.69)

Four columns (stats):
  colW = 11.50 / 4 = 2.875"
  col1: x=0.64
  col2: x=3.64
  col3: x=6.64
  col4: x=9.64
  right edge of col4: 9.64 + 2.875 = 12.515" ✓

Card grid (2×2):
  cardW = 5.50"
  gutter = 1.05"
  card1: x=0.64, card2: x=7.19
  right edge of card2: 7.19 + 5.50 = 12.69" ✓

  cardH = 2.40"
  row1 y=1.20, row2 y=4.00
  bottom of row2: 4.00 + 2.40 = 6.40" ✓ (< 6.90)

Process flow (4 items):
  stepW = 2.20"
  gap = 0.50"
  total = 4 × 2.20 + 3 × 0.50 = 10.30"
  startX = (13.33 - 10.30) / 2 = 1.52"
  right edge: 1.52 + 10.30 = 11.82" ✓

Icon rows:
  Max 3 items at rowH=1.40" → total 4.20" (fits: 1.20 + 4.20 = 5.40" < 6.90")
  Max 4 items at rowH=1.10" → total 4.40" (fits: 1.20 + 4.40 = 5.60" < 6.90")
```

---

## Summary: Priority Fixes for the Skill

### P0 — Blockers

1. **Fix `LAYOUT_16x9` → `LAYOUT_WIDE`** in theme YAML and generated scripts. This fixes all clipping.
2. **Fix footer** to match corp template (no separator line, no proprietary label, correct logo position)

### P1 — Visual Alignment with Corp Template

3. **Add "corporate-match" mode** for AMD theme — minimalist white-on-black, no colored shapes
4. **Fix section dividers** — vertically center title, remove full-width teal bar
5. **Add safe-area validation** — the guide should include a validation function that checks all element positions against slide boundaries before rendering

### P2 — Layout Improvements

6. **Process flow** — auto-scale for item count (2 rows if > 3 items)
7. **Icon rows** — adaptive row height based on item count (1.4" for ≤3, 1.1" for 4)
8. **Card grid** — recalculate positions with proper margins (see coordinate reference above)
9. **Closing slide** — fix bullet indent levels, center content

### P3 — Guide Updates

10. **Add dimension warning** to pptxgenjs-guide.md header
11. **Add safe-area constants** to the script template
12. **Add boundary validation helper** function to the guide
13. **Document LAYOUT_WIDE vs LAYOUT_16x9** difference explicitly
