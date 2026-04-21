# Helper Library Remediation Plan

**Date:** 2026-03-11
**Source:** First real-world test of create-deck with helper libraries (32-slide deck)

---

## Priority 1: Broken (blocks generation)

### Fix 1: ESM import pattern for react-icons

**Problem:** The pptxgenjs guide uses `await import('react-icons/fa')` but `NODE_PATH` doesn't propagate to ESM dynamic imports. Every generation fails until the user manually switches to `createRequire`.

**Files:**
- `.claude/skills/create-deck/references/pptxgenjs-guide.md` — 8 occurrences of `await import()`
- The helper library itself (`lib/pptxgenjs-helpers.mjs`) already uses `createRequire` correctly

**Fix:** Replace all `await import('react-icons/...')` with the `createRequire` pattern:

```javascript
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { FaServer } = require('react-icons/fa');
const { SiDocker } = require('react-icons/si');
```

**Locations to change (line numbers from current file):**
- Line 45: `const { FaServer } = await import('react-icons/fa');`
- Line 267-268: template icon imports
- Line 286: SI icon discovery snippet
- Line 303: SI import example
- Line 356: FA import example
- Line 398-399: complete example icon imports

Also update the script template (lines ~30-50) to include `createRequire` in the boilerplate.

---

## Priority 2: Incorrect guidance (causes confusion)

### Fix 2: Remove vestigial TOTAL constant

**Problem:** Guide says "ALWAYS count total slides before generating, set TOTAL constant" but nothing uses it. Dead code confuses the LLM.

**Files:**
- `.claude/skills/create-deck/references/pptxgenjs-guide.md` — line 41 (`const TOTAL = 15;`)
- `.claude/skills/create-deck/SKILL.md` — line 106 ("ALWAYS count total slides...")

**Fix:** Remove the `TOTAL` constant from the template and delete the "ALWAYS count total slides" rule from SKILL.md. If slide-of-total footer is wanted later, add it as a feature to the helper library's `addFooter()`.

### Fix 3: Raise sectioned generation threshold

**Problem:** The 12-slide threshold was set when scripts had inline layout logic (~40 lines/slide). With helper libraries, scripts are ~5-10 lines/slide. A 32-slide deck worked fine as a single 300-line script.

**Files:**
- `.claude/skills/create-deck/SKILL.md` — lines 318, 324
- `.claude/skills/create-deck/references/sectioned-generation.md` — lines 3, 9-12, 14, 93

**Fix:** Change threshold from 12 to 25. Update tables:

| Outline Size | Strategy |
|---|---|
| ≤25 slides | Single script |
| 26–40 slides | 2–3 sections |
| 41+ slides | 3–5 sections |

Add qualifying note: "With helper library imports, single-script generation works well up to ~40 slides. Sectioning primarily benefits outlines with 25+ slides where context diversity (many different layout types, icon sets) would stress the LLM."

---

## Priority 3: Missing functionality in helpers

### Fix 4: Add `notes` parameter to all slide builders

**Problem:** Only `addBulletSlide` accepts a `notes` param. `*Notes:*` blocks from outlines can't attach to icon rows, card grids, process flows, etc. without raw `slide.addNotes()` after the helper call.

**Files:**
- `lib/pptxgenjs-helpers.mjs` — all `export function add*Slide()` functions

**Fix:** Add optional `notes` parameter (last arg or via options object) to every slide builder:

```javascript
// Functions to update (add notes param):
export function addIconRowsSlide(deck, title, items, iconImages, slideNum, notes)
export function addProcessFlow(deck, title, steps, slideNum, notes)
export function addTwoColumn(deck, title, leftHeader, rightHeader, leftItems, rightItems, slideNum, notes)
export function addCardGrid(deck, title, cards, slideNum, notes)
export function addStatCallout(deck, title, stats, slideNum, notes)
export function addCodeSlide(deck, title, code, slideNum, notes)
export function addClosingSlide(deck, slideNum, notes)  // rarely used but consistent
```

Each function adds before the `return slide;`:
```javascript
if (notes) slide.addNotes(notes);
```

Also update the python-pptx helper `lib/pptx_helpers.py` — `add_bullets`, `add_bullets_with_sub`, `add_numbered_bullets` don't call `set_notes()`. Consider adding a notes param there too, or document that callers should call `set_notes(slide, text)` separately (which already exists in the lib).

