# pptxgenjs Generation Guide

Reference for generating PowerPoint decks with pptxgenjs using the helper library. Claude reads this when creating deck scripts.

## IMPORTANT: Slide Dimensions

All coordinates use **LAYOUT_WIDE** (13.33" x 7.5").

**Do NOT use LAYOUT_16x9** — despite the name, it is only 10" x 5.625". All coordinates will be wrong and content will clip off the right and bottom edges.

| Layout Constant | Width | Height | Use? |
|---|---|---|---|
| `LAYOUT_WIDE` | 13.33" | 7.5" | **Yes — always use this** |
| `LAYOUT_16x9` | 10.0" | 5.625" | No — coordinates won't fit |

The helper library sets this automatically via `createDeck()`.

## Setup & Execution

### Required Packages

```bash
npm install -g pptxgenjs react-icons react react-dom sharp
```

### Script Template

Scripts are ES modules (`.mjs`) that import from the helper library:

```javascript
import {
  createDeck, addTitleSlide, addBulletSlide, addImageSlide,
  addImageBulletsSlide, addProcessFlow, addTwoColumn, addCardGrid,
  addStatCallout, addCodeSlide, addIconRowsSlide, addLogoGridSlide,
  addSectionDivider, addClosingSlide, addFooter, renderIconSvg,
  iconToBase64, preRenderIcons, cardShadow, SW, SH,
} from '../lib/pptxgenjs-helpers.mjs';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

async function buildDeck() {
  const deck = createDeck('themes/amd.yaml');
  let sn = 1;

  // Pre-render icons
  const { FaServer } = require('react-icons/fa');
  const icons = await preRenderIcons({
    server: { component: FaServer, color: '00C2DE' },
  });

  addTitleSlide(deck, "Deck Title", "Subtitle", sn++);
  addBulletSlide(deck, "Overview", ["Point 1", "Point 2"], sn++);
  addClosingSlide(deck, sn);

  await deck.save('output/deck.pptx');
}

buildDeck().catch(console.error);
```

### Execution

```bash
NODE_PATH="$(npm root -g)" node output/script.mjs
```

`NODE_PATH` is required because packages are installed globally.

## Critical Pitfalls

These cause **silent file corruption** — PowerPoint will try to repair or refuse to open the file:

| Pitfall | Wrong | Correct |
|---------|-------|---------|
| Hex color prefix | `"#00B4D8"` | `"00B4D8"` |
| 8-char hex (opacity) | `"00B4D880"` | Use `opacity` property instead |
| Reusing shadow objects | `const s = {...}; shape1({shadow: s}); shape2({shadow: s})` | Use `cardShadow()` factory from helpers |
| Rounded rect + borders | `ROUNDED_RECTANGLE` with accent border | Use `RECTANGLE` instead |

### Additional Gotchas

- Use `bullet: true` — not unicode `•` characters
- Use `breakLine: true` between text array items for line breaks
- Avoid `lineSpacing` with bullets — use `paraSpaceAfter` instead
- Property is `charSpacing` — not `letterSpacing` (silently ignored)
- `valign` is `"top"`, `"middle"`, `"bottom"` — not CSS values

### Visual Pitfalls

| Pitfall | Problem | Alternative |
|---------|---------|-------------|
| `rotate` on text | Rotation doesn't render reliably across LibreOffice and PowerPoint — vertical text becomes garbled or mispositioned | Use a thin rect shape or dot row for vertical decoration; keep all text horizontal |
| All-white SI icons | Simple Icons are designed with brand colors — white versions lose recognition value entirely | Use the actual hex brand color from simpleicons.org |
| Reusing `cardShadow` objects | Still a corruption risk even with named pattern | Always use the `cardShadow()` factory function from the helper library |

## Helper Library API

All slide builders accept a `deck` object returned by `createDeck()`. The deck bundles `pptx`, `theme`, and `layout` so callers don't juggle multiple arguments.

### createDeck(themePath)

Creates a new deck with theme and layout computed from a YAML file.

```javascript
const deck = createDeck('themes/amd.yaml');
// deck.pptx   — pptxgenjs instance (layout already set)
// deck.theme  — parsed theme: { colors, fonts, logo, slide, footer }
// deck.layout — computed geometry: { M, CONTENT_W, CONTENT_Y, FOOTER_Y, CONTENT_H, RIGHT_EDGE }
// deck.save(outputPath) — async, writes file and prints size
```

