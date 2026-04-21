# PRD: Slide Helper Libraries

**Date:** 2026-03-11
**Author:** Matt Elliott
**Status:** Draft

---

## Summary

Extract the repeated boilerplate from every generated deck script into importable helper libraries — `lib/pptxgenjs-helpers.mjs` for the JavaScript/pptxgenjs engine and `lib/pptx_helpers.py` for the python-pptx engine. Instead of generating 500–1200-line self-contained scripts, the LLM produces ~20–80-line scripts that import pre-built layout functions and call them with slide-specific data. This cuts token usage by 60–80%, reduces generation errors, and makes visual fixes automatically propagate to all future decks.

## Motivation

- **Massive boilerplate duplication.** Every generated script re-implements the same ~120 lines of infrastructure: theme loading, safe-area constants, shadow factories, icon pipelines, footer helpers, bullet formatting, placeholder manipulation, bold lead-in parsing. Across 14 existing scripts in `output/`, that's ~1,700 lines of near-identical code.
- **Token waste.** The LLM must hold 1,300+ lines of pptxgenjs API reference in context to regenerate these patterns each time. With helpers, the reference docs shrink to a compact API surface (~200 lines), freeing context for the actual slide content.
- **Bug propagation.** When a visual fix is discovered (e.g., `valign: "top"` instead of `"middle"` for bullets, or the two-row process flow layout), it must be manually applied to the skill's reference docs and re-learned by the LLM. With helpers, fixes are made once in the library and every future deck benefits automatically.
- **Consistency.** Different decks currently implement slight variations of the same patterns (different function names, argument orders, formatting approaches). A shared library enforces a single canonical implementation.
- **Enables sectioned generation.** The companion PRD (sectioned generation) depends on tiny per-section scripts. Without helpers, each section would still be 200+ lines; with helpers, sections shrink to ~15 lines of pure data calls.

## Requirements

### Must Have

