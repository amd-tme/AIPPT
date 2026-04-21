# Create-Deck "Snazz" Enhancements Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the create-deck skill with new visual patterns — Simple Icons integration, logo grid layout, improved section dividers, brand badges, icon row spacing fix, column headers with logos, and conservative snazz for python-pptx.

**Architecture:** All changes are documentation/guide updates to the create-deck skill files. No Python code changes — this is entirely about teaching Claude how to generate better-looking deck scripts. Each task updates one or more files in `.claude/skills/create-deck/`.

**Tech Stack:** Markdown documentation, pptxgenjs API patterns, python-pptx API patterns, react-icons/si (Simple Icons), YAML theme schema

---

## Scope Check

This is a single subsystem (the create-deck skill documentation). All changes live in `.claude/skills/create-deck/` and are tightly coupled — they all modify how Claude generates deck scripts. One plan is appropriate.

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `.claude/skills/create-deck/references/pptxgenjs-guide.md` | Modify | Add new layout patterns, icon integration updates, spacing fixes |
| `.claude/skills/create-deck/references/python-pptx-guide.md` | Modify | Add conservative snazz patterns |
| `.claude/skills/create-deck/SKILL.md` | Modify | Update layout decision strategy table, add new layout types |

## Chunk 1: Simple Icons Integration + Icon Best Practices

### Task 1: Add Simple Icons (react-icons/si) to pptxgenjs guide

**Files:**
- Modify: `.claude/skills/create-deck/references/pptxgenjs-guide.md` (lines 709-753, Icon Integration section)

- [ ] **Step 1: Read the current Icon Integration section**

Verify the current content at lines 709-753 of `pptxgenjs-guide.md`.

- [ ] **Step 2: Expand the Icon Integration section**

After the existing `### Common Icons` block (line 753), add a new subsection for Simple Icons. Insert before `## Theme Application` (line 757):

```markdown
### Simple Icons (Brand Logos)

**Before choosing icons for any slide mentioning a named technology, check `react-icons/si` first.** Simple Icons provide real product logos with brand-accurate colors — the single fastest upgrade from "generic presentation" to professional-looking deck.

#### Discovery Pattern

```javascript
// Find SI icons for a technology name
const si = require("react-icons/si");
const keys = Object.keys(si).filter(k => k.toLowerCase().includes("terraform"));
// → ["SiTerraform"]
```

#### Common DevOps / Infrastructure Icons

```javascript
const {
  SiTerraform, SiAnsible, SiDocker, SiKubernetes,
  SiNomad, SiConsul, SiVault, SiPacker,
  SiTraefikproxy, SiMinio, SiN8N, SiTailscale,
  SiGrafana, SiPrometheus, SiElasticsearch, SiRedis,
  SiPostgresql, SiMongodb, SiGithub, SiGitlab,
  SiJenkins, SiArgo, SiHelm, SiNginx,
  SiLinux, SiUbuntu, SiWindows, SiApple,
  SiPython, SiNodedotjs, SiTypescript, SiRust, SiGo,
} = require("react-icons/si");
```

#### Brand Color Rule

**Always render SI icons in their brand color, never white.** The recognition value of Simple Icons comes from their color — a white Terraform icon is just a generic shape, but `#844FBA` Terraform purple is instantly recognizable.

```javascript
// CORRECT — brand color
const terraformIcon = await iconToBase64(renderIconSvg(SiTerraform, 256, "844FBA"));

// WRONG — white loses brand recognition
const terraformIcon = await iconToBase64(renderIconSvg(SiTerraform, 256, "FFFFFF"));
```

Common brand colors (look up exact values at simpleicons.org):
| Icon | Brand Color |
|------|------------|
| `SiTerraform` | `844FBA` |
| `SiAnsible` | `EE0000` |
| `SiDocker` | `2496ED` |
| `SiKubernetes` | `326CE5` |
| `SiNomad` | `00CA8E` |
| `SiConsul` | `F24C53` |
| `SiGrafana` | `F46800` |
| `SiPrometheus` | `E6522C` |
| `SiRedis` | `DC382D` |
| `SiPostgresql` | `4169E1` |
| `SiGithub` | `FFFFFF` (exception: white on dark bg) |

#### Fallback Rule

If no SI icon exists for a named technology, use a contextually appropriate FA icon **in the accent color** (not white). A white generic server icon reads as decorative noise; a colored one at least implies meaning.

