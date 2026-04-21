# Theme YAML Schema Reference

Theme configs define the visual identity applied to generated decks. They live in `themes/` as `.yaml` files.

## Full Schema

```yaml
name: <string>           # Display name (e.g. "AMD Corporate")
description: <string>    # Short description of the theme

colors:
  background: <hex6>     # Primary slide background
  background_alt: <hex6> # Alternate background (section dividers, cards)
  surface: <hex6>        # Card/panel surface color
  text_primary: <hex6>   # Headings, titles
  text_secondary: <hex6> # Subtitles, captions, muted text
  text_body: <hex6>      # Body text, bullets
  accent: <hex6>         # Primary accent (bars, highlights, icons)
  accent_alt: <hex6>     # Secondary accent (variety, alternating elements)
  warning: <hex6>        # Warnings, alerts, callouts

fonts:
  heading: <string>      # Font for titles and headings
  body: <string>         # Font for body text and bullets
  mono: <string>         # Font for code blocks

logo:
  path: <string>         # Path relative to project root (empty string = no logo)
  position: <position>   # Where to place the logo on each slide
  width_inches: <float>  # Logo width in inches (0 = no logo)
  height_inches: <float> # Logo height (optional, estimated from width if absent)
  x_inches: <float>      # Exact x position override (optional)
  y_inches: <float>      # Exact y position override (optional)

slide:
  layout: <layout>       # pptxgenjs slide layout constant
  margin_inches: <float> # Content margin from slide edges

footer:
  show: <bool>           # Whether to show footer elements
  text: <string>         # Custom footer text (empty = none)
  show_slide_numbers: <bool>  # Show slide numbers in footer
```

## Field Details

### Colors (`colors.*`)

All color values are **6-character hex strings without the `#` prefix**.

| Field | Purpose | Example |
|-------|---------|---------|
| `background` | Primary slide background | `"000000"` (black) |
| `background_alt` | Alternate bg for variety | `"1E293B"` (dark slate) |
| `surface` | Card/panel backgrounds | `"334155"` (dark gray) |
| `text_primary` | Headings, titles | `"FFFFFF"` (white) |
| `text_secondary` | Subtitles, muted text | `"94A3B8"` (light gray) |
| `text_body` | Body text, bullets | `"E2E8F0"` (off-white) |
| `accent` | Primary accent color | `"00B4D8"` (teal) |
| `accent_alt` | Secondary accent | `"06D6A0"` (green) |
| `warning` | Warnings, callouts | `"E94560"` (red) |

**CRITICAL:** Never use `#` prefix. pptxgenjs will corrupt the file if hex colors include `#`. Never use 8-character hex (with opacity) — this also causes corruption.

### Fonts (`fonts.*`)

Font names must match fonts available on the target system. Safe defaults:

| Field | Purpose | Safe Choices |
|-------|---------|-------------|
| `heading` | Titles, section headers | Trebuchet MS, Arial, Calibri |
| `body` | Bullets, body text | Calibri, Arial, Segoe UI |
| `mono` | Code blocks | Consolas, Courier New, monospace |

### Logo (`logo.*`)

| Field | Type | Values |
|-------|------|--------|
| `path` | string | Relative to project root. Empty string `""` = no logo |
| `position` | string | `"bottom-right"`, `"bottom-left"`, `"top-right"`, `"top-left"` |
| `width_inches` | float | Logo width. `0` = no logo. Typical: `1.0` - `1.5` |

**pptxgenjs logo placement mapping:**

| Position | x | y |
|----------|---|---|
| `bottom-right` | `slideWidth - margin - width` | `slideHeight - margin - height` |
| `bottom-left` | `margin` | `slideHeight - margin - height` |
| `top-right` | `slideWidth - margin - width` | `margin` |
| `top-left` | `margin` | `margin` |

### Slide (`slide.*`)

| Field | Type | Values |
|-------|------|--------|
| `layout` | string | pptxgenjs layout constant (see below) |
| `margin_inches` | float | Content inset from edges. Typical: `0.4` - `0.6` |

**Layout constants:**

| Constant | Width | Height | Notes |
|----------|-------|--------|-------|
| `LAYOUT_WIDE` | 13.33" | 7.5" | **Use this — all guide coordinates match** |
| `LAYOUT_16x9` | 10.0" | 5.625" | Do NOT use — coordinates will clip |
| `LAYOUT_16x10` | 10.0" | 6.25" | Not recommended |
| `LAYOUT_4x3` | 10.0" | 7.5" | Classic 4:3 only |

**IMPORTANT:** Despite both being 16:9 aspect ratio, `LAYOUT_WIDE` and `LAYOUT_16x9` have different EMU sizes. All coordinates in the pptxgenjs guide are designed for `LAYOUT_WIDE` (13.33" × 7.5"). Using `LAYOUT_16x9` will cause content to clip off the right and bottom edges.

### Footer (`footer.*`)

| Field | Type | Purpose |
|-------|------|---------|
| `show` | bool | `true` = render footer bar on each slide |
| `text` | string | Custom text in footer. Empty = no text |
| `show_slide_numbers` | bool | `true` = show "N / TOTAL" in footer |

## Creating a New Theme

1. Copy an existing theme YAML as a starting point
2. Update `name` and `description`
3. Set `colors` to match the brand's color palette
4. Set `fonts` to the brand's typography
5. Place logo image in `themes/assets/` and update `logo.path`
6. Save as `themes/<brand-name>.yaml`

### Example: Acme Corp Theme

```yaml
name: Acme Corp
description: Blue and white corporate theme

colors:
  background: "FFFFFF"
  background_alt: "F1F5F9"
  surface: "E2E8F0"
  text_primary: "0F172A"
  text_secondary: "64748B"
  text_body: "334155"
  accent: "2563EB"
  accent_alt: "7C3AED"
  warning: "DC2626"

fonts:
  heading: "Arial"
  body: "Calibri"
  mono: "Consolas"

logo:
  path: "themes/assets/acme-logo.png"
  position: "top-left"
  width_inches: 1.5

slide:
  layout: "LAYOUT_WIDE"    # 13.33" × 7.5" — always use LAYOUT_WIDE
  margin_inches: 0.5

footer:
  show: true
  text: "Acme Corp Confidential"
  show_slide_numbers: true
```

## Usage in Scripts

### pptxgenjs

```javascript
const yaml = require('js-yaml');
const fs = require('fs');
const theme = yaml.load(fs.readFileSync('themes/amd.yaml', 'utf8'));

// Apply colors
const C = theme.colors;
slide.addShape(pptx.ShapeType.rect, {
  fill: { color: C.background },
});

// Apply fonts
slide.addText("Title", {
  fontFace: theme.fonts.heading,
  color: C.text_primary,
});

// Apply logo
if (theme.logo.path) {
  slide.addImage({
    path: theme.logo.path,
    w: theme.logo.width_inches,
    // calculate x, y from theme.logo.position
  });
}
```

### python-pptx

Theme colors are less directly applicable in python-pptx (the template carries its own theme). Use theme YAML primarily for reference when the template doesn't cover a setting.
