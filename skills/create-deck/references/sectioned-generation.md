# Sectioned Deck Generation

Reference for splitting large outlines into sections and generating them independently. Use this when an outline has more than 25 slides.

> **Note:** With helper library imports, single-script generation works well up to ~40 slides. Sectioning primarily benefits outlines with 25+ slides where context diversity (many different layout types, icon sets) would stress the LLM.

## When to Section

| Outline Size | Strategy | Sections |
|---|---|---|
| ≤25 slides | Single script (no sectioning) | 1 |
| 26–40 slides | Sectioned generation | 2–3 |
| 41+ slides | Sectioned generation | 3–5 |

Sectioning keeps each generation call focused (~10–15 slides), preventing context fatigue and improving quality consistency across the deck.

## Parsing Outlines

Use `lib/section_parser.py` to parse and split:

```python
import sys; sys.path.insert(0, 'lib')
from section_parser import parse_sections

outline_text = open('outlines/my-deck.md').read()
result = parse_sections(outline_text)
```

### Return Value

```python
{
    'deck_title': 'AMD SMI MCP Server',
    'subtitle': 'Overview and Architecture',
    'frontmatter': {'audience': 'engineers', ...},
    'sections': [
        {
            'title': 'Introduction',
            'slides': [
                {
                    'title': 'What is AMD SMI?',
                    'bullets': ['Point 1', 'Point 2'],
                    'layout': 'bullet',        # optional
                    'image': 'images/arch.png', # optional
                    'notes': 'Speaker notes',   # optional
                },
                ...
            ],
            'global_offset': 0,  # 0-based index of first slide
        },
        {
            'title': 'Architecture',
            'slides': [...],
            'global_offset': 8,
        },
    ],
    'total_slides': 24,
    'pattern': 'A',  # or 'B'
}
```

### Section Context for Each Generation Call

When generating a section script, pass this context:

| Field | Description | Example |
|-------|-------------|---------|
| `deck_title` | Deck-level title (for title slide in section 1) | "AMD SMI MCP Server" |
| `section.title` | Section heading | "Architecture" |
| `section.slides` | Array of slide objects (title, bullets, layout, image, notes) | See above |
| `section.global_offset` | First slide's global number (0-based) | 8 |
| `total_slides` | Total slides across all sections | 24 |
| `theme` | Path to theme YAML | "themes/amd.yaml" |
| `engine` | "pptxgenjs" or "python-pptx" | "pptxgenjs" |

### Outline Patterns

The parser auto-detects two heading patterns:

**Pattern A: `#` / `##`** (most common)
- `#` = deck title (first one) or section heading (subsequent ones)
- `##` = slide title

**Pattern B: `#` / `##` / `###`**
- `#` = deck title
- `##` = section heading
- `###` = slide title

### Splitting Rules

- **Minimum section size:** 3 slides (smaller sections merge with adjacent)
- **Maximum section size:** 15 slides (larger sections split at midpoint)
- **Empty sections** (section headings with no slide children) merge into the next section
- **Small outlines** (≤25 slides) return a single section — no splitting

## pptxgenjs: Function-Composition Pattern

For pptxgenjs, each section exports an `addSlides(deck)` function instead of producing a standalone PPTX. The merge script calls all section functions on a single deck object.

### Section Script Template

```javascript
// output/sections/my-deck-section-2.mjs
import {
  addBulletSlide, addProcessFlow, addTwoColumn,
  renderIconSvg, iconToBase64,
} from '../../lib/pptxgenjs-helpers.mjs';

/**
 * Section 2: Architecture (slides 9–16)
 */
export async function addSlides(deck) {
  let sn = 9;  // globalSlideOffset + 1

  addBulletSlide(deck, "System Architecture", [
    "**MontySandbox** — secure execution environment",
    "**API Gateway** — rate limiting and auth",
  ], sn++);

  addTwoColumn(deck, "Read vs Write Operations",
    "Read-Only", "Write",
    ["System info queries", "Monitoring data"],
    ["Fan speed control", "Power management"],
    sn++
  );

  // ... more slides ...
}
```

### Merge Script