Update reference docs to show the notes parameter in examples.

### Fix 5: Add sub-bullet support to pptxgenjs bullet slides

**Problem:** Outlines frequently have indented sub-bullets. `addBulletSlide` only handles flat string arrays. The python-pptx helper has `add_bullets_with_sub` but pptxgenjs has no equivalent.

**Files:**
- `lib/pptxgenjs-helpers.mjs` — `addBulletSlide` function

**Fix:** Support mixed input — strings for flat bullets, `{text, subs: [...]}` objects for items with sub-bullets:

```javascript
export function addBulletSlide(deck, title, bullets, slideNum, notes) {
  // ...existing setup...

  const textItems = [];
  bullets.forEach((b) => {
    if (typeof b === 'object' && b.subs) {
      // Parent bullet
      _pushBulletItem(textItems, b.text, leadSize, bodySize, spacing, C);
      // Sub-bullets (smaller, indented)
      b.subs.forEach(sub => {
        textItems.push({
          text: sub,
          options: {
            fontSize: bodySize - 2,
            color: C.text_body,
            bullet: true,
            indentLevel: 1,
            breakLine: true,
            paraSpaceAfter: spacing / 2,
          }
        });
      });
    } else {
      const text = typeof b === 'string' ? b : b.text;
      _pushBulletItem(textItems, text, leadSize, bodySize, spacing, C);
    }
  });
  // ...rest unchanged...
}
```

Update reference docs to show both flat and nested formats.

### Fix 6: Handle 3-item card grid layout

**Problem:** `addCardGrid` uses `cols = n <= 4 ? 2 : 3`, so 3 cards render as a 2+1 grid with an empty bottom-right. Looks unbalanced.

**Files:**
- `lib/pptxgenjs-helpers.mjs` — `addCardGrid` function (line 631)

**Fix:** Change column logic to handle 3 items as single row:

```javascript
const cols = n === 3 ? 3 : n <= 4 ? 2 : 3;
```

This gives: 2 items → 2 cols (1 row), 3 items → 3 cols (1 row), 4 items → 2 cols (2 rows), 5-6 → 3 cols.

Alternatively, add `addThreeColumnCards(deck, title, cards, slideNum, notes)` as a distinct layout function that's purpose-built for exactly 3 items with wider cards. The layout decision table already references "Three-column cards" as a layout type.

---

## Priority 4: Documentation improvements

### Fix 7: Document icon fallback strategy for duplicate items

**Problem:** When multiple items need icons but all map to the same generic FA icon (e.g., 3 databases → FaDatabase), repeating the same icon looks bad.

**Files:**
- `.claude/skills/create-deck/references/pptxgenjs-guide.md` — icon selection section
- `.claude/skills/create-deck/SKILL.md` — Icon Selection Strategy section

**Fix:** Add guidance after the existing icon priority list:

```markdown
**When multiple items share the same fallback icon:**
- If 3+ items would use the same FA icon, use accent-bar fallback for ALL of them instead
- Alternatively, vary FA icons by concept (FaDatabase, FaServer, FaCloud for different infra)
- Never repeat the exact same icon+color on more than 2 items — it looks like a rendering bug
```

### Fix 8: Reframe layout variety as a validation step

**Problem:** The "maintain a `prevLayout` variable" instruction is a mental exercise. It would be more actionable as a post-planning check.

**Files:**
- `.claude/skills/create-deck/SKILL.md` — Layout Variety Rule section

**Fix:** Rewrite as a two-step process:

```markdown
### Layout Variety Rule

1. **Plan phase:** For each slide, choose the best layout based on content signals (table above).
2. **Validation phase:** Scan the planned layout sequence. If two consecutive slides use the same
   layout type, swap the second to the next-best alternative from the substitution table below.
```

### Fix 9: Document auto-split as a manual LLM step

**Problem:** The auto-split for numbered slides with CLI commands is described in the skill but has no helper function. It's unclear whether this is automated or manual.

**Files:**
- `.claude/skills/create-deck/SKILL.md` — CLI Command Detection section

**Fix:** Add a note clarifying this is a content-analysis step performed during outline parsing, not a helper library function:

```markdown
> **Note:** Auto-split is a content analysis step — examine the bullets, separate concept items
> from CLI commands, then call `addProcessFlow()` for the concepts and `addCodeSlide()` for the
> commands. There is no automatic detection helper; the LLM performs this split during layout planning.
```

