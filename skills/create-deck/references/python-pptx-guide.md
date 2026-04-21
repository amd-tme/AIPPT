# python-pptx Template Engine Guide

Reference for generating PowerPoint decks using python-pptx with the helper library and an existing corporate template. Claude reads this when creating template-based deck scripts.

## Template Analysis

### Enumerating Layouts and Placeholders

Run this script to discover what's available in any template:

```python
from pptx import Presentation
from pptx.enum.shapes import PP_PLACEHOLDER_TYPE as PT

prs = Presentation('templates/corp.pptx')
for i, layout in enumerate(prs.slide_layouts):
    print(f"Layout {i}: {layout.name}")
    for ph in layout.placeholders:
        print(f"  idx={ph.placeholder_format.idx}, "
              f"type={ph.placeholder_format.type}, "
              f"name={ph.name}")
```

### Placeholder Types

| Type Value | Constant | Meaning |
|-----------|----------|---------|
| 1 | TITLE | Slide title |
| 2 | BODY | Body text area |
| 7 | OBJECT | Generic content (AMD template uses this instead of BODY) |
| 18 | PICTURE | Image placeholder |

**Important:** The AMD corporate template uses OBJECT (type 7) placeholders for content, not BODY (type 2). When searching for content placeholders, match by `idx > 0` rather than by type.

### Two-Column Placeholders

Two-column layouts use placeholder indices 12 (left) and 13 (right).

## Key Layout Indices (corp.pptx)

| Index | Name | Placeholders |
|-------|------|-------------|
| 0 | Title Slide - No Image | idx 0 = title, idx 12 = subtitle |
| 3 | Title and Content | idx 0 = title, idx 10 = body |
| 5 | Two Content | idx 0 = title, idx 12 = left, idx 13 = right |
| 7 | Title Only | idx 0 = title |
| 17 | Three Content with Headings | idx 0 = title, idx 10/13/16 = headings, idx 12/15/18 = content |
| 26 | Divider Slide | idx 0 = title, idx 14 = subtitle |
| 28 | Developer Code Layout | idx 0 = title, idx 10 = code body |
| 30 | Closing Logo Slide | (logo only, no text placeholders) |

## Helper Library API

Import the helper library in all scripts:

```python
import sys; sys.path.insert(0, 'lib')
from pptx_helpers import (
    load_template, save_deck, get_placeholder, set_placeholder,
    suppress_bullet, add_bullets, add_bullets_with_sub,
    add_numbered_bullets, add_two_column_with_header,
    add_column_divider, set_notes,
)
```

### load_template(template_path)

Load a PPTX template and remove all sample slides.

```python
prs = load_template('templates/corp.pptx')
# Returns a Presentation ready for adding new slides
# Sample slides are already removed
```

### save_deck(prs, output_path)

Save the presentation and print file size.

```python
save_deck(prs, 'output/deck.pptx')
# Prints: "Deck saved: output/deck.pptx (2.1 MB, 15 slides)"
```

### get_placeholder(slide, idx)

Get a placeholder by its format index. Returns the placeholder or None.

### set_placeholder(slide, idx, text)

Find placeholder by idx, clear it, and set text. Returns the placeholder or None.

```python
slide = prs.slides.add_slide(prs.slide_layouts[3])
set_placeholder(slide, 0, "Slide Title")
```

### add_bullets(slide, idx, items)

Add bulleted items to a placeholder with bold lead-in detection.

**Item formats:**
- `str` — plain text, rendered at level 0
- `(text, level)` tuple — text at specified indent level (0 = top, 1 = indented)
- Bold lead-ins auto-detected: `"**Bold** — rest"` renders bold prefix with em dash

```python
add_bullets(slide, 10, [
    "**Container Runtime** — Docker 24.0 with multi-stage builds",
    "**Orchestration** — Kubernetes 1.28 with custom operators",
    "Standard bullet text",
    ("Sub-bullet at indent level 1", 1),
])
```

### add_bullets_with_sub(slide, idx, items)

Add bulleted items with sub-bullet support.

**Item formats:**
- `str` — plain bullet
- `dict` with `'text'` and optional `'subs'` list — parent bullet with sub-bullets

```python
add_bullets_with_sub(slide, 10, [
    "Simple bullet",
    {"text": "**Parent Item** — with children", "subs": [
        "Sub-item 1",
        "Sub-item 2",
    ]},
])
```

### add_numbered_bullets(slide, idx, items)

Add numbered items with bullet suppression and bold handling.

**Item formats:**
- `str` — numbered item (e.g., "1. text")
- `dict` with `'text'` and optional `'subs'` — numbered item with code sub-items (Consolas 14pt)