```javascript
// Good fallback — accent-colored FA icon
const fallbackIcon = await iconToBase64(renderIconSvg(FaServer, 256, C.accent));

// Bad fallback — white generic icon (decorative noise)
const fallbackIcon = await iconToBase64(renderIconSvg(FaServer, 256, "FFFFFF"));
```
```

- [ ] **Step 3: Update the Required Packages section**

At line 23 of `pptxgenjs-guide.md`, the install command currently lists `react-icons`. No change needed — `react-icons` already includes both `fa` and `si` submodules. But update the check command at SKILL.md line 33 to also verify `si`:

In `SKILL.md`, update the check command (line 33):

```bash
NODE_PATH="$(npm root -g)" node -e "require('react-icons/fa'); require('react-icons/si'); require('sharp'); console.log('icons OK')"
```

- [ ] **Step 4: Commit**

```bash
git add -f .claude/skills/create-deck/references/pptxgenjs-guide.md .claude/skills/create-deck/SKILL.md
git commit -m "feat(create-deck): add Simple Icons integration with brand colors"
```

---

### Task 2: Add Logo Grid layout to pptxgenjs guide

**Files:**
- Modify: `.claude/skills/create-deck/references/pptxgenjs-guide.md` (insert after Three-Column Cards section, ~line 653)
- Modify: `.claude/skills/create-deck/SKILL.md` (update Layout Decision Strategy table, ~line 183)

- [ ] **Step 1: Read current Three-Column Cards section end**

Verify the insertion point after the Three-Column Cards closing `}` around line 653.

- [ ] **Step 2: Add Logo Grid layout pattern to pptxgenjs guide**

Insert after the Three-Column Cards section (after line 653), before Standard Bullets:

````markdown
### Logo Grid (Technology Stack)

A grid of named technologies with their brand logos. Use when a slide lists 4–8 named products/tools. Each cell shows the tool's logo circle, name, and a one-line description.

**Corporate-match mode (AMD default):** Render technology lists as plain icon+text rows or standard bullets instead of the card-based logo grid. The card surfaces and shadows violate the no-decorative-shapes rule. Logo grid is a rich-mode-only layout.

**Trigger signals (rich mode only):**
- Slide title contains "Stack", "Tools", "Platform", "Services", "Components"
- Content is a list of 4–8 named technologies (not narrative bullets)
- Each item is a product name, not a concept

**Grid sizing:**
- 4 items → single row of 4 wide cards
- 5–6 items → 2×3 grid
- 7–8 items → 2×4 grid
- Auto-calculate: `cols = n <= 4 ? n : (n <= 6 ? 3 : 4)`

```javascript
function addLogoGrid(pptx, title, items, iconImages, brandColors, theme) {
  const C = theme.colors;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  slide.addText(title, {
    x: M, y: 0.3, w: CONTENT_W, h: 0.7,
    fontSize: 28, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });

  const n = items.length;
  const cols = n <= 4 ? n : (n <= 6 ? 3 : 4);
  const rows = Math.ceil(n / cols);
  const gap = 0.3;
  const cardW = (CONTENT_W - (cols - 1) * gap) / cols;
  const cardH = (CONTENT_H - (rows - 1) * gap) / rows;
  const circleSize = Math.min(0.8, cardH * 0.35);

  items.forEach((item, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const x = M + col * (cardW + gap);
    const y = CONTENT_Y + row * (cardH + gap);

    // Card background
    slide.addShape(pptx.ShapeType.rect, {
      x: x, y: y, w: cardW, h: cardH,
      fill: { color: C.surface },
      shadow: cardShadow(),
    });

    // Top accent bar in tool's brand color
    const brandColor = brandColors[i] || C.accent;
    slide.addShape(pptx.ShapeType.rect, {
      x: x, y: y, w: cardW, h: 0.06,
      fill: { color: brandColor },
    });

    // Logo circle (dark bg so colored icons pop)
    const circleX = x + (cardW - circleSize) / 2;
    const circleY = y + 0.25;
    slide.addShape(pptx.ShapeType.ellipse, {
      x: circleX, y: circleY, w: circleSize, h: circleSize,
      fill: { color: C.background },
    });

    // Logo image (brand-colored SI icon)
    if (iconImages[i]) {
      const imgInset = circleSize * 0.15;
      slide.addImage({
        data: iconImages[i],
        x: circleX + imgInset, y: circleY + imgInset,
        w: circleSize - 2 * imgInset, h: circleSize - 2 * imgInset,
      });
    }

    // Tool name
    slide.addText(item.name, {
      x: x + 0.1, y: circleY + circleSize + 0.1, w: cardW - 0.2, h: 0.4,
      fontSize: 16, fontFace: theme.fonts.heading,
      color: C.text_primary, bold: true,
      align: "center",
    });

    // Description
    slide.addText(item.description, {
      x: x + 0.1, y: circleY + circleSize + 0.5, w: cardW - 0.2,
      h: cardH - circleSize - 1.0,
      fontSize: 12, fontFace: theme.fonts.body,
      color: C.text_body, align: "center", valign: "top",
    });
  });

  addFooter(slide, pptx, theme, slideNum, TOTAL);
  return slide;
}
```

**Usage with Simple Icons:**

```javascript
const { SiNomad, SiConsul, SiTerraform, SiDocker, SiTraefikproxy, SiMinio } = require("react-icons/si");

