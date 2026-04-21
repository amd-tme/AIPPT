# Create-Deck Skill Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a `/create-deck` Claude Code skill that generates PowerPoint decks from markdown outlines using pptxgenjs or python-pptx engines with theme-based styling.

**Architecture:** The skill is documentation-driven (SKILL.md + reference docs) with no executable code — Claude reads the instructions and generates tailored scripts per invocation. Theme config (YAML) defines brand styling. A slash command routes to the skill.

**Tech Stack:** Claude Code skills (markdown), YAML (theme config), pptxgenjs (Node.js), python-pptx (Python)

**Spec:** `docs/plans/2026-03-10-create-deck-skill.md`

---

## File Structure

```
.claude/
  skills/
    create-deck/
      SKILL.md                              # Main skill — interactive flow, layout strategy, generation instructions
      references/
        theme-schema.md                     # Theme YAML format reference
        pptxgenjs-guide.md                  # pptxgenjs pitfalls, patterns, and code examples
        python-pptx-guide.md               # python-pptx template engine patterns
  commands/
    create-deck.md                          # Slash command router (invokes the skill)

themes/
  amd.yaml                                  # AMD corporate theme config
  default.yaml                              # Minimal default theme config
  assets/
    amd-logo-white.png                      # AMD logo extracted from templates/corp.pptx
    amd-wordmark.png                        # AMD text wordmark from template
```

**Dependency:** `pptxgenjs`, `react-icons`, `react`, `react-dom`, `sharp` must be installed globally via npm. `python-pptx` is already in `requirements.txt`.

---

## Chunk 1: Theme System

### Task 1: Extract Logo Assets from Corporate Template

**Files:**
- Create: `themes/assets/amd-logo-white.png`
- Create: `themes/assets/amd-wordmark.png`

The corporate template (`templates/corp.pptx`) is a ZIP archive containing logo images in `ppt/media/`.

- [ ] **Step 1: Create themes directory structure**

```bash
mkdir -p themes/assets
```

- [ ] **Step 2: Extract logo images from template**

```bash
cd /home/matt/git/shamsway/aippt
unzip -j templates/corp.pptx ppt/media/image2.jpg -d /tmp/corp-extract/
unzip -j templates/corp.pptx ppt/media/image3.png -d /tmp/corp-extract/
```

- `image2.jpg` — AMD logo graphic (dark background)
- `image3.png` — AMD text wordmark