```python
add_numbered_bullets(slide, 10, [
    "**Install** — set up the base environment",
    {"text": "**Configure** — apply settings", "subs": [
        "sudo systemctl enable myservice",
        "sudo systemctl start myservice",
    ]},
    "Verify the installation",
])
```

### add_two_column_with_header(slide, idx, header, items)

Add a column header + bullets to a two-column placeholder (idx 12 or 13).

- Header: teal accent color (`00C2DE`), centered, bold, 20pt, bullet suppressed
- Items: same format as `add_bullets_with_sub()`

```python
slide = prs.slides.add_slide(prs.slide_layouts[5])
set_placeholder(slide, 0, "Comparison Title")
add_two_column_with_header(slide, 12, "Before", [
    "Manual deployments",
    "Single region",
])
add_two_column_with_header(slide, 13, "After", [
    "Automated CI/CD",
    "Multi-region active-active",
])
```

### add_column_divider(slide, prs)

Add a vertical divider line between two-column placeholders. Uses surface gray (`636466`).

```python
add_column_divider(slide, prs)
```

### suppress_bullet(paragraph)

Remove bullet dot from a paragraph (for headers, numbered items). Required because the corp.pptx template applies bullet formatting at the layout level.

```python
# Usually called internally by add_numbered_bullets and add_two_column_with_header
# Direct use for custom formatting:
p = tf.paragraphs[0]
p.text = "Header Text"
suppress_bullet(p)
```

### set_notes(slide, text)

Set speaker notes on a slide.

```python
set_notes(slide, "Key talking point: emphasize the cost savings.")
```

## Common Slide Patterns

### Title Slide (Layout 0)

```python
slide = prs.slides.add_slide(prs.slide_layouts[0])
set_placeholder(slide, 0, "Presentation Title")
set_placeholder(slide, 12, "Subtitle or author info")
```

### Content Slide (Layout 3)

```python
slide = prs.slides.add_slide(prs.slide_layouts[3])
set_placeholder(slide, 0, "Slide Title")
add_bullets(slide, 10, [
    "**First Point** — description here",
    "**Second Point** — another description",
    "Third point without bold lead-in",
])
```

### Two-Column Slide (Layout 5)

```python
slide = prs.slides.add_slide(prs.slide_layouts[5])
set_placeholder(slide, 0, "Comparison Title")
add_two_column_with_header(slide, 12, "Category A", [
    "Left item 1", "Left item 2",
])
add_two_column_with_header(slide, 13, "Category B", [
    "Right item 1", "Right item 2",
])
add_column_divider(slide, prs)
```

### Numbered List Slide (Layout 3)

```python
slide = prs.slides.add_slide(prs.slide_layouts[3])
set_placeholder(slide, 0, "Process Steps")
add_numbered_bullets(slide, 10, [
    "**Prepare** — set up the environment",
    "**Deploy** — push to production",
    "**Verify** — run smoke tests",
])
```

### Image + Bullets Side-by-Side (Layout 3)

```python
from pptx.util import Inches

slide = prs.slides.add_slide(prs.slide_layouts[3])
set_placeholder(slide, 0, "Architecture")

# Reposition content placeholder to right half
ph = get_placeholder(slide, 10)
if ph:
    ph.left = Inches(6.5)
    ph.top = Inches(1.8)
    ph.width = Inches(5.8)
    ph.height = Inches(5.0)

# Add image on left
slide.shapes.add_picture("images/diagram.png",
    left=Inches(0.5), top=Inches(2.0), width=Inches(5.5))

add_bullets(slide, 10, ["Key observation 1", "Key observation 2"])
```

### Diagram / Full Image Slide (Layout 7)

```python
from PIL import Image as PILImage
from pptx.util import Inches

slide = prs.slides.add_slide(prs.slide_layouts[7])
set_placeholder(slide, 0, "Architecture Overview")

# Center image
img = PILImage.open("images/architecture.png")
aspect = img.width / img.height
width = min(Inches(7.0), prs.slide_width - Inches(2))
height = int(width / aspect)
left = (prs.slide_width - width) // 2
top = Inches(1.5) + (Inches(5.3) - height) // 2
slide.shapes.add_picture("images/architecture.png", left, top, width, height)

set_notes(slide, "Diagram showing the full system architecture.")
```

### Section Divider (Layout 26)

```python
slide = prs.slides.add_slide(prs.slide_layouts[26])
set_placeholder(slide, 0, "Section Name")
set_placeholder(slide, 14, "Optional subtitle")
```

### Code Slide (Layout 28)