const tools = [
  { name: "Nomad", description: "Workload orchestration", icon: SiNomad, color: "00CA8E" },
  { name: "Consul", description: "Service discovery & mesh", icon: SiConsul, color: "F24C53" },
  { name: "Terraform", description: "Infrastructure as code", icon: SiTerraform, color: "844FBA" },
  { name: "Docker", description: "Container runtime", icon: SiDocker, color: "2496ED" },
  { name: "Traefik", description: "Edge routing & load balancing", icon: SiTraefikproxy, color: "24A1C1" },
  { name: "MinIO", description: "S3-compatible object storage", icon: SiMinio, color: "C72E49" },
];

// Pre-render brand-colored icons
const iconImages = await Promise.all(
  tools.map(t => iconToBase64(renderIconSvg(t.icon, 256, t.color)))
);
const brandColors = tools.map(t => t.color);

addLogoGrid(pptx, "Platform Stack", tools, iconImages, brandColors, theme);
```
````

- [ ] **Step 3: Update Layout Decision Strategy in SKILL.md**

In `SKILL.md`, add a new row to the Layout Decision Strategy table (after the "Standard bullet list" row, ~line 196):

```markdown
| 4–8 named technologies (tools, products, services) | Logo grid (brand icons + descriptions) | Layout 3 (Title and Content) |
```

- [ ] **Step 4: Commit**

```bash
git add -f .claude/skills/create-deck/references/pptxgenjs-guide.md .claude/skills/create-deck/SKILL.md
git commit -m "feat(create-deck): add logo grid layout for technology stack slides"
```

---

## Chunk 2: Section Dividers + Brand Badges

### Task 3: Replace section divider with numbered panel pattern

**Files:**
- Modify: `.claude/skills/create-deck/references/pptxgenjs-guide.md` (replace Section Divider at lines 136-163)

- [ ] **Step 1: Read the current Section Divider pattern**

Verify content at lines 136-163.

- [ ] **Step 2: Replace the Section Divider with the numbered panel pattern**

Replace the existing `### Section Divider` block (lines 136-163) with:

````markdown
### Section Divider

In corporate-match mode (AMD default), skip section dividers entirely — use normal content slides instead. In rich mode, use the numbered panel pattern below.

The numbered panel creates a split-panel design with a section number on the left and the title on the right. This is a major upgrade over a plain centered title.