**Theme colors available via `deck.theme.colors`:**

| Key | Description | AMD Default |
|-----|-------------|-------------|
| `background` | Slide background | `000000` |
| `surface` | Card/panel backgrounds | `636466` |
| `text_primary` | Titles, headings | `FFFFFF` |
| `text_secondary` | Labels, metadata | `9D9FA2` |
| `text_body` | Body text, bullets | `D5D5D5` |
| `accent` | Primary accent | `00C2DE` |
| `accent_alt` | Secondary accent | `C1A968` |
| `warning` | Warning/error accent | `EF4444` |

### Layout Geometry

Computed by `computeLayout(theme)` and available on `deck.layout`:

| Constant | Value (default margin) | Description |
|----------|----------------------|-------------|
| `M` | 0.64 | Margin from slide edges |
| `CONTENT_W` | 12.05 | Usable content width |
| `CONTENT_Y` | 1.2 | Top of content area (below title) |
| `FOOTER_Y` | 6.9 | Top of footer zone |
| `CONTENT_H` | 5.7 | Usable content height |
| `RIGHT_EDGE` | 12.69 | Rightmost safe x+w |

Also exported: `SW = 13.33`, `SH = 7.5` (slide dimensions).

### addTitleSlide(deck, title, subtitle, slideNum)

AMD style: logo on left half, title on right, accent bar.

- `title` — Main title text (36pt heading, bold)
- `subtitle` — Optional subtitle (18pt body, secondary color)
- Automatically uses logo from theme (derives `-logo.jpg` from wordmark path)

### addBulletSlide(deck, title, bullets, slideNum, notes?)

Standard bullet slide with adaptive font sizing.

- `bullets` — Array of strings or `{text, subs}` objects. Supports bold lead-in: `"**Bold** — rest of text"`
- Font scaling: ≤4 bullets → 22/24pt, 5 → 20/22pt, 6-7 → 18/20pt, 8+ → 16/18pt
- `notes` — Optional speaker notes string
- Uses `valign: "top"` (never `"middle"` — avoids gap below title)

**Bold lead-in patterns detected automatically:**
```
"**Key Concept** — description here"   → bold lead-in with em dash
"**Step Name** description"            → bold prefix, normal rest
"Plain bullet text"                    → standard bullet
```

**Sub-bullet support:** Pass `{text, subs}` objects for items with sub-bullets:
```javascript
addBulletSlide(deck, "Overview", [
  "Plain top-level bullet",
  { text: "**Category** — main point", subs: [
    "Sub-point one",
    "Sub-point two",
  ]},
  "Another plain bullet",
], sn++);
```

### Icon + Text Rows

Row height divides the full content area evenly (`CONTENT_H / items.length`), preventing the 30–40% blank space that comes from fixed row heights. Icons are vertically centered within each row. Separator lines between rows break up the space without adding visual noise.

**No-icon fallback:** When no icon image is available for a row, render an accent-colored left bar (0.06" × 0.7") instead of an empty circle. This avoids plain solid circles that look like decorative blobs.

### addIconRowsSlide(deck, title, items, iconImages, slideNum, notes?)

Rows with icon circles (or accent bars if no icon) and label/description.

- `items` — Array of `{ label, desc }` objects
- `iconImages` — Array of base64 data URIs (or null entries for accent-bar fallback)
- `notes` — Optional speaker notes string
- Row height divides full content area evenly: `CONTENT_H / items.length` — no fixed heights

**Internal implementation reference:**

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

### addProcessFlow(deck, title, steps, slideNum, notes?)

Numbered step boxes with arrows. Auto-scales layout.

- `steps` — Array of strings. Use `\n` to split label from description: `"Step Label\nStep description text"`
- `notes` — Optional speaker notes string
- ≤4 steps → single row with arrows
- 5+ steps → two-row layout (top row gets `ceil(n/2)`, bottom gets rest, centered)
- Step boxes have surface background, shadow, step number in accent color

### addTwoColumn(deck, title, leftHeader, rightHeader, leftItems, rightItems, slideNum, notes?)

Two-column layout with headers and vertical divider.

