# PRD: Sectioned Deck Generation

**Date:** 2026-03-11
**Author:** Matt Elliott
**Status:** Draft

---

## Summary

Enable large presentation outlines (20+ slides) to be generated in independent sections, each with its own LLM call and script execution, then merged into a single PPTX file. This keeps per-section context usage small (~250 lines vs. ~3,000+), enables parallel generation via subagents, and prevents quality degradation on long decks. Sections are defined by `##` headings in the outline's markdown structure.

## Motivation

- **Context window pressure.** A 30-slide outline (~1,000 lines like `ai-techjam-vienna.md`) plus the skill's reference docs (~1,300 lines for pptxgenjs) plus the generated script (~1,200 lines) approaches 100K+ tokens. As context grows, the LLM makes more errors: wrong colors, inconsistent spacing, forgotten patterns.
- **Quality degradation on long decks.** Slides generated late in a large script tend to have simpler layouts, missing features, and more bugs. The LLM "fatigues" as it generates more code in a single pass.
- **Speed.** A 30-slide deck takes 3–5 minutes to generate in a single pass. With sectioned generation and parallel subagents, each 8-slide section takes ~1 minute, and three sections run concurrently. Wall-clock time drops to ~2 minutes.
- **Error isolation.** If one section has a generation error, only that section needs regeneration — not the entire 30-slide deck.
- **Existing precedent.** The `outlines/ai-techjam-vienna.md` outline already uses `## Section` headings to group slides. The outline format naturally maps to sections. The existing `quarterly-review-sections.js` script name suggests this pattern was already being considered.

## Requirements

### Must Have

- [ ] Outline sectioning logic: parse a markdown outline and split it into sections at `##` heading boundaries
- [ ] Each section generates an independent script (JS or Python) that produces a standalone PPTX chunk
- [ ] PPTX merge utility that combines section chunks into a single final deck
- [ ] Slide numbering fixed during merge (each section starts at 1 internally; merge renumbers to global sequence)
- [ ] Theme and visual consistency enforced across sections (all sections use the same theme file and helper library)
- [ ] Section metadata passed to each generation call: section index, total sections, global slide number offset, deck title
- [ ] Works with both pptxgenjs and python-pptx engines
- [ ] Fallback: outlines with ≤12 slides generate as a single script (no sectioning overhead for small decks)

### Nice to Have

- [ ] Parallel section generation via subagents (dispatch N sections concurrently)
- [ ] Section-level error recovery: if one section fails, regenerate just that section
- [ ] Progress reporting: "Section 2/4 complete (slides 9–16)"
- [ ] `SECTION:` directive in outline markdown to override automatic section boundaries
- [ ] Section dependency graph (e.g., title slide section must complete first to establish deck-level metadata)

### Out of Scope

- Cross-section content optimization (e.g., narrative arc across sections) — each section is self-contained
- Automatic slide reordering or deduplication across sections
- Real-time streaming of section generation progress to the web UI
- Modifying the aippt core pipeline (`cli.py create` command) — this is a skill-level feature

---

## Design

### Approach

The sectioned generation workflow has four phases:

```
PARSE → SPLIT → GENERATE → MERGE

1. PARSE:    Read outline.md, extract frontmatter, parse into slide entries
2. SPLIT:    Group slides by ## section headings into N chunks
3. GENERATE: For each chunk, generate a script using the helper library, execute it → chunk.pptx
4. MERGE:    Combine chunk PPTX files into final.pptx, fix slide numbers
```

### Phase 1: Outline Parsing