```javascript
// output/my-deck-merge.mjs
import { createDeck } from '../lib/pptxgenjs-helpers.mjs';

async function mergeDeck() {
  const deck = createDeck('themes/amd.yaml');

  // Import and execute each section in order
  const section1 = await import('./sections/my-deck-section-1.mjs');
  await section1.addSlides(deck);

  const section2 = await import('./sections/my-deck-section-2.mjs');
  await section2.addSlides(deck);

  const section3 = await import('./sections/my-deck-section-3.mjs');
  await section3.addSlides(deck);

  await deck.save('output/my-deck.pptx');
}

mergeDeck().catch(console.error);
```

**Execute:** `NODE_PATH="$(npm root -g)" node output/my-deck-merge.mjs`

**Advantages of function-composition:**
- No PPTX-level merging needed — avoids media reference issues
- Each section has full access to the same deck/theme object
- Slide numbering is handled naturally (each section increments from its offset)
- Individual sections can be re-executed independently by importing into a test deck

## python-pptx: Standalone Scripts + Merge

For python-pptx, each section produces a standalone PPTX file. The files are merged using `lib/merge.py`.

### Section Script Template

```python
# output/sections/my-deck-section-2.py
import sys; sys.path.insert(0, 'lib')
from pptx_helpers import (
    load_template, save_deck, set_placeholder,
    add_bullets, add_two_column_with_header, add_column_divider,
)

prs = load_template('templates/corp.pptx')

# Slide 9 (global_offset=8, so first slide is 9)
slide = prs.slides.add_slide(prs.slide_layouts[3])
set_placeholder(slide, 0, "System Architecture")
add_bullets(slide, 10, [
    "**MontySandbox** — secure execution environment",
    "**API Gateway** — rate limiting and auth",
])

# Slide 10
slide = prs.slides.add_slide(prs.slide_layouts[5])
set_placeholder(slide, 0, "Read vs Write Operations")
add_two_column_with_header(slide, 12, "Read-Only", [
    "System info queries", "Monitoring data",
])
add_two_column_with_header(slide, 13, "Write", [
    "Fan speed control", "Power management",
])
add_column_divider(slide, prs)

# ... more slides ...

save_deck(prs, 'output/sections/my-deck-section-2.pptx')
```

### Merging Section PPTX Files

**CLI:**

```bash
$VENV_PYTHON aippt.py merge \
    output/sections/my-deck-section-1.pptx \
    output/sections/my-deck-section-2.pptx \
    output/sections/my-deck-section-3.pptx \
    -o output/my-deck.pptx
```

**Programmatic:**

```python
import sys; sys.path.insert(0, 'lib')
from merge import merge_decks

result = merge_decks(
    ['output/sections/s1.pptx', 'output/sections/s2.pptx', 'output/sections/s3.pptx'],
    'output/my-deck.pptx'
)
# result = { 'output_path': ..., 'slide_count': 24, 'chunk_counts': [8, 8, 8] }
```

### Merge Behavior

- Uses the first chunk as the base (preserves template, theme, slide masters)
- Copies slides from subsequent chunks using XML-level deep copy
- Renumbers slide footer text boxes (small number text in bottom-left corner)
- All section files must use the same template for reliable merging

## Parallel Section Generation

For 3+ sections, dispatch generation as parallel subagents. Each section is fully independent — no shared state, same theme file.

Use `superpowers:dispatching-parallel-agents` to generate sections concurrently:

```
Agent 1: Generate section 1 (slides 1–8)  → output/sections/deck-section-1.pptx
Agent 2: Generate section 2 (slides 9–16) → output/sections/deck-section-2.pptx
Agent 3: Generate section 3 (slides 17–24) → output/sections/deck-section-3.pptx
```

After all agents complete, run the merge step.

**For pptxgenjs:** Each agent writes a `.mjs` section file. The parent runs the merge script.

**For python-pptx:** Each agent runs its section script to produce a `.pptx` file. The parent merges with `aippt merge`.

## Workflow Summary

```
1. Read outline → count slides
2. If ≤25: generate as single script (no sectioning)
3. If >25: parse_sections() → split into N sections
4. For each section:
   a. pptxgenjs: write .mjs with export async function addSlides(deck)
   b. python-pptx: write .py that produces standalone .pptx
5. Merge:
   a. pptxgenjs: write merge.mjs that imports all sections → single deck
   b. python-pptx: run `aippt merge *.pptx -o final.pptx`
6. Verify final deck exists and has correct slide count
```