- `leftHeader` / `rightHeader` — Column header text (accent color, bold, 20pt). Pass empty string to omit.
- `leftItems` / `rightItems` — Arrays of bullet strings
- `notes` — Optional speaker notes string
- Automatic vertical divider line between columns (surface color)
- Column widths: left 5.70", gutter 0.36", right fills remainder

#### Column Headers with Logos

When each column represents a named tool or technology, add the tool's logo to the column header for a purposeful layout instead of "two lists next to each other."

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

  function addColumnHeader(x, w, header, iconData) {
    slide.addShape(pptx.ShapeType.rect, {
      x, y: CONTENT_Y, w, h: headerH,
      fill: { color: C.surface },
    });
    slide.addShape(pptx.ShapeType.rect, {
      x, y: CONTENT_Y, w, h: 0.05,
      fill: { color: C.accent },
    });
    if (iconData) {
      slide.addImage({ data: iconData, x: x + 0.1, y: CONTENT_Y + 0.07, w: 0.34, h: 0.34 });
    }
    const textX = iconData ? x + 0.55 : x + 0.15;
    slide.addText(header, {
      x: textX, y: CONTENT_Y + 0.02, w: w - (textX - x) - 0.1, h: headerH - 0.04,
      fontSize: 18, fontFace: theme.fonts.heading,
      color: C.text_primary, bold: true, valign: "middle",
    });
  }

  if (leftHeader) addColumnHeader(M, col1W, leftHeader, leftIcon);
  if (rightHeader) addColumnHeader(col2X, col2W, rightHeader, rightIcon);

  slide.addShape(pptx.ShapeType.rect, {
    x: M + col1W + gutter / 2 - 0.01, y: CONTENT_Y, w: 0.02, h: CONTENT_H,
    fill: { color: C.surface },
  });

  const bodyY = CONTENT_Y + headerH + 0.15;
  const bodyH = CONTENT_H - headerH - 0.15;

  slide.addText(leftContent.map(item => ({
    text: item, options: { fontSize: 16, fontFace: theme.fonts.body, color: C.text_body, bullet: true, breakLine: true, paraSpaceAfter: 8 },
  })), { x: M, y: bodyY, w: col1W, h: bodyH, valign: "top" });

  slide.addText(rightContent.map(item => ({
    text: item, options: { fontSize: 16, fontFace: theme.fonts.body, color: C.text_body, bullet: true, breakLine: true, paraSpaceAfter: 8 },
  })), { x: col2X, y: bodyY, w: col2W, h: bodyH, valign: "top" });

  addFooter(slide, slideNum, theme);
  return slide;
}
```

**When to use:** Both columns represent named technologies or products with recognizable logos. Falls back to `addTwoColumn` when columns are generic concepts (e.g., "Pros" vs "Cons").

### addCardGrid(deck, title, cards, slideNum, notes?)

2x2 or 2x3 card grid with accent bars and optional icons.

- `cards` — Array of `{ title, body, iconImg? }` objects
- `notes` — Optional speaker notes string
- ≤4 cards → 2-column layout; 5-6 → 3-column layout
- Each card has surface background, left accent bar (rotating colors), shadow
- If `card.iconImg` is set, renders icon circle in top-left of card

### addStatCallout(deck, title, stats, slideNum, notes?)

Large colored numbers with labels.

- `stats` — Array of `{ value, label, desc? }` objects
- `notes` — Optional speaker notes string
- `value` renders at 48pt in accent color
- Columns auto-calculate width: `CONTENT_W / stats.length`

### addCodeSlide(deck, title, code, slideNum, notes?)

Dark code panel with monospace font.

- `code` — Code text string (use `\n` for line breaks)
- `notes` — Optional speaker notes string
- Panel background: `0D1117` (GitHub dark), accent bar on top
- Font: Consolas 14pt, color `58A6FF`

### addImageSlide(deck, title, imagePath, slideNum, notes?)

Full-image slide. Image fills the content area with aspect ratio preserved.

- `imagePath` — File path string or base64 data URI (prefix `"image/png;base64,..."`)
- `notes` — Optional speaker notes string
- Image uses `sizing: { type: 'contain' }` — fits within CONTENT_W × CONTENT_H without distortion
- Data URIs (starting with `"image/"`) are passed as `data:` to pptxgenjs
- Missing files show a gray placeholder with `[Image: <path>]` text

```javascript
// File path
addImageSlide(deck, "Architecture Overview", "images/arch-diagram.png", sn++, "Key: blue = services, green = data stores");