```python
from pptx.util import Pt

slide = prs.slides.add_slide(prs.slide_layouts[28])
set_placeholder(slide, 0, "Deployment Commands")
ph = get_placeholder(slide, 10)
if ph:
    tf = ph.text_frame
    tf.clear()
    for i, cmd in enumerate(["kubectl apply -f deploy.yaml",
                              "kubectl rollout status deploy/app"]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        run = p.add_run()
        run.text = cmd
        run.font.name = "Consolas"
        run.font.size = Pt(14)
```

### Closing Slide (Layout 30)

```python
slide = prs.slides.add_slide(prs.slide_layouts[30])
# Logo-only slide, no text to set
```

## Layout Selection Strategy

| Content Type | Layout Index | Layout Name | Notes |
|-------------|-------------|-------------|-------|
| First `#` heading | 0 | Title Slide | |
| `#` heading, no children | 26 | Divider | |
| Standard bullets | 3 | Title and Content | Use `add_bullets()` |
| `LAYOUT: numbered` or sequential steps | 3 | Title and Content | Use `add_numbered_bullets()`. If >6 items, consider splitting. 8+ is a readability smell. |
| `LAYOUT: numbered` with CLI commands | 28 | Developer Code | Auto-split: concepts → Layout 3, commands → Layout 28 |
| `LAYOUT: two_column` or `|||` | 5 | Two Content | Use `add_two_column_with_header()` + `add_column_divider()` |
| `IMAGE:` with no bullets | 7 | Title Only | Center image; content goes to speaker notes |
| `IMAGE:` with bullets | 3 | Title and Content | Reposition placeholder to right half |
| `LAYOUT: diagram` without `IMAGE:` | 3 | Title and Content | Fallback — keep bullets in body, suggest Excalidraw follow-up |
| Code blocks / CLI | 28 | Developer Code | Use Consolas font (Pt(14)) |
| 3 parallel items with headings | 17 | Three Content | |
| Last slide / thank you | 30 | Closing Logo | |

## Venv Python Detection

Always use the virtualenv Python:

```bash
if [ -f venv/bin/python ]; then
    VENV_PYTHON=venv/bin/python
elif [ -f venv/Scripts/python.exe ]; then
    VENV_PYTHON=venv/Scripts/python.exe
fi
$VENV_PYTHON output/script.py
```

## Complete Script Example

```python
import sys; sys.path.insert(0, 'lib')
from pptx_helpers import (
    load_template, save_deck, set_placeholder, get_placeholder,
    add_bullets, add_numbered_bullets, add_two_column_with_header,
    add_column_divider, set_notes,
)

prs = load_template('templates/corp.pptx')

# Title slide
slide = prs.slides.add_slide(prs.slide_layouts[0])
set_placeholder(slide, 0, "Infrastructure Overview")
set_placeholder(slide, 12, "Q1 2026 Review")

# Bullet slide
slide = prs.slides.add_slide(prs.slide_layouts[3])
set_placeholder(slide, 0, "Key Achievements")
add_bullets(slide, 10, [
    "**Container Migration** — moved 85% of workloads to K8s",
    "**Uptime** — achieved 99.97% availability",
    "**Cost Reduction** — 30% infrastructure cost savings",
])
set_notes(slide, "Highlight the cost savings in particular.")

# Two-column comparison
slide = prs.slides.add_slide(prs.slide_layouts[5])
set_placeholder(slide, 0, "Before vs After")
add_two_column_with_header(slide, 12, "Legacy", [
    "Manual deployments",
    "Single region",
    "4-hour recovery",
])
add_two_column_with_header(slide, 13, "Current", [
    "Automated CI/CD",
    "Multi-region active-active",
    "15-minute recovery",
])
add_column_divider(slide, prs)

# Numbered process steps
slide = prs.slides.add_slide(prs.slide_layouts[3])
set_placeholder(slide, 0, "Deployment Pipeline")
add_numbered_bullets(slide, 10, [
    "**Prepare** — set up environment and dependencies",
    "**Build** — compile and package application",
    "**Test** — run automated integration suite",
    "**Deploy** — rolling update to production",
])

# Closing
slide = prs.slides.add_slide(prs.slide_layouts[30])

save_deck(prs, 'output/infra-overview.pptx')
```

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| "Click to edit" text remains | Didn't clear text frame | Use `set_placeholder()` or call `tf.clear()` |
| Extra sample slides | Didn't remove template samples | Use `load_template()` instead of `Presentation()` |
| Wrong placeholder filled | Matched by position not idx | Use `get_placeholder(slide, idx)` |
| Text not visible | Wrong placeholder type | AMD uses OBJECT (7), check idx manually |
| Layout not found | Wrong index | Run enumeration script on template |
| Bullet dots on headers | Template forces bullets | Call `suppress_bullet()` — auto-handled by `add_two_column_with_header()` and `add_numbered_bullets()` |