```javascript
function addSectionDivider(pptx, sectionNumber, title, theme) {
  const C = theme.colors;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  // Left panel (18% width) — slightly lighter background
  const panelW = SW * 0.18;
  slide.addShape(pptx.ShapeType.rect, {
    x: 0, y: 0, w: panelW, h: SH,
    fill: { color: C.background_alt || C.surface },
  });

  // Large faint section number as watermark
  const numStr = String(sectionNumber).padStart(2, "0");
  slide.addText(numStr, {
    x: 0, y: SH * 0.3, w: panelW, h: 1.5,
    fontSize: 96, fontFace: theme.fonts.heading,
    color: C.text_secondary, bold: true,
    align: "center", valign: "middle",
    transparency: 70,
  });

  // Accent vertical bar at right edge of left panel
  slide.addShape(pptx.ShapeType.rect, {
    x: panelW - 0.04, y: 0, w: 0.04, h: SH,
    fill: { color: C.accent },
  });

  // Right panel content
  const rightX = panelW + 0.6;
  const rightW = SW - rightX - M;

  // "SECTION" label with letter-spacing
  slide.addText("SECTION", {
    x: rightX, y: SH * 0.35, w: rightW, h: 0.4,
    fontSize: 12, fontFace: theme.fonts.body,
    color: C.text_secondary,
    charSpacing: 6,
  });

  // Section title
  slide.addText(title, {
    x: rightX, y: SH * 0.42, w: rightW, h: 1.2,
    fontSize: 42, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });

  // Short accent underline below title
  slide.addShape(pptx.ShapeType.rect, {
    x: rightX, y: SH * 0.42 + 1.25, w: 2.0, h: 0.06,
    fill: { color: C.accent },
  });

  addFooter(slide, pptx, theme, slideNum, TOTAL);
  return slide;
}
```

**Conservative snazz variant (corporate themes):** If section dividers are enabled but the theme is corporate/minimalist, skip the numbered panel. Use a full-width accent bar across the top, section title at 36pt, and a subtle branded watermark:

```javascript
function addSectionDividerConservative(pptx, title, theme) {
  const C = theme.colors;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  // Full-width accent bar at top
  slide.addShape(pptx.ShapeType.rect, {
    x: 0, y: 0, w: SW, h: 0.08,
    fill: { color: C.accent },
  });

  // Section title — vertically centered
  slide.addText(title.toUpperCase(), {
    x: M, y: 0, w: CONTENT_W, h: SH,
    fontSize: 36, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
    charSpacing: 4,
    valign: "middle",
  });

  addFooter(slide, pptx, theme, slideNum, TOTAL);
  return slide;
}
```
````

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/create-deck/references/pptxgenjs-guide.md
git commit -m "feat(create-deck): upgrade section dividers to numbered panel pattern"
```

---

### Task 4: Add Brand Badge pattern to pptxgenjs guide

**Files:**
- Modify: `.claude/skills/create-deck/references/pptxgenjs-guide.md` (insert after the footer helper section, before Complete Script Structure)

- [ ] **Step 1: Identify insertion point**

The Brand Badge pattern goes after the `### Footer Helper` section (ends ~line 808), before `## Complete Script Structure` (~line 811).

- [ ] **Step 2: Add Brand Badge pattern**

Insert before `## Complete Script Structure`:

````markdown
### Brand Badge

When a slide is specifically about a vendor's hardware or product (e.g., "AMD MI300X Performance"), add a badge in the top-right corner. This is low-effort, high-impact — it signals "this slide is about [vendor product]" without changing the slide's content structure.

```javascript
function addBrandBadge(slide, pptx, vendorLogo, productName, theme) {
  const C = theme.colors;
  const badgeW = 1.8;
  const badgeX = RIGHT_EDGE - badgeW;  // 12.69 - 1.8 = 10.89" — stays within safe area
  const badgeY = 0.2;

  // Badge background
  slide.addShape(pptx.ShapeType.rect, {
    x: badgeX, y: badgeY, w: badgeW, h: 0.8,
    fill: { color: C.surface },
    rectRadius: 0.05,
  });

  // Vendor logo inside badge
  if (vendorLogo) {
    slide.addImage({
      data: vendorLogo,
      x: badgeX + 0.1, y: badgeY + 0.08, w: 0.64, h: 0.64,
    });
  }

  // Product name
  slide.addText(productName, {
    x: badgeX + 0.82, y: badgeY + 0.15, w: badgeW - 0.92, h: 0.5,
    fontSize: 14, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
    valign: "middle",
  });
}
```

**When to use:** Slides that mention specific vendor hardware (GPUs, CPUs, accelerators), named cloud services, or branded product lines. Works especially well for hardware/GPU slides in vendor-context decks.