// Data URI (e.g., from icon rendering)
addImageSlide(deck, "Logo", iconDataUri, sn++);
```

### addImageBulletsSlide(deck, title, imagePath, bullets, slideNum, notes?)

Split layout: image on the left (~48%), bullets on the right (~52%), 0.36" gutter.

- `imagePath` — Same as `addImageSlide` (file path or data URI)
- `bullets` — Array of strings or `{text, subs}` objects (same format as `addBulletSlide`)
- `notes` — Optional speaker notes string
- Supports bold lead-in patterns and sub-bullets (reuses `addBulletSlide` internals)
- Adaptive font sizing based on bullet count (slightly smaller than full-width bullet slides)

```javascript
addImageBulletsSlide(deck, "System Design", "images/topology.png", [
  "**Frontend** — React SPA with SSR",
  "**API Layer** — GraphQL gateway",
  { text: "**Data Stores**", subs: ["PostgreSQL primary", "Redis cache"] },
], sn++, "Discuss migration timeline");
```

### addSectionDivider(deck, sectionNumber, title, slideNum)

Numbered panel on left, title on right (rich mode only).

- `sectionNumber` — Section number (rendered as zero-padded watermark)
- Large number at 96pt with 70% transparency, accent vertical bar
- "SECTION" label with letter-spacing, title at 42pt

**Corporate-match mode (AMD default):** Skip section dividers entirely — do not render a slide for section headings with no content.

**Conservative snazz variant** — for corporate themes that want minimal section markers without the numbered panel:

```javascript
function addSectionDividerConservative(pptx, title, theme, slideNum) {
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

  addFooter(slide, slideNum, theme);
  return slide;
}
```

### addClosingSlide(deck, slideNum, notes?)

Centered wordmark, no footer.

- Uses logo from theme, centered at 4.0" width
- `notes` — Optional speaker notes string
- Footer is suppressed (both logo and slide number)

### addFooter(slide, slideNum, theme, opts?)

Add slide number and logo to a slide. Called automatically by all slide builders.

- `opts.suppressLogo` — Omit logo (default: false)
- `opts.suppressNumber` — Omit slide number (default: false)
- Use both suppress flags on the closing slide

### cardShadow()

Factory function returning a fresh shadow object. **Never reuse shadow objects** — pptxgenjs mutates them in place.

```javascript
slide.addShape(pptx.ShapeType.rect, { shadow: cardShadow() });
```

## Icon Integration

### renderIconSvg(IconComponent, size?, color?)

Render a react-icons component to SVG string.

- `size` — Pixel size (default 256)
- `color` — Hex color without `#` (default "FFFFFF")

### iconToBase64(svgString, size?)

Convert SVG string to base64 PNG data URI via sharp.

Returns `"image/png;base64,..."` — pass directly to `slide.addImage({ data: ... })`.

### preRenderIcons(iconMap)

Batch pre-render icons to base64.

```javascript
const { FaServer, FaCloud } = require('react-icons/fa');
const { SiDocker } = require('react-icons/si');

const icons = await preRenderIcons({
  server: { component: FaServer, color: '00C2DE' },
  cloud:  { component: FaCloud, color: '00C2DE' },
  docker: { component: SiDocker, color: '2496ED' },
});

// Use: slide.addImage({ data: icons.docker, x: 1, y: 1, w: 0.5, h: 0.5 });
```

### Simple Icons (Brand Logos)

**Before choosing icons for any slide mentioning a named technology, check `react-icons/si` first.** Simple Icons provide real product logos with brand-accurate colors.

#### Discovery Pattern

```javascript
const si = require('react-icons/si');
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

#### Icon Fallback Priority

1. **SI with brand color** → `react-icons/si` in the technology's official hex color
2. **FA in accent color** → `react-icons/fa` using the theme's accent color
3. **FA in white** → Last resort only when accent color clashes

```javascript
// Good fallback — accent-colored FA icon
const fallbackIcon = await iconToBase64(renderIconSvg(FaServer, 256, "00C2DE"));