- [ ] **Step 3: Convert and copy to themes/assets/**

The logo from the template has a dark background. For pptxgenjs slides (which also use dark backgrounds), this works directly. Copy as-is and also create a clean PNG version if needed.

```bash
cp /tmp/corp-extract/image2.jpg themes/assets/amd-logo.jpg
cp /tmp/corp-extract/image3.png themes/assets/amd-wordmark.png
```

- [ ] **Step 4: Verify images are readable**

Open each image to verify they're valid and contain the expected AMD branding. Use `file` command to confirm format:

```bash
file themes/assets/amd-logo.jpg
file themes/assets/amd-wordmark.png
```

Expected: JPEG and PNG format confirmations.

- [ ] **Step 5: Commit**

```bash
git add themes/assets/
git commit -m "feat: extract AMD logo assets from corporate template"
```

---

### Task 2: Create Theme Config Files

**Files:**
- Create: `themes/amd.yaml`
- Create: `themes/default.yaml`

- [ ] **Step 1: Create AMD theme config**

Write `themes/amd.yaml` with colors, fonts, and logo settings derived from the corporate template. The template uses a black background with white text and the AMD logo in the bottom-right corner. Accent color is teal (`00B4D8`) based on our experiment.

```yaml
name: AMD Corporate
description: Black/white minimal with teal accent, matching corp.pptx template

colors:
  background: "000000"
  background_alt: "1A1A2E"
  surface: "16213E"
  text_primary: "FFFFFF"
  text_secondary: "94A3B8"
  text_body: "E2E8F0"
  accent: "00B4D8"
  accent_alt: "06D6A0"
  warning: "E94560"

fonts:
  heading: "Trebuchet MS"
  body: "Calibri"
  mono: "Consolas"

logo:
  path: "themes/assets/amd-wordmark.png"
  position: "bottom-right"
  width_inches: 1.2

slide:
  layout: "LAYOUT_16x9"
  margin_inches: 0.5

footer:
  show: true
  text: ""
  show_slide_numbers: true
```

- [ ] **Step 2: Create default theme config**

Write `themes/default.yaml` — a clean dark theme with no logo, usable for non-branded decks.

```yaml
name: Default
description: Clean dark theme, no branding

colors:
  background: "1E293B"
  background_alt: "0F172A"
  surface: "334155"
  text_primary: "F8FAFC"
  text_secondary: "94A3B8"
  text_body: "CBD5E1"
  accent: "3B82F6"
  accent_alt: "10B981"
  warning: "EF4444"

fonts:
  heading: "Trebuchet MS"
  body: "Calibri"
  mono: "Consolas"

logo:
  path: ""
  position: "bottom-right"
  width_inches: 0

slide:
  layout: "LAYOUT_16x9"
  margin_inches: 0.5

footer:
  show: true
  text: ""
  show_slide_numbers: true
```

- [ ] **Step 3: Verify YAML is valid**

```bash
venv/bin/python -c "import yaml; print(yaml.safe_load(open('themes/amd.yaml'))['name'])"
venv/bin/python -c "import yaml; print(yaml.safe_load(open('themes/default.yaml'))['name'])"
```

Expected: `AMD Corporate` and `Default`.

- [ ] **Step 4: Commit**

```bash
git add themes/amd.yaml themes/default.yaml
git commit -m "feat: add AMD and default theme configs for create-deck skill"
```

---

### Task 3: Create Theme Schema Reference

**Files:**
- Create: `.claude/skills/create-deck/references/theme-schema.md`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p .claude/skills/create-deck/references
```

- [ ] **Step 2: Write theme-schema.md**

Document the complete YAML schema with field descriptions, valid values, and examples. This reference is read by Claude when generating scripts — it needs to know how to parse and apply theme values.

Contents should cover:
- Full schema with all fields and their types
- Color fields: 6-char hex without `#` prefix (pptxgenjs requirement)
- Font fields: must be fonts available on the target system
- Logo fields: path relative to project root, position options, width in inches
- Slide fields: pptxgenjs layout constants, margin in inches
- Footer fields: show/hide, custom text, slide numbers
- Example: how to create a new theme for a different brand

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/create-deck/references/theme-schema.md
git commit -m "docs: add theme YAML schema reference for create-deck skill"
```

---

## Chunk 2: Engine Reference Guides

### Task 4: Create pptxgenjs Guide

**Files:**
- Create: `.claude/skills/create-deck/references/pptxgenjs-guide.md`

This is the critical reference that Claude reads when generating pptxgenjs scripts. It must contain everything learned from our experiment and the pptx skill's `pptxgenjs.md`.

- [ ] **Step 1: Write pptxgenjs-guide.md**

Contents should cover these sections:

**Setup & Execution:**
- `NODE_PATH` must be set to `$(npm root -g)` for globally installed packages
- Script structure: require, create pres, add slides, writeFile
- Async pattern needed for icon generation (wrap in `async function buildDeck()`)

**Critical Pitfalls (from experiment + pptx skill):**
- NEVER use `#` prefix on hex colors — causes file corruption
- NEVER encode opacity in hex color strings (8-char colors corrupt the file)
- NEVER reuse option objects across calls — pptxgenjs mutates objects in-place. Use factory functions for shadows.
- Use `bullet: true` not unicode `•` symbols
- Use `breakLine: true` between text array items
- Avoid `lineSpacing` with bullets — use `paraSpaceAfter` instead
- `charSpacing` not `letterSpacing` (silently ignored)
- `ROUNDED_RECTANGLE` + accent borders don't work — use `RECTANGLE`

**Layout Patterns (with code examples):**
- Title slide: centered text on dark background with accent line
- Section divider: large uppercase text, letter-spacing, accent bar
- Card grid (2x2): rectangle shapes with left accent bars, icons, shadow factory
- Icon + text rows: oval icon circles, label + description pairs
- Stat callout: large number (60-72pt) with supporting text
- Code block: dark rectangle with mono font, green text
- Process flow: horizontal boxes with arrow characters between
- Two-column: side-by-side content groups
- Three-column cards: vertical cards with top accent bars
- Standard bullets: bulleted text arrays with bold lead-ins

**Icon Integration:**
- react-icons + sharp for SVG → PNG base64 conversion
- `renderIconSvg()` and `iconToBase64()` helper functions
- Use size 256+ for crisp rendering
- Common icon imports from `react-icons/fa`

**Theme Application:**
- Read theme YAML at top of script
- Map theme colors to slide elements
- Logo placement using `slide.addImage()` with theme position/size
- Footer bar construction from theme settings

**Shadow Factory Pattern:**
```javascript
const cardShadow = () => ({
  type: "outer", blur: 4, offset: 2,
  angle: 135, color: "000000", opacity: 0.12
});
```

- [ ] **Step 2: Verify the guide includes code examples for each layout pattern**

Read through the file and confirm each layout pattern section has a self-contained, copy-pasteable code example that Claude can reference when generating scripts.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/create-deck/references/pptxgenjs-guide.md
git commit -m "docs: add pptxgenjs generation guide for create-deck skill"
```

---

### Task 5: Create python-pptx Guide

**Files:**
- Create: `.claude/skills/create-deck/references/python-pptx-guide.md`

- [ ] **Step 1: Write python-pptx-guide.md**

Contents should cover:

**Template Analysis:**
- How to enumerate slide layouts and their placeholders
- Placeholder types: TITLE (1), BODY (2), OBJECT (7), PICTURE (18)
- AMD template specifics: uses OBJECT (type 7) not BODY (type 2) for content
- Two-column placeholders are idx 12 and 13
- Template ships with 3 sample slides that must be removed

**Script Structure:**
- Load template with `Presentation('templates/corp.pptx')`
- Remove sample slides (code pattern from our experiment)
- Add slides using `prs.slides.add_slide(prs.slide_layouts[N])`
- Set text via placeholder index: find placeholder by `placeholder_format.idx`

**Key Layout Indices (corp.pptx):**
- 0: Title Slide - No Image (idx 0=title, 12=subtitle)
- 3: Title and Content (idx 0=title, 10=body)
- 5: Two Content (idx 0=title, 12=left, 13=right)
- 7: Title Only
- 17: Three content with headings (idx 0=title, 10/13/16=headings, 12/15/18=content)
- 26: Divider slide (idx 0=title, 14=subtitle)
- 28: Developer Code Layout (idx 0=title, 10=code body)
- 30: Closing logo slide

**Content Formatting:**
- Bullet levels via `paragraph.level = N`
- Bold via `run.font.bold = True`
- Speaker notes via `slide.notes_slide.notes_text_frame.text`
- Clear existing text with `text_frame.clear()` before writing

**Sample Slide Removal Pattern:**
```python
sample_count = len(prs.slides)
for i in range(sample_count - 1, -1, -1):
    rId = prs.slides._sldIdLst[i].rId
    prs.part.drop_rel(rId)
    del prs.slides._sldIdLst[i]
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/create-deck/references/python-pptx-guide.md
git commit -m "docs: add python-pptx template guide for create-deck skill"
```

---

## Chunk 3: Skill and Command

### Task 6: Create the Main SKILL.md

**Files:**
- Create: `.claude/skills/create-deck/SKILL.md`

This is the core deliverable — the instructions Claude reads when the skill is invoked. It must be comprehensive enough that Claude can generate a complete deck script from any outline without additional guidance.

- [ ] **Step 1: Write SKILL.md frontmatter and overview**

Frontmatter:
```yaml
---
name: create-deck
description: Create PowerPoint decks from markdown outlines using pptxgenjs (rich visuals) or python-pptx (template-based). Interactive workflow — walks through outline selection, engine choice, and theme configuration.
---
```

Overview section: brief description of what the skill does, the two engines, and when to use each.

- [ ] **Step 2: Write Environment Setup section**

Instructions for:
- Detecting venv Python path (same snippet from CLAUDE.md)
- Checking pptxgenjs availability: `NODE_PATH="$(npm root -g)" node -e "require('pptxgenjs')"`
- Checking icon deps: `NODE_PATH="$(npm root -g)" node -e "require('react-icons/fa'); require('sharp')"`
- Installing missing deps: `npm install -g pptxgenjs react-icons react react-dom sharp`

- [ ] **Step 3: Write Interactive Flow section**

Step-by-step instructions for the interactive prompts:

1. **Select outline** — Scan `outlines/` for `.md` files. Present via `AskUserQuestion`. If `$ARGUMENTS` is provided, use it as the outline path.
2. **Choose engine** — Ask: pptxgenjs (rich visuals, default) or python-pptx (use template). If user mentions "template" or provides a `.pptx` path, auto-select python-pptx.
3. **Choose theme/template** — If pptxgenjs: scan `themes/` for `.yaml` files. If only one, use it without asking. If python-pptx: scan `templates/` for `.pptx` files.
4. **Confirm output path** — Auto-derive from outline filename: `output/{outline-stem}.pptx`. Mention it but don't prompt unless user wants to change it.

- [ ] **Step 4: Write Generation: pptxgenjs section**

Instructions for generating and executing a pptxgenjs script:

1. Read the outline file and parse its structure (slides, directives, frontmatter)
2. Read the theme YAML file (load colors, fonts, logo settings)
3. Generate a complete, self-contained Node.js script that:
   - Requires pptxgenjs and icon libraries
   - Defines theme colors as constants from the YAML
   - Creates a shadow factory function (never reuse shadow objects)
   - Creates an icon-to-base64 helper function
   - Creates a footer helper function (using theme settings)
   - Builds each slide with the appropriate layout
   - Saves to the output path
4. Execute the script with `NODE_PATH="$(npm root -g)" node <script.js>`
5. Verify the output file exists and report results

Include the layout decision strategy table (content signals → layout types) and the layout variety rule.

- [ ] **Step 5: Write Generation: python-pptx section**

Instructions for generating and executing a python-pptx script:

1. Read the outline file and parse its structure
2. Analyze the template's available layouts (run the placeholder enumeration snippet)
3. Generate a Python script that:
   - Loads the template
   - Removes sample slides
   - Maps content to appropriate template layouts
   - Sets text in placeholders by index
   - Adds speaker notes from `*Notes:*` blocks
   - Saves to the output path
4. Execute with `venv/bin/python <script.py>`
5. Verify output

- [ ] **Step 6: Write Layout Guide section**

Document the content-signal-to-layout mapping:

| Content Signal | pptxgenjs Layout | python-pptx Layout |
|---|---|---|
| First `#` heading | Title slide (centered) | Layout 0 (Title Slide) |
| `#` heading, no `##` children | Section divider | Layout 26 (Divider) |
| 3-4 bold lead-in bullets | Card grid with icons | Layout 3 (Title and Content) |
| Prominent number/stat | Stat callout (large number) | Layout 3 (Title and Content) |
| Code blocks / CLI commands | Code panel (dark bg, mono) | Layout 28 (Developer Code) |
| `LAYOUT: two_column` or `|||` | Side-by-side columns | Layout 5 (Two Content) |
| `LAYOUT: numbered` / steps | Process flow (numbered) | Layout 3 (Title and Content) |
| Standard bullets | Icon + text rows | Layout 3 (Title and Content) |

Include the layout variety rule: never repeat the same layout on consecutive slides.

- [ ] **Step 7: Write Output & Handoff section**

Document:
- Output file naming: `output/{outline-stem}.pptx`
- Script retention: save generated `.js`/`.py` alongside the `.pptx`
- Next steps message to show the user:
  - `/deck-review` for visual QA
  - `aippt ingest <output.pptx>` for cataloging and tags
  - `aippt improve <output.pptx>` for LLM refinement

- [ ] **Step 8: Write Troubleshooting section**

Table of common issues and solutions:
- pptxgenjs not found → install with npm, set NODE_PATH
- Corrupted .pptx → check for shadow object reuse, `#` in hex colors, 8-char color strings
- Missing logo → verify theme `logo.path` points to an existing file
- Missing fonts → use system-available fonts (Calibri, Arial, Trebuchet MS)
- Template placeholders not filling → check placeholder idx values, AMD uses OBJECT type 7
- Icons not rendering → install react-icons, react, react-dom, sharp globally

- [ ] **Step 9: Read through SKILL.md end-to-end for completeness**

Verify:
- All sections present and logically ordered
- Reference docs linked with `[text](references/filename.md)` syntax
- No placeholder or TODO content remaining
- Instructions are specific enough for Claude to generate a complete script

- [ ] **Step 10: Commit**

```bash
git add .claude/skills/create-deck/SKILL.md
git commit -m "feat: add create-deck skill definition"
```

---

### Task 7: Create Slash Command

**Files:**
- Create: `.claude/commands/create-deck.md`

- [ ] **Step 1: Write create-deck.md**

```markdown
---
description: Create a PowerPoint deck from a markdown outline
---

Use the create-deck skill to generate a PowerPoint presentation.
Walk the user through outline selection, engine choice, and theme
configuration interactively.

If arguments are provided, treat them as the outline file path: $ARGUMENTS
```

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/create-deck.md
git commit -m "feat: add /create-deck slash command"
```

---

## Chunk 4: Verification

### Task 8: End-to-End Verification

**Files:**
- None created (verification only)

Test the complete workflow by generating a deck from an existing outline.

- [ ] **Step 1: Verify skill is discoverable**

Start a new Claude Code conversation (or use `/help` to list commands) and confirm `/create-deck` appears in the available commands list.

- [ ] **Step 2: Run /create-deck with pptxgenjs engine**

Invoke `/create-deck` and walk through the interactive flow:
- Outline: `outlines/Q1/Q126 - AMD GPU Operator and Kubernetes.md`
- Engine: pptxgenjs
- Theme: amd

Verify:
- Script generated at `output/Q126 - AMD GPU Operator and Kubernetes.js`
- PPTX generated at `output/Q126 - AMD GPU Operator and Kubernetes.pptx`
- PPTX opens without corruption in PowerPoint or LibreOffice
- Slides use varied layouts (not all bullets)
- AMD theme colors and logo are applied

- [ ] **Step 3: Run /create-deck with python-pptx engine**

Invoke `/create-deck` again:
- Outline: same as above
- Engine: python-pptx
- Template: `templates/corp.pptx`

Verify:
- Script generated at `output/Q126 - AMD GPU Operator and Kubernetes.py`
- PPTX generated and opens without corruption
- Corporate template branding is present (logo, colors, footer)
- No leftover "Click to edit..." placeholder text

- [ ] **Step 4: Run /deck-review on generated output**

Invoke `/deck-review` to confirm the handoff workflow works:
- Convert to images via LibreOffice + pdftoppm
- Visual QA identifies any issues
- Confirm aippt integration: `venv/bin/python aippt.py ingest output/<deck>.pptx`

- [ ] **Step 5: Fix any issues found during verification**

If issues are found:
- Update the relevant reference doc or SKILL.md
- Re-test the affected engine
- Commit fixes

- [ ] **Step 6: Final commit**

```bash
git add -A .claude/skills/create-deck/ .claude/commands/create-deck.md themes/
git commit -m "feat: create-deck skill — complete implementation with themes and commands"
```

---

## Update CLAUDE.md

### Task 9: Update Project Documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add create-deck to CLAUDE.md**

Add a section under the existing documentation that mentions the `/create-deck` command and the themes directory. Keep it brief — the skill itself has the detailed docs.

Add to the CLI Commands section or a new Skills section:
```markdown
## Skills / Slash Commands

- `/create-deck` — Generate a PowerPoint deck from a markdown outline (pptxgenjs or python-pptx)
- `/deck-review` — Visual QA and full lifecycle review of generated decks
```

Add `themes/` to the Architecture section's file tree.

- [ ] **Step 2: Update Active PRDs table**

Add the create-deck skill PRD to the Active PRDs table in CLAUDE.md with its branch and status.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add create-deck skill to CLAUDE.md"
```