**When NOT to use:** Generic concept slides, section dividers, title/closing slides, or slides that discuss multiple vendors equally.
````

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/create-deck/references/pptxgenjs-guide.md
git commit -m "feat(create-deck): add brand badge pattern for vendor product slides"
```

---

## Chunk 3: Icon Row Fix + Column Headers with Logos

### Task 5: Fix Icon Row empty space issue

**Files:**
- Modify: `.claude/skills/create-deck/references/pptxgenjs-guide.md` (update Icon + Text Rows section, lines 231-303)

- [ ] **Step 1: Read current Icon + Text Rows section**

Verify content at lines 231-303.

- [ ] **Step 2: Remove the old standalone no-icon fallback snippet**

Delete the standalone no-icon fallback code block at lines 237-252 (the snippet that starts `// No-icon fallback: teal left-accent bar`). This snippet is superseded by the integrated fallback logic in the updated `addIconRows` function below. Leaving it would create two contradicting fallback patterns.

- [ ] **Step 3: Update the Icon + Text Rows pattern**

Replace the `addIconRows` function (lines 254-303) with the improved version that divides full content height evenly and adds separator lines:

````markdown
```javascript
function addIconRows(pptx, title, items, iconImages, theme) {
  const C = theme.colors;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  slide.addText(title, {
    x: M, y: 0.3, w: CONTENT_W, h: 0.7,
    fontSize: 28, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });

  // Divide full content height evenly — prevents 30-40% blank space
  const rowH = CONTENT_H / items.length;

  items.forEach((item, i) => {
    const y = CONTENT_Y + i * rowH;

    // Vertically center icon within the row
    const circleSize = 0.7;
    const circleY = y + rowH / 2 - circleSize / 2;

    // No-icon fallback: accent bar instead of empty circle
    if (!iconImages || !iconImages[i]) {
      slide.addShape(pptx.ShapeType.rect, {
        x: M + 0.56, y: circleY, w: 0.06, h: circleSize,
        fill: { color: C.accent },
      });
    } else {
      // Icon circle
      slide.addShape(pptx.ShapeType.ellipse, {
        x: M + 0.56, y: circleY, w: circleSize, h: circleSize,
        fill: { color: C.accent },
      });
      // Icon image
      slide.addImage({
        data: iconImages[i],
        x: M + 0.68, y: circleY + 0.12, w: 0.46, h: 0.46,
      });
    }

    // Label — vertically centered in top portion of row
    slide.addText(item.label, {
      x: M + 1.56, y: y + rowH * 0.15, w: CONTENT_W - 1.56, h: 0.4,
      fontSize: 20, fontFace: theme.fonts.heading,
      color: C.text_primary, bold: true,
    });

    // Description — below label
    slide.addText(item.description, {
      x: M + 1.56, y: y + rowH * 0.15 + 0.4, w: CONTENT_W - 1.56,
      h: rowH * 0.55,
      fontSize: 14, fontFace: theme.fonts.body,
      color: C.text_body,
    });

    // Separator line between rows (not after last item)
    if (i < items.length - 1) {
      slide.addShape(pptx.ShapeType.rect, {
        x: M + 1.56, y: y + rowH - 0.01, w: CONTENT_W - 1.56, h: 0.01,
        fill: { color: C.surface },
      });
    }
  });

  addFooter(slide, pptx, theme, slideNum, TOTAL);
  return slide;
}
```
````

Also update the intro text above the function (lines 231-233) to replace the old description:

```markdown
### Icon + Text Rows

Row height divides the full content area evenly (`CONTENT_H / items.length`), preventing the 30–40% blank space that comes from fixed row heights. Icons are vertically centered within each row. Separator lines between rows break up the space without adding visual noise.

**No-icon fallback:** When no icon image is available for a row, render an accent-colored left bar (0.06" × 0.7") instead of an empty circle. This avoids plain solid circles that look like decorative blobs.
```

- [ ] **Step 4: Commit**

```bash
git add -f .claude/skills/create-deck/references/pptxgenjs-guide.md
git commit -m "fix(create-deck): icon row height fills content area, add separator lines"
```

---

### Task 6: Add Column Headers with Logos pattern

**Files:**
- Modify: `.claude/skills/create-deck/references/pptxgenjs-guide.md` (enhance Two-Column section, lines 521-598)

- [ ] **Step 1: Read current Two-Column section**

Verify content at lines 521-598.

- [ ] **Step 2: Add logo-enhanced column header variant**

After the existing `addTwoColumn` function closing (line 597), add a new variant:

````markdown
#### Column Headers with Logos

When each column represents a named tool or technology, adding the tool's logo to the column header creates a purposeful layout instead of "two lists next to each other."