// Bad fallback — white generic icon (decorative noise)
const fallbackIcon = await iconToBase64(renderIconSvg(FaServer, 256, "FFFFFF"));
```

**When multiple items share the same fallback icon:**
- If 3+ items would use the same FA icon, use accent-bar fallback for ALL of them instead
- Alternatively, vary FA icons by concept (FaDatabase, FaServer, FaCloud for different infra)
- Never repeat the exact same icon+color on more than 2 items — it looks like a rendering bug

### Common FA Icons

```javascript
const {
  FaServer, FaDocker, FaCogs, FaShieldAlt, FaChartLine,
  FaCloud, FaLock, FaRocket, FaCode, FaDatabase,
  FaNetworkWired, FaCubes, FaCheckCircle, FaExclamationTriangle,
  FaBolt, FaTerminal, FaMicrochip, FaLayerGroup,
} = require("react-icons/fa");
```

## Advanced: Custom Layouts Beyond Helpers

For layouts not covered by the helper library, access the raw `deck.pptx` and `deck.theme` directly. The patterns below are ready-to-use implementations of the most common custom layouts.

### Logo Grid (Technology Stack)

A grid of named technologies with brand logos. Use when a slide lists 4–8 named products/tools. Each cell shows the tool's logo circle, name, and a one-line description. Use `addLogoGridSlide` from the helper library — no boilerplate needed.

**Corporate-match mode (AMD default):** Use plain icon+text rows or bullets instead — card surfaces and shadows violate the no-decorative-shapes rule. Logo grid is rich-mode only.

**Trigger signals (rich mode):** Slide title contains "Stack", "Tools", "Platform", "Services", or "Components" AND content is a list of 4–8 named product names.

**Grid sizing:** `cols = n <= 4 ? n : (n <= 6 ? 3 : 4)`

### addLogoGridSlide(deck, title, items, iconImages, brandColors, slideNum, notes?)

- `items` — Array of `{ name, description }` objects
- `iconImages` — Array of base64 data URIs from `preRenderIcons` (or null for no icon)
- `brandColors` — Array of hex color strings (no `#`) — used for the brand accent bar per card
- `notes` — Optional speaker notes string

**Usage with Simple Icons:**

```javascript
const { SiNomad, SiConsul, SiTerraform, SiDocker, SiTraefikproxy, SiMinio } = require("react-icons/si");

const tools = [
  { name: "Nomad",     description: "Workload orchestration",       icon: SiNomad,        color: "00CA8E" },
  { name: "Consul",    description: "Service discovery & mesh",     icon: SiConsul,       color: "F24C53" },
  { name: "Terraform", description: "Infrastructure as code",       icon: SiTerraform,    color: "844FBA" },
  { name: "Docker",    description: "Container runtime",            icon: SiDocker,       color: "2496ED" },
  { name: "Traefik",   description: "Edge routing & load balancing",icon: SiTraefikproxy, color: "24A1C1" },
  { name: "MinIO",     description: "S3-compatible object storage", icon: SiMinio,        color: "C72E49" },
];

const icons = await preRenderIcons(
  Object.fromEntries(tools.map(t => [t.name, { component: t.icon, color: t.color }]))
);
const iconImages = tools.map(t => icons[t.name]);
const brandColors = tools.map(t => t.color);

addLogoGridSlide(deck, "Platform Stack", tools, iconImages, brandColors, sn++);
```

---

### Brand Badge

When a slide is specifically about a vendor product (e.g., "AMD MI300X Performance"), add a small badge in the top-right corner. Low-effort, high-impact — signals "this slide is about [product]" without changing the content structure.

```javascript
function addBrandBadge(slide, pptx, vendorLogo, productName, theme) {
  const C = theme.colors;
  const badgeW = 1.8;
  const badgeX = RIGHT_EDGE - badgeW;
  const badgeY = 0.2;

  slide.addShape(pptx.ShapeType.rect, {
    x: badgeX, y: badgeY, w: badgeW, h: 0.8,
    fill: { color: C.surface }, rectRadius: 0.05,
  });
  if (vendorLogo) {
    slide.addImage({ data: vendorLogo, x: badgeX + 0.1, y: badgeY + 0.08, w: 0.64, h: 0.64 });
  }
  slide.addText(productName, {
    x: badgeX + 0.82, y: badgeY + 0.15, w: badgeW - 0.92, h: 0.5,
    fontSize: 14, fontFace: theme.fonts.heading, color: C.text_primary, bold: true, valign: "middle",
  });
}
```