---

## Priority 3 (continued): Missing functionality in helpers

### Fix 10: Add `addImageSlide` and `addImageBulletsSlide` helper functions

**Problem:** Outlines with `IMAGE:` directives need image-based layouts. During the first real-world run, two custom layout functions were written inline in the generated script — `addImageSlide` (full-bleed image with optional caption) and `addImageBulletsSlide` (image on left, bullets on right). These should be standardized in the helper library.

**Files:**
- `lib/pptxgenjs-helpers.mjs` — add two new exported functions
- `.claude/skills/create-deck/references/pptxgenjs-guide.md` — document the new functions

**Fix:** Add two functions to the helper library:

```javascript
// Full-image slide with optional title overlay or caption bar
export function addImageSlide(deck, title, imagePath, slideNum, notes)

// Split layout: image on left (~50%), bullets on right (~50%)
export function addImageBulletsSlide(deck, title, imagePath, bullets, slideNum, notes)
```

Design considerations:
- Image sizing should respect aspect ratio (use `sizing: { type: 'contain' }` or manual calculation)
- `addImageSlide`: image fills content area; title rendered as semi-transparent overlay bar at top or bottom
- `addImageBulletsSlide`: left half = image (vertically centered), right half = bullet list using same styling as `addBulletSlide`
- Both should accept `imagePath` as a file path string (resolved by the caller) or a base64 data URI
- Layout constants (`M`, `CONTENT_Y`, `CONTENT_W`, `CONTENT_H`) should be used for positioning consistency

### Fix 11: Image path resolution convention

**Problem:** Outline `IMAGE:` directives use paths like `IMAGE: memes/this-is-fine.jpg` or `IMAGE: images/arch.png`. These are ambiguous — relative to the outline file? The project root? The output directory? The generated script needs to resolve them correctly.

**Files:**
- `.claude/skills/create-deck/SKILL.md` — document the resolution convention
- Possibly `lib/pptxgenjs-helpers.mjs` — optional resolver utility

**Fix:** Establish a convention and document it:

1. **Convention:** Image paths in outlines are relative to the project root (where `aippt.py` lives), not relative to the outline file or output directory
2. **Script generation:** When the LLM generates a script, it should resolve `IMAGE: foo/bar.png` to a path like `'foo/bar.png'` (relative to CWD when running the script) or an absolute path
3. **Optional utility:** Consider adding a `resolveImagePath(relativePath, basePath?)` helper that:
   - Checks if the path exists as-is
   - Tries resolving relative to a provided base directory
   - Returns the absolute path or throws a clear error
4. **Document in SKILL.md:** Under the "Diagram + Image Handling" section, add guidance on how the LLM should handle `IMAGE:` paths when generating scripts

---

## Implementation Checklist

| # | Priority | Fix | Files |
|---|----------|-----|-------|
| 1 | P1 | Replace `await import()` with `createRequire` | `references/pptxgenjs-guide.md` |
| 2 | P2 | Remove TOTAL constant and rule | `references/pptxgenjs-guide.md`, `SKILL.md` |
| 3 | P2 | Raise section threshold 12→25 | `SKILL.md`, `references/sectioned-generation.md` |
| 4 | P3 | Add `notes` param to all slide builders | `lib/pptxgenjs-helpers.mjs`, `references/pptxgenjs-guide.md` |
| 5 | P3 | Add sub-bullet support to `addBulletSlide` | `lib/pptxgenjs-helpers.mjs`, `references/pptxgenjs-guide.md` |
| 6 | P3 | Fix 3-item card grid layout | `lib/pptxgenjs-helpers.mjs` |
| 7 | P4 | Document icon fallback for duplicates | `SKILL.md`, `references/pptxgenjs-guide.md` |
| 8 | P4 | Reframe layout variety as validation | `SKILL.md` |
| 9 | P4 | Clarify auto-split is manual | `SKILL.md` |
| 10 | P3 | ✅ Add `addImageSlide` and `addImageBulletsSlide` helpers | `lib/pptxgenjs-helpers.mjs`, `references/pptxgenjs-guide.md` |
| 11 | P3 | ✅ Image path resolution convention | `SKILL.md`, possibly `lib/pptxgenjs-helpers.mjs` |