Use the existing outline parsing logic (similar to `parser.py`'s `parse_outline()`). Extract:
- Deck title (first `#` heading)
- Subtitle (if present under title)
- Sections (each `##` heading starts a new section)
- Slides within each section (each `###` or `##` child heading)
- `LAYOUT:` and `IMAGE:` directives per slide
- `*Notes:*` blocks for speaker notes

### Phase 2: Section Splitting

```
Outline structure:
  # Deck Title              → metadata (shared with all sections)
  ## Section A               → Section 1: slides 1-8
    ### Slide 1
    ### Slide 2
    ...
  ## Section B               → Section 2: slides 9-16
    ### Slide 3
    ...
  ## Section C               → Section 3: slides 17-24
    ...
```

**Rules:**
- Title slide always goes in Section 1
- Closing slide always goes in the last section
- `##` headings with no slide children (pure section dividers) attach to the next section
- If the outline has no `##` headings, treat the entire outline as one section
- Maximum section size: 12 slides (split further if a section exceeds this)
- Minimum section size: 3 slides (merge with adjacent section if too small)

**Section context object** (passed to each generation call):

```json
{
  "deckTitle": "AMD SMI MCP Server",
  "sectionIndex": 1,
  "totalSections": 3,
  "globalSlideOffset": 8,
  "totalSlides": 24,
  "theme": "themes/amd.yaml",
  "engine": "pptxgenjs",
  "slides": [
    {
      "title": "Sandboxed Execution",
      "layout": "bullet",
      "bullets": ["**MontySandbox** — runs in secure sandbox", "..."],
      "notes": "..."
    }
  ]
}
```

### Phase 3: Section Generation

Each section is generated independently. With the helper library (companion PRD), each section script is ~15–30 lines:

**pptxgenjs section script:**
```javascript
import { createDeck, addBulletSlide, addProcessFlow,
         addTwoColumn } from '../lib/pptxgenjs-helpers.mjs';

async function buildSection() {
  const deck = await createDeck('themes/amd.yaml');
  let sn = 9;  // globalSlideOffset + 1

  addBulletSlide(deck, "Sandboxed Execution", [
    "**MontySandbox** — every tool call runs inside a secure sandbox",
    "**30-second timeout** — prevents runaway operations",
  ], sn++);

  addTwoColumn(deck, "Read-Only Monitoring", "Category", "Category",
    ["SYSTEM-INFO (12)", "MONITORING (15)"],
    ["PCIE-TOPOLOGY (10)", "PROCESS (5)"],
    sn++
  );

  await deck.save('output/sections/section-2.pptx');
}

buildSection().catch(console.error);
```

**python-pptx section script:**
```python
import sys; sys.path.insert(0, 'lib')
from pptx_helpers import load_template, save_deck, set_placeholder, add_bullets

prs = load_template('templates/corp.pptx')

# Slide 9
slide = prs.slides.add_slide(prs.slide_layouts[3])
set_placeholder(slide, 0, "Sandboxed Execution")
add_bullets(slide, 10, [
    "**MontySandbox** — every tool call runs inside a secure sandbox",
    "**30-second timeout** — prevents runaway operations",
])

save_deck(prs, 'output/sections/section-2.pptx')
```

**Parallel generation** (Nice to Have): The skill dispatches N subagents, each generating one section. All sections share the same theme and helper library. This is a natural fit for the `superpowers:dispatching-parallel-agents` skill.

### Phase 4: PPTX Merge

A Python utility (`lib/merge.py`) that:

1. Opens each section PPTX in order
2. Copies all slides from each section into a new master Presentation
3. Fixes slide number text boxes (renumbers from 1 to N globally)
4. For pptxgenjs: copies each section's slide XML + media into the master
5. For python-pptx: uses `python-pptx`'s slide copy mechanism (copy `sldId` entries and relationships)
6. Saves the merged deck

**Slide copying strategy:**

python-pptx doesn't have a built-in "copy slide from another presentation" API. Two approaches:

**Option A: XML-level copy (recommended)**
```python
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
import copy

def merge_decks(chunk_paths, output_path):
    """Merge multiple PPTX files into one."""
    master = Presentation()
    # Set slide dimensions from first chunk
    first = Presentation(chunk_paths[0])
    master.slide_width = first.slide_width
    master.slide_height = first.slide_height

    for path in chunk_paths:
        src = Presentation(path)
        for slide in src.slides:
            # Copy slide layout, then copy slide content
            # (implementation uses lxml deep copy + relationship mapping)
            ...
    master.save(output_path)
```

**Option B: pptxgenjs-native merge (for JS engine)**
Since pptxgenjs generates from scratch (no template), the merge can simply generate all slides into one pptx object in a single script that imports section data:
```javascript
// merge.mjs — load section data files, call helpers in sequence
import { createDeck } from '../lib/pptxgenjs-helpers.mjs';

const deck = await createDeck('themes/amd.yaml');
// Import and execute each section's slide definitions
for (const sectionFile of sectionFiles) {
  const section = await import(sectionFile);
  await section.addSlides(deck);
}
await deck.save('output/final.pptx');
```

This avoids PPTX-level merging entirely for pptxgenjs — each section exports an `addSlides(deck)` function rather than producing a standalone PPTX. The "merge" is just calling all section functions on one pptx object.

**Recommended approach:** Use Option B for pptxgenjs (function-level composition) and Option A for python-pptx (XML-level copy). This plays to each engine's strengths.

### Section Decision Thresholds

| Outline Size | Strategy |
|---|---|
| ≤12 slides | Single script (no sectioning) |
| 13–24 slides | 2–3 sections |
| 25–36 slides | 3–4 sections |
| 37+ slides | 4–6 sections (cap section size at ~10 slides) |

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `lib/merge.py` | New | PPTX merge utility (copy slides between presentations) |
| `lib/section_parser.py` | New | Outline → section splitting logic |
| `.claude/skills/create-deck/SKILL.md` | Modified | Add sectioned generation workflow for large outlines |
| `.claude/skills/create-deck/references/sectioned-generation.md` | New | Reference doc for section context format and merge process |
| `aippt/cli.py` | Modified (Nice to Have) | Add `merge` subcommand |

### Data Model Changes

No data model changes.

---

## CLI Changes

### New Commands

```
aippt.py merge <chunk1.pptx> <chunk2.pptx> [...] -o <output.pptx>
```

Merges multiple PPTX section files into one deck in the order provided.

| Argument | Required | Description |
|----------|----------|-------------|
| `chunk*.pptx` | Yes | One or more PPTX files to merge, in order |
| `-o`, `--output` | Yes | Output file path |
| `--renumber` | No (default: true) | Fix slide number text boxes to global numbering |

### Example Usage

```bash
# Merge 3 sections into final deck
python aippt.py merge output/sections/section-1.pptx output/sections/section-2.pptx output/sections/section-3.pptx -o output/final-deck.pptx

# Merge with glob
python aippt.py merge output/sections/section-*.pptx -o output/final-deck.pptx
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_section_parser.py` | `TestSectionSplitting`, `TestSectionBoundaries`, `TestSmallOutlineFallback` | `lib/section_parser.py` — splitting logic, min/max section sizes |
| `tests/test_merge.py` | `TestMergeSlideCount`, `TestMergeSlideOrder`, `TestRenumbering` | `lib/merge.py` — PPTX merge, slide count preservation, numbering |

### Integration Tests

1. Parse `outlines/mcp-amdsmi-overview.md` (15 slides) → verify 2 sections created
2. Parse `outlines/ai-techjam-vienna.md` (30+ slides) → verify 3–4 sections created
3. Generate 2 section PPTX files independently → merge → verify final deck has correct slide count and ordering
4. Merge 3 PPTX files → verify slide numbers are sequential (1, 2, 3, ... N)

### Manual Testing

1. Run full sectioned workflow on a 20+ slide outline — verify each section generates without errors
2. Open merged PPTX in LibreOffice/PowerPoint — verify all slides present, no corruption
3. Verify slide numbers are sequential across section boundaries
4. Verify theme colors/fonts are consistent across section boundaries
5. Compare merged deck to a single-pass generation of the same outline — visual spot check for consistency

---

## Changelog Entry

```markdown
### Added
- Sectioned deck generation for large outlines (20+ slides) — generates in parallel chunks, merges into final PPTX
- `aippt.py merge` command for combining multiple PPTX files
- `lib/section_parser.py` for outline sectioning logic
- `lib/merge.py` for PPTX merge operations
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Create `lib/section_parser.py` — outline parsing and section splitting | `lib/section_parser.py` | -- |
| 2 | Create `lib/merge.py` — PPTX slide copy and merge | `lib/merge.py` | -- |
| 3 | Add unit tests for section parser | `tests/test_section_parser.py` | 1 |
| 4 | Add unit tests for merge utility | `tests/test_merge.py` | 2 |
| 5 | Update SKILL.md with sectioned generation workflow | `.claude/skills/create-deck/SKILL.md` | 1, 2 |
| 6 | Create `references/sectioned-generation.md` | `.claude/skills/create-deck/references/sectioned-generation.md` | 1 |
| 7 | Integration test: section + generate + merge a real outline | -- | 1, 2, helper library PRD |
| 8 | Wire up `merge` CLI subcommand (Nice to Have) | `aippt/cli.py` | 2 |
| 9 | Add parallel subagent dispatch to SKILL.md for section generation (Nice to Have) | `.claude/skills/create-deck/SKILL.md` | 5 |

---

## Risks & Open Questions

- **Risk:** PPTX slide copying is notoriously fragile — media references (images, embedded fonts) may break during merge. Mitigation: test thoroughly with decks containing images/icons; consider using `python-pptx-copier` or similar libraries if the built-in approach is insufficient.
- **Risk:** Visual inconsistency between sections if different subagents make slightly different styling choices. Mitigation: the helper library (companion PRD) eliminates this by centralizing all styling in reusable functions. Subagents only provide data, not styling code.
- **Risk:** For pptxgenjs, the function-composition approach (Option B) requires each section to export a function rather than be a standalone script. This changes the mental model slightly. Mitigation: provide clear examples in the reference docs; the function export pattern is simpler than standalone scripts.
- **Question:** Should the section parser live in `lib/` or in `aippt/`? — Recommendation: `lib/` since it's used by the skill, not the core pipeline. Move to `aippt/` if the `merge` CLI command becomes a first-class feature.
- **Question:** How should section boundaries handle `IMAGE:` directives that reference files? — The image path should be resolved relative to the outline file (same as today), and each section script uses the same relative path. No special handling needed.
- **Question:** For pptxgenjs function-composition merge, should each section be a separate `.mjs` file or should sections be encoded as JSON data files? — Recommendation: separate `.mjs` files with `export async function addSlides(deck)`, since this keeps the pattern consistent with standalone scripts and allows manual execution of individual sections for debugging.
- **Dependency:** This PRD depends on the helper library PRD (`2026-03-11-slide-helper-libraries.md`). Without helpers, sectioned scripts would still be 200+ lines each, negating much of the context savings. Implement helpers first.

---

## References

- Companion PRD: `docs/plans/2026-03-11-slide-helper-libraries.md`
- Large outline example: `outlines/ai-techjam-vienna.md` (30+ slides, natural section structure)
- Existing section-named script: `output/quarterly-review-sections.js`
- python-pptx slide copy discussion: https://github.com/scanny/python-pptx/issues/132
- Parallel subagent pattern: `superpowers:dispatching-parallel-agents` skill