```javascript
function addTwoColumnWithLogos(pptx, title, leftHeader, rightHeader, leftContent, rightContent, leftIcon, rightIcon, theme) {
  const C = theme.colors;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  slide.addText(title, {
    x: M, y: 0.3, w: CONTENT_W, h: 0.7,
    fontSize: 28, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });

  const col1W = 5.70;
  const gutter = 0.36;
  const col2X = M + col1W + gutter;
  const col2W = CONTENT_W - col1W - gutter;
  const headerH = 0.48;

  // Helper: render a column header with logo
  function addColumnHeader(x, w, header, iconData) {
    // Header background pill
    slide.addShape(pptx.ShapeType.rect, {
      x: x, y: CONTENT_Y, w: w, h: headerH,
      fill: { color: C.surface },
    });

    // Accent bar on top of header
    slide.addShape(pptx.ShapeType.rect, {
      x: x, y: CONTENT_Y, w: w, h: 0.05,
      fill: { color: C.accent },
    });

    // Logo inside header (if available)
    if (iconData) {
      slide.addImage({
        data: iconData,
        x: x + 0.1, y: CONTENT_Y + 0.07, w: 0.34, h: 0.34,
      });
    }

    // Header text (offset right if logo present)
    const textX = iconData ? x + 0.55 : x + 0.15;
    slide.addText(header, {
      x: textX, y: CONTENT_Y + 0.02, w: w - (textX - x) - 0.1, h: headerH - 0.04,
      fontSize: 18, fontFace: theme.fonts.heading,
      color: C.text_primary, bold: true, valign: "middle",
    });
  }

  // Column headers
  if (leftHeader) addColumnHeader(M, col1W, leftHeader, leftIcon);
  if (rightHeader) addColumnHeader(col2X, col2W, rightHeader, rightIcon);

  // Vertical divider
  slide.addShape(pptx.ShapeType.rect, {
    x: M + col1W + gutter / 2 - 0.01, y: CONTENT_Y,
    w: 0.02, h: CONTENT_H,
    fill: { color: C.surface },
  });

  // Column content (below headers)
  const bodyY = CONTENT_Y + headerH + 0.15;
  const bodyH = CONTENT_H - headerH - 0.15;

  slide.addText(leftContent.map(item => ({
    text: item,
    options: {
      fontSize: 16, fontFace: theme.fonts.body,
      color: C.text_body, bullet: true,
      breakLine: true, paraSpaceAfter: 8,
    },
  })), {
    x: M, y: bodyY, w: col1W, h: bodyH, valign: "top",
  });

  slide.addText(rightContent.map(item => ({
    text: item,
    options: {
      fontSize: 16, fontFace: theme.fonts.body,
      color: C.text_body, bullet: true,
      breakLine: true, paraSpaceAfter: 8,
    },
  })), {
    x: col2X, y: bodyY, w: col2W, h: bodyH, valign: "top",
  });

  addFooter(slide, pptx, theme, slideNum, TOTAL);
  return slide;
}
```

**When to use:** When both columns represent named technologies, tools, or products that have recognizable logos. Falls back to the standard `addTwoColumn` when columns are generic concepts (e.g., "Pros" vs "Cons").
````

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/create-deck/references/pptxgenjs-guide.md
git commit -m "feat(create-deck): add two-column with logo headers variant"
```

---

## Chunk 4: Things to Avoid + Conservative Snazz + SKILL.md Updates

### Task 7: Add "Things to Avoid" section to pptxgenjs guide

**Files:**
- Modify: `.claude/skills/create-deck/references/pptxgenjs-guide.md` (add after Critical Pitfalls section, ~line 97)

- [ ] **Step 1: Read the current Critical Pitfalls section**

Verify the section ends around line 97.

- [ ] **Step 2: Add visual pitfalls after Critical Pitfalls**

Insert after the Shadow Factory Pattern section (line 97), before `## Layout Patterns`:

```markdown
### Visual Pitfalls

| Pitfall | Problem | Alternative |
|---------|---------|-------------|
| `rotate` on text | Rotation doesn't render reliably across LibreOffice and PowerPoint — vertical text becomes garbled or mispositioned | Use a thin rect shape or dot row for vertical decoration; keep all text horizontal |
| All-white SI icons | Simple Icons are designed with brand colors — white versions lose recognition value entirely | Use the actual hex brand color from simpleicons.org |
| Reusing `cardShadow` objects | Still a corruption risk even with named pattern | Always use the factory function `const cardShadow = () => ({...})` in every script |
```

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/create-deck/references/pptxgenjs-guide.md
git commit -m "docs(create-deck): add visual pitfalls to avoid section"
```

---

### Task 8: Add Conservative Snazz section to python-pptx guide

**Files:**
- Modify: `.claude/skills/create-deck/references/python-pptx-guide.md` (add before Troubleshooting section, ~line 533)

- [ ] **Step 1: Read the current end of python-pptx guide**

Verify the Troubleshooting section starts around line 533.

- [ ] **Step 2: Add Conservative Snazz section**

Insert before `## Troubleshooting`:

````markdown
## Conservative Snazz (Template-Based)

For python-pptx decks using `corp.pptx`, visual enhancements are constrained by the template but still achievable. The key insight: **don't fight the template's structure — add on top of it.** Floating images and shapes can be layered over any template layout without touching placeholder indices.

### Logo Badges

Add a vendor or tool logo as a floating image on relevant slides (not in a placeholder). Works on any layout:

```python
from pptx.util import Inches

def add_logo_badge(slide, image_path, x=Inches(10.5), y=Inches(0.3), w=Inches(0.8)):
    """Add a floating logo badge in the top-right area."""
    slide.shapes.add_picture(image_path, x, y, w)
```

### Tech Stack Icon Strip

A row of small tool logos at the bottom of a slide (above the footer zone) as a "tech stack" badge strip:

```python
def add_icon_strip(slide, icon_paths, y=Inches(6.2), icon_size=Inches(0.45), gap=Inches(0.15)):
    """Add a row of small icons near the bottom of the slide."""
    total_width = len(icon_paths) * (icon_size + gap) - gap
    start_x = (Inches(13.33) - total_width) // 2  # center the strip
    for i, path in enumerate(icon_paths):
        x = start_x + i * (icon_size + gap)
        slide.shapes.add_picture(path, x, y, icon_size, icon_size)
```

### Stat Callouts

Large numbers in the AMD accent color (`00C2DE`) draw the eye even in an otherwise plain template layout. Add as floating text boxes over a Title and Content layout:

```python
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

def add_stat_callout(slide, value, label, x, y, w=Inches(3.0)):
    """Add a large colored stat number with a label below it."""
    # Large number
    txBox = slide.shapes.add_textbox(x, y, w, Inches(0.8))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = value
    run.font.size = Pt(48)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x00, 0xC2, 0xDE)  # AMD teal accent
    p.alignment = PP_ALIGN.CENTER

    # Label below
    txBox2 = slide.shapes.add_textbox(x, y + Inches(0.85), w, Inches(0.4))
    tf2 = txBox2.text_frame
    p2 = tf2.paragraphs[0]
    p2.text = label
    p2.font.size = Pt(14)
    p2.font.color.rgb = RGBColor(0x9D, 0x9F, 0xA2)  # text_secondary
    p2.alignment = PP_ALIGN.CENTER
```

### Header with Logo

Works in python-pptx too: add a colored shape + image on top of a layout placeholder's header area. This creates a visual header row without modifying the placeholder:

```python
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

def add_header_with_logo(slide, text, logo_path, x, y, w, accent_color=RGBColor(0x00, 0xC2, 0xDE)):
    """Add a styled header bar with logo on top of a placeholder area."""
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    RECT = MSO_SHAPE_TYPE.RECTANGLE

    # Header background
    shape = slide.shapes.add_shape(
        RECT, x, y, w, Inches(0.48)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(0x63, 0x64, 0x66)  # surface
    shape.line.fill.background()

    # Accent bar on top
    accent = slide.shapes.add_shape(RECT, x, y, w, Inches(0.05))
    accent.fill.solid()
    accent.fill.fore_color.rgb = accent_color
    accent.line.fill.background()

    # Logo
    if logo_path:
        slide.shapes.add_picture(
            logo_path,
            x + Inches(0.1), y + Inches(0.07),
            Inches(0.34), Inches(0.34)
        )

    # Text (offset for logo)
    text_x = x + (Inches(0.55) if logo_path else Inches(0.15))
    txBox = slide.shapes.add_textbox(text_x, y + Inches(0.02), w - (text_x - x) - Inches(0.1), Inches(0.44))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = text
    run.font.size = Pt(18)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
```
````

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/create-deck/references/python-pptx-guide.md
git commit -m "feat(create-deck): add conservative snazz patterns for python-pptx"
```

---

### Task 9: Update SKILL.md layout decision strategy and references

**Files:**
- Modify: `.claude/skills/create-deck/SKILL.md`

- [ ] **Step 1: Read current SKILL.md layout decision strategy**

Verify the Layout Decision Strategy table at lines 183-201.

- [ ] **Step 2: Update the Layout Decision Strategy table**

Replace the existing table (lines 183-201) with the updated version that includes logo grid and new patterns:

```markdown
| Content Signal | pptxgenjs Layout | python-pptx Layout |
|---|---|---|
| First section heading in outline | Title slide (right-side text, left visual area) | Layout 0 (Title Slide) |
| Section heading with no slide children (corp-match) | **SKIP — do not render a slide** | N/A |
| Section heading with no slide children (rich mode) | Section divider (numbered panel) | Layout 26 (Divider) |
| 3-4 bullets with bold lead-ins (`Key: value`) | Card grid with icons (2x2) | Layout 3 (Title and Content) |
| 4–8 named technologies (tools, products, services) | Logo grid (brand SI icons + descriptions) | Layout 3 (Title and Content) |
| Prominent number or statistic | Stat callout (large number, 60-72pt) | Layout 3 + floating stat callout |
| Code blocks or CLI commands | Code panel (dark bg, mono font) | Layout 28 (Developer Code) |
| `LAYOUT: two_column` or `\|\|\|` separator | Two-column (with logos if named tools) | Layout 5 (Two Content) |
| `LAYOUT: numbered` or sequential steps | Process flow (numbered boxes) | Layout 3 (Title and Content) |
| 3 parallel items with headings | Three-column cards | Layout 17 (Three Content) |
| Standard bullet list | Icon + text rows or standard bullets | Layout 3 (Title and Content) |
| `IMAGE:` with no bullets | Image slide (full) | Layout 7 (Title Only) + centered image |
| `IMAGE:` with bullets | Image + text side-by-side | Layout 3 + repositioned placeholder |
| `LAYOUT: diagram` without `IMAGE:` | N/A | Layout 3 (Title and Content) + print warning |
| Slide about specific vendor product | Any layout + brand badge (top-right) | Any layout + floating logo badge |
| Last slide / thank you | Closing slide | Layout 30 (Closing Logo) |
```

- [ ] **Step 3: Add icon selection guidance to SKILL.md**

After the `### Honoring Directives` section (~line 223), add:

```markdown
### Icon Selection Strategy

When generating pptxgenjs scripts that include icons:

1. **Named technologies first** → Check `react-icons/si` (Simple Icons) for brand logos. Use brand-accurate colors.
2. **Generic concepts** → Use `react-icons/fa` (Font Awesome) in the theme's accent color (not white).
3. **No match** → Use an accent-colored left bar instead of an empty/meaningless icon circle.

**Discovery:** `Object.keys(require("react-icons/si")).filter(k => k.toLowerCase().includes("searchterm"))`

**Logo grid trigger:** When a slide lists 4–8 named technologies (title contains "Stack", "Tools", "Platform", "Services", "Components"), prefer the Logo Grid layout over Icon + Text Rows.
```

- [ ] **Step 4: Update layout variety rule fallbacks**

In the Layout Variety Rule section (~line 204-212), add a new fallback:

```markdown
- Two icon+text rows in a row → make the second one a logo grid (if items are named technologies) or card grid
```

- [ ] **Step 5: Commit**

```bash
git add -f .claude/skills/create-deck/SKILL.md
git commit -m "feat(create-deck): update layout strategy with logo grid, brand badges, icon selection"
```

---

## Summary of Changes

| File | What Changed |
|------|-------------|
| `pptxgenjs-guide.md` | Simple Icons section, Logo Grid layout, numbered panel dividers, brand badge, icon row fix, column headers with logos, visual pitfalls |
| `python-pptx-guide.md` | Conservative snazz section (logo badges, icon strips, stat callouts, header with logo) |
| `SKILL.md` | Updated layout decision strategy, icon selection guidance, SI check in deps, variety rule updates |

Total: ~9 tasks across 4 chunks. All changes are documentation updates — no Python/JS runtime code changes.