- [ ] `lib/pptxgenjs-helpers.mjs` — ES module exporting all layout builder functions, theme loader, icon pipeline, footer helper, and safe-area constants
- [ ] `lib/pptx_helpers.py` — Python module exporting placeholder helpers, bullet formatting, bold lead-in parsing, suppress_bullet, column divider, two-column with header, and template management
- [ ] Theme loader function that reads a theme YAML file and returns a structured config object (colors, fonts, logo, slide dimensions, footer settings)
- [ ] Both libraries must be importable from generated scripts without modifying `NODE_PATH` or `sys.path` (use relative imports from `output/` → `lib/`)
- [ ] Slide builder functions must accept the same data structures currently used in generated scripts (no breaking change to the LLM's mental model)
- [ ] Updated skill reference docs (`references/pptxgenjs-guide.md`, `references/python-pptx-guide.md`) that document the helper API instead of raw library internals
- [ ] At least one existing generated script per engine rewritten to use the helpers as a validation/example

### Nice to Have

- [ ] `lib/merge.py` — PPTX merge utility (copy slides from multiple PPTX files into one) to support the sectioned generation PRD
- [ ] CLI command (`aippt.py merge chunk1.pptx chunk2.pptx -o final.pptx`) for manual merging
- [ ] Theme validation function that checks YAML structure and reports missing/invalid fields
- [ ] Unit tests for helper functions (bullet formatting, lead-in parsing, theme loading)

### Out of Scope

- Changing the pptxgenjs or python-pptx libraries themselves
- Modifying the existing `aippt/` package modules (cli.py, layouts.py, etc.) — the helpers are for the skill's generated scripts, not the core pipeline
- Automated visual regression testing (that's a separate concern)
- Migrating all 14 existing scripts to use helpers (do one per engine as proof; rest can be migrated organically)

---

## Design

### Approach

Analyze the 14 existing generated scripts in `output/` to identify the canonical implementation of each pattern. Extract those patterns into two library files. Update the skill's reference docs to teach the LLM the helper API. The libraries live in `lib/` at the project root (sibling to `output/`, `themes/`, `templates/`).

### pptxgenjs Helper Library (`lib/pptxgenjs-helpers.mjs`)

**Exports:**

```javascript
// Theme & config
export function loadTheme(yamlPath)        // → { colors, fonts, logo, slide, footer }
export const SW, SH                        // Safe-area constants (always 13.33, 7.5)
export function computeLayout(theme)       // → { M, CONTENT_W, CONTENT_Y, FOOTER_Y, CONTENT_H, RIGHT_EDGE }

// Infrastructure
export function cardShadow()               // Fresh shadow object factory
export function renderIconSvg(Icon, size, color) // React icon → SVG string
export async function iconToBase64(svg, size)    // SVG → base64 PNG data URI
export async function preRenderIcons(iconMap)    // { name: { component, color } } → { name: base64 }

// Footer
export function addFooter(slide, slideNum, theme, opts)

// Slide builders — each returns the slide object
export function addTitleSlide(pptx, theme, layout, title, subtitle, slideNum)
export function addBulletSlide(pptx, theme, layout, title, bullets, slideNum)
export function addIconRowsSlide(pptx, theme, layout, title, items, iconImages, slideNum)
export function addProcessFlow(pptx, theme, layout, title, steps, slideNum)
export function addTwoColumn(pptx, theme, layout, title, leftHeader, rightHeader, leftItems, rightItems, slideNum)
export function addCardGrid(pptx, theme, layout, title, cards, slideNum)
export function addStatCallout(pptx, theme, layout, title, stats, slideNum)
export function addCodeSlide(pptx, theme, layout, title, code, slideNum)
export function addClosingSlide(pptx, theme, layout, slideNum)

// Deck lifecycle
export function createDeck(themePath)       // → { pptx, theme, layout, save(path) }
```

**How generated scripts change:**

Before (559 lines):
```javascript
const pptxgen = require("pptxgenjs");
const fs = require("fs");
// ... 70 lines of boilerplate ...
// ... 330 lines of slide builder functions ...
async function buildDeck() {
  const pptx = new pptxgen();
  pptx.layout = "LAYOUT_WIDE";
  // ... 150 lines of slide calls with inline data ...
}
buildDeck().catch(console.error);
```

After (~60 lines):
```javascript
import { createDeck, addTitleSlide, addBulletSlide, addProcessFlow,
         addTwoColumn, addIconRowsSlide, addClosingSlide,
         preRenderIcons } from '../lib/pptxgenjs-helpers.mjs';

const { FaExclamationTriangle, FaSearch } = await import("react-icons/fa");

async function buildDeck() {
  const deck = await createDeck('themes/amd.yaml');
  const icons = await preRenderIcons({
    bloat: { component: FaExclamationTriangle, color: "FFFFFF" },
    search: { component: FaSearch, color: "FFFFFF" },
  });

  let sn = 1;
  addTitleSlide(deck, "AMD SMI MCP Server", "GPU Monitoring via MCP", sn++);
  addBulletSlide(deck, "Overview", [
    "**MCP server** — exposes 70 AMD GPU monitoring tools via FastMCP",
    "**Wraps amdsmi** — C library Python bindings for AMD GPUs",
  ], sn++);
  addIconRowsSlide(deck, "Problems", [
    { label: "Context bloat", desc: "70 tool schemas consume thousands of tokens" },
  ], [icons.bloat], sn++);
  addClosingSlide(deck, sn++);

  await deck.save('output/mcp-amdsmi-overview.pptx');
}

buildDeck().catch(console.error);
```

### python-pptx Helper Library (`lib/pptx_helpers.py`)

**Exports:**

```python
# Template management
def load_template(template_path)           # → prs (with sample slides removed)
def save_deck(prs, output_path)            # Save + print size

# Placeholder helpers
def get_placeholder(slide, idx)
def set_placeholder(slide, idx, text)

# Bullet formatting
def suppress_bullet(paragraph)
def add_bullets(slide, idx, items)                    # items: list[str | tuple[str, int]]
def add_bullets_with_sub(slide, idx, items)           # items: list[str | dict]
def add_numbered_bullets(slide, idx, items)           # items: list[str | dict]

# Two-column helpers
def add_two_column_with_header(slide, idx, header, items)
def add_column_divider(slide, prs)

# Speaker notes
def set_notes(slide, text)
```

**How generated scripts change:**

Before (465 lines):
```python
from pptx import Presentation
# ... 130 lines of helper function definitions ...
prs = Presentation('templates/corp.pptx')
# ... 15 lines of sample slide removal ...
# ... 300 lines of slide creation ...
```

After (~80 lines):
```python
import sys; sys.path.insert(0, 'lib')
from pptx_helpers import (load_template, save_deck, set_placeholder,
                           add_bullets, add_numbered_bullets, set_notes,
                           add_two_column_with_header, add_column_divider)

prs = load_template('templates/corp.pptx')

# Slide 1: Title
slide = prs.slides.add_slide(prs.slide_layouts[0])
set_placeholder(slide, 0, "Enterprise AI Suite")
set_placeholder(slide, 12, "Matt Elliott\nTechnical Marketing Engineer")

# Slide 2: Agenda
slide = prs.slides.add_slide(prs.slide_layouts[3])
set_placeholder(slide, 0, "Agenda")
add_bullets(slide, 10, [
    "What is the Enterprise AI Suite?",
    "AMD Resource Manager",
    "AMD AI Workbench",
])

# ... remaining slides (pure data, no boilerplate) ...

save_deck(prs, 'output/Q126-enterprise-ai.pptx')
```

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `lib/pptxgenjs-helpers.mjs` | New | JavaScript helper library for pptxgenjs slide generation |
| `lib/pptx_helpers.py` | New | Python helper library for python-pptx slide generation |
| `.claude/skills/create-deck/references/pptxgenjs-guide.md` | Modified | Replace raw API reference with helper API docs + examples |
| `.claude/skills/create-deck/references/python-pptx-guide.md` | Modified | Replace raw helper definitions with import-based API docs |
| `.claude/skills/create-deck/SKILL.md` | Modified | Update generation instructions to use `import` pattern |

### Data Model Changes

No data model changes.

---

## CLI Changes

### New Commands (Nice to Have)

```
aippt.py merge chunk1.pptx chunk2.pptx [...] -o output.pptx
```

Merges multiple PPTX files into a single deck. Copies slides in order, preserves layouts and formatting. Optionally renumbers slide footers.

| Option | Default | Description |
|--------|---------|-------------|
| `-o`, `--output` | (required) | Output file path |
| `--renumber` | `true` | Fix slide number text boxes in footers |

### Example Usage

```bash
# Merge three section chunks
python aippt.py merge output/section1.pptx output/section2.pptx output/section3.pptx -o output/final.pptx
```

If the merge command is deferred, it moves to the sectioned generation PRD.

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_pptx_helpers.py` | `TestBulletFormatting`, `TestLeadInParsing`, `TestSuppressBullet`, `TestTemplateLoading` | `lib/pptx_helpers.py` — all exported functions |
| `tests/test_pptxgenjs_helpers.js` | Theme loading, safe-area math, shadow factory | `lib/pptxgenjs-helpers.mjs` — pure functions (no PPTX generation) |

### Integration Tests

Rewrite one existing generated script per engine to use helpers, then verify the output PPTX:
- Opens without errors in LibreOffice/PowerPoint
- Has the expected number of slides
- Title text matches expectations (spot check)

### Manual Testing

1. Run rewritten JS script — `NODE_PATH="$(npm root -g)" node output/example-helpers.mjs` — verify PPTX opens and looks identical to the original
2. Run rewritten Python script — `$VENV_PYTHON output/example-helpers.py` — verify PPTX opens and looks identical to the original
3. Generate a new deck using `/create-deck` with updated skill docs — verify LLM produces import-based script that executes successfully
4. Visually compare a deck generated with helpers vs. the same outline generated without (should be visually identical)

---

## Changelog Entry

```markdown
### Added
- `lib/pptxgenjs-helpers.mjs` — reusable slide builder library for pptxgenjs engine
- `lib/pptx_helpers.py` — reusable helper library for python-pptx engine
- Updated create-deck skill to generate compact scripts using helper imports

### Changed
- create-deck skill reference docs now document the helper API instead of raw library internals
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Create `lib/pptx_helpers.py` — extract helpers from existing python-pptx scripts | `lib/pptx_helpers.py` | -- |
| 2 | Create `lib/pptxgenjs-helpers.mjs` — extract helpers from existing pptxgenjs scripts | `lib/pptxgenjs-helpers.mjs` | -- |
| 3 | Add theme loader to JS helpers (read YAML, return config object) | `lib/pptxgenjs-helpers.mjs` | 2 |
| 4 | Rewrite one python-pptx script to use helpers (validation) | `output/Q126-enterprise-ai-helpers.py` | 1 |
| 5 | Rewrite one pptxgenjs script to use helpers (validation) | `output/mcp-amdsmi-helpers.mjs` | 2, 3 |
| 6 | Update `references/python-pptx-guide.md` with helper API | `.claude/skills/create-deck/references/python-pptx-guide.md` | 1, 4 |
| 7 | Update `references/pptxgenjs-guide.md` with helper API | `.claude/skills/create-deck/references/pptxgenjs-guide.md` | 2, 3, 5 |
| 8 | Update `SKILL.md` generation instructions for import pattern | `.claude/skills/create-deck/SKILL.md` | 6, 7 |
| 9 | Add unit tests for `lib/pptx_helpers.py` | `tests/test_pptx_helpers.py` | 1 |
| 10 | Add unit tests for JS helpers (theme loading, safe-area math) | `tests/test_pptxgenjs_helpers.mjs` | 2, 3 |
| 11 | End-to-end test: generate a new deck via `/create-deck` and verify execution | -- | 8 |

---

## Risks & Open Questions

- **Risk:** LLM may still try to inline helper code instead of importing it — mitigation: strong examples in reference docs, explicit "NEVER redefine these functions" instruction in SKILL.md
- **Risk:** Helper function signatures may need to evolve as new layout types are added — mitigation: use options objects (`opts = {}`) for extensibility, follow semver-like discipline
- **Question:** Should `lib/` helpers be published as an npm/pip package, or stay as local project files? — Recommendation: start local, extract later if reuse emerges
- **Question:** ES module (`.mjs`) vs CommonJS (`.cjs`) for the JS helpers — Recommendation: `.mjs` with `import` syntax, since generated scripts can use dynamic `import()` for react-icons. Fall back to `.cjs` only if NODE_PATH resolution breaks with ESM
- **Question:** Should the theme YAML be loaded at runtime by the helpers, or should the LLM still inline theme constants? — Recommendation: runtime loading (the whole point is less generated code), with a `loadTheme()` function

---

## References

- Existing generated scripts: `output/*.js`, `output/*.py`
- Current skill reference docs: `.claude/skills/create-deck/references/`
- Theme files: `themes/amd.yaml`, `themes/default.yaml`
- Companion PRD: `docs/plans/2026-03-11-sectioned-deck-generation.md`