**When to use:** Slides about specific vendor hardware (GPUs, CPUs), named cloud services, or branded product lines. Call `addBrandBadge(slide, pptx, logo, "MI300X", theme)` after building the slide with any helper.

**When NOT to use:** Generic concept slides, section dividers, title/closing slides, or slides comparing multiple vendors.

---

For layouts not covered by the helper library (e.g., logo grid, three-column cards, brand badges), access the raw `deck.pptx` and `deck.theme` directly:

```javascript
const deck = createDeck('themes/amd.yaml');
const { pptx, theme, layout } = deck;
const { M, CONTENT_W, CONTENT_Y, CONTENT_H } = layout;
const C = theme.colors;

const slide = pptx.addSlide();
slide.background = { color: C.background };

// Custom layout code here — use the same constants as helpers
slide.addText("Custom content", {
  x: M, y: CONTENT_Y, w: CONTENT_W, h: CONTENT_H,
  fontSize: 18, fontFace: theme.fonts.body,
  color: C.text_body,
});

addFooter(slide, slideNum, theme);
```

This works seamlessly with helper-built slides in the same deck. Use the theme colors and layout constants for consistency.

## Complete Script Example

```javascript
import {
  createDeck, addTitleSlide, addBulletSlide, addImageSlide,
  addImageBulletsSlide, addProcessFlow, addTwoColumn, addCardGrid,
  addStatCallout, addCodeSlide, addIconRowsSlide, addLogoGridSlide,
  addClosingSlide, renderIconSvg, iconToBase64, preRenderIcons, cardShadow,
} from '../lib/pptxgenjs-helpers.mjs';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

async function buildDeck() {
  const deck = createDeck('themes/amd.yaml');
  let sn = 1;

  // Pre-render icons
  const { FaServer, FaCloud, FaLock } = require('react-icons/fa');
  const { SiDocker, SiKubernetes } = require('react-icons/si');
  const icons = await preRenderIcons({
    server: { component: FaServer, color: '00C2DE' },
    cloud: { component: FaCloud, color: '00C2DE' },
    lock: { component: FaLock, color: '00C2DE' },
    docker: { component: SiDocker, color: '2496ED' },
    k8s: { component: SiKubernetes, color: '326CE5' },
  });

  // Title slide
  addTitleSlide(deck, "Infrastructure Overview", "Q1 2026 Review", sn++);

  // Bullet slide
  addBulletSlide(deck, "Key Achievements", [
    "**Container Migration** — moved 85% of workloads to K8s",
    "**Uptime** — achieved 99.97% availability",
    "**Cost Reduction** — 30% infrastructure cost savings",
  ], sn++, "Highlight the cost savings in particular.");

  // Card grid
  addCardGrid(deck, "Platform Components", [
    { title: "Orchestration", body: "Kubernetes for all workloads", iconImg: icons.k8s },
    { title: "Containers", body: "Docker with multi-stage builds", iconImg: icons.docker },
    { title: "Security", body: "Zero-trust network policies", iconImg: icons.lock },
    { title: "Monitoring", body: "Full observability stack", iconImg: icons.cloud },
  ], sn++);

  // Process flow
  addProcessFlow(deck, "Deployment Pipeline", [
    "Code Push\nDeveloper pushes to main",
    "Build\nCI builds container image",
    "Test\nAutomated integration tests",
    "Deploy\nRolling update to production",
  ], sn++);

  // Two-column comparison
  addTwoColumn(deck, "Before vs After", "Legacy", "Current",
    ["Manual deployments", "Single region", "4-hour recovery"],
    ["Automated CI/CD", "Multi-region active-active", "15-minute recovery"],
    sn++
  );

  // Code slide
  addCodeSlide(deck, "Deployment Command", [
    "kubectl apply -f deployment.yaml",
    "kubectl rollout status deploy/app",
    "kubectl get pods -l app=myapp",
  ].join('\n'), sn++);

  // Closing
  addClosingSlide(deck, sn);

  await deck.save('output/infra-overview.pptx');
}

buildDeck().catch(console.error);
```
