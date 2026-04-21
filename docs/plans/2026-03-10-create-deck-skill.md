# PRD: Create-Deck Skill and Slash Command

**Date:** 2026-03-10
**Status:** Draft
**Branch:** TBD

## Summary

A `/create-deck` Claude Code skill and slash command that generates PowerPoint presentations from markdown outlines. Supports two generation engines: pptxgenjs (Node.js, rich visual output with theme config) and python-pptx (template-based, corporate compliance). Focused on generation only — visual QA, notes, tags, and refinement are handled by the existing deck-reviewer skill and aippt CLI.

## Motivation

The aippt CLI's `create` command produces functional decks but is constrained by its python-pptx pipeline and template placeholder system. Our experiment (2026-03-10) showed that pptxgenjs can produce visually superior decks with card grids, stat callouts, icon rows, and process flows — layouts impossible within template placeholders. However, pptxgenjs doesn't support importing existing templates, and the python-pptx engine guarantees exact brand compliance.

A hybrid skill that supports both engines gives users the best of both worlds: rich visual output when creative freedom matters, template compliance when brand requirements are strict.

## Design Decisions

### Approach: Monolithic Script Generator

Claude reads the outline and theme config, then generates a complete, self-contained `.js` or `.py` script tailored to the specific deck content. No reusable template library — Claude's intelligence IS the layout engine.

**Why this approach:**
- Proven in our experiment: Claude generates excellent pptxgenjs scripts from scratch
- Maximum per-slide creative flexibility (cards vs bullets vs stat callouts)
- Generated scripts are inspectable and editable by users
- No template library to build and maintain upfront
- Common patterns can be extracted into helpers later (organic evolution)

**Alternatives considered:**
- Template Library + Content Injection — consistent but inflexible, requires building a layout library
- AI-Driven Layout Selection + Template Library — best of both but higher initial scope

### Engine Selection: Hybrid (User Chooses)

- **pptxgenjs** (default) — rich visual output, theme config for brand styling, no template file required
- **python-pptx** — uses actual .pptx template, exact corporate compliance, constrained to template layouts

### Scope: Generation Only

The skill produces a `.pptx` file and stops. Downstream workflows:
- `/deck-review` — visual QA, slide inspection
- `aippt ingest` — catalog + tags
- `aippt improve` — LLM-powered content rewriting
- `aippt analyze` — speaker notes, feedback, improvements

### Invocation: Interactive

`/create-deck` walks through options interactively:
1. Select outline (scan `outlines/` for `.md` files)
2. Choose engine (pptxgenjs or python-pptx)
3. Choose theme/template (scan `themes/` or `templates/`)

Smart defaults: auto-derive output path from outline filename, skip theme prompt if only one exists, auto-select engine if user mentions "template" or passes a `.pptx` path.

### Theme System: YAML Config

Brand identity defined in YAML files (`themes/amd.yaml`). Includes colors, fonts, logo path/position, slide dimensions, and footer settings. Portable across brands — create a new theme file for a new brand.

## Architecture

### File Structure

```
.claude/
  skills/
    create-deck/
      SKILL.md                    # Skill definition + instructions
      references/
        theme-schema.md           # Theme YAML format reference
        pptxgenjs-guide.md        # pptxgenjs pitfalls + best practices
        python-pptx-guide.md      # Template engine patterns
  commands/
    create-deck.md                # Slash command router

themes/
  amd.yaml                        # AMD corporate theme
  default.yaml                    # Minimal default theme
  assets/
    amd-logo-white.png            # Logo image(s)
```

### Workflow

```
/create-deck
  → Interactive prompts (outline, engine, theme)
  → Parse outline (extract slides, directives, frontmatter)
  → Read theme YAML (colors, fonts, logo)
  → Generate script (.js or .py) tailored to content
  → Execute script → output.pptx
  → Report results + suggest next steps
```

### Theme YAML Schema

```yaml
name: AMD Corporate
description: Black/white minimal with teal accent

colors:
  background: "000000"
  background_alt: "1A1A2E"
  surface: "16213E"           # cards, callout boxes
  text_primary: "FFFFFF"
  text_secondary: "94A3B8"
  text_body: "E2E8F0"
  accent: "00B4D8"            # primary accent
  accent_alt: "06D6A0"        # success/highlight
  warning: "E94560"           # alerts, caution

fonts:
  heading: "Trebuchet MS"
  body: "Calibri"
  mono: "Consolas"

logo:
  path: "themes/assets/amd-logo-white.png"
  position: "bottom-right"
  width_inches: 1.2

slide:
  layout: "LAYOUT_16x9"
  margin_inches: 0.5

footer:
  show: true
  text: ""                    # empty = use deck title
  show_slide_numbers: true
```

### Layout Decision Strategy

Claude analyzes each slide's content and selects the best visual treatment. No predefined layout library — each script is custom. Content signals that inform layout choice:

| Signal | Layout |
|--------|--------|
| First slide with `#` heading | Title slide (centered title + subtitle + author) |
| `#` heading with no `##` children | Section divider (dark bg, large centered text) |
| 3-4 bold lead-in bullets with descriptions | Card grid (2x2 or 3-col with accent bars + icons) |
| Content with a prominent number/stat | Stat callout (large number + supporting text) |
| Backtick code blocks or CLI commands | Code block (dark panel with mono font) |
| `LAYOUT: two_column` or `|||` separator | Two-column side-by-side |
| `LAYOUT: numbered` or sequential steps | Process flow (numbered circles + horizontal flow) |
| Standard bullet content | Icon + text rows or standard bullets (fallback) |

**Layout variety rule:** Never repeat the same layout on consecutive slides. If two slides in a row would naturally be "bullet" slides, the second one should use a different visual treatment.

**Outline directives override:** `LAYOUT:` and `IMAGE:` directives from the markdown outline take precedence over Claude's layout selection.

### Outline Compatibility

The skill reads the same markdown outline format that `aippt.py create` uses:

- YAML frontmatter (`audience`, `goal`, `tone`)
- `#` section headings → section divider slides
- `##` slide titles → content slides
- Bullet points + sub-bullets (indentation preserved)
- Bold lead-ins (`**Key —** description`)
- `LAYOUT:` directive (overrides layout choice)
- `IMAGE:` directive (embeds image, content → speaker notes)
- `|||` column separator (two-column split)
- `*Notes:*` blocks (→ speaker notes)

### Dependency Management

**pptxgenjs engine:**
- Required: `pptxgenjs` (npm global)
- Optional (for icons): `react`, `react-dom`, `react-icons`, `sharp`
- Skill checks deps before generation, prompts user to install if missing

**python-pptx engine:**
- Required: `python-pptx` (already in `requirements.txt`)
- Required: `.pptx` template file in `templates/`
- Skill detects venv Python path using the platform detection snippet from CLAUDE.md

### Output

Both engines produce:
- `.pptx` file in `output/` (named after the outline)
- Generated `.js` or `.py` script alongside it (for inspection/modification)

## Slash Command

```markdown
---
description: Create a PowerPoint deck from a markdown outline
---

Use the create-deck skill to generate a PowerPoint presentation.
Walk the user through outline selection, engine choice, and theme
configuration interactively.

If arguments are provided, treat them as the outline file path: $ARGUMENTS
```

## Out of Scope

**Handled by deck-reviewer / aippt CLI:**
- Visual QA / slide inspection
- Speaker notes generation
- Tag classification
- LLM-powered content rewriting
- Deck cataloging / ingestion

**Future work:**
- Excalidraw diagram generation within slides
- DALL-E / MCP image generation
- Reusable template library (extract common patterns from generated scripts)
- Web UI integration
- Batch generation
- Auto-extract theme from existing .pptx template

## Deliverables

| # | File | Type | Size Est. |
|---|------|------|-----------|
| 1 | `.claude/skills/create-deck/SKILL.md` | Skill definition | ~400 lines |
| 2 | `.claude/skills/create-deck/references/theme-schema.md` | Reference doc | ~60 lines |
| 3 | `.claude/skills/create-deck/references/pptxgenjs-guide.md` | Reference doc | ~150 lines |
| 4 | `.claude/skills/create-deck/references/python-pptx-guide.md` | Reference doc | ~100 lines |
| 5 | `.claude/commands/create-deck.md` | Slash command | ~10 lines |
| 6 | `themes/amd.yaml` | Theme config | ~30 lines |
| 7 | `themes/default.yaml` | Theme config | ~25 lines |
| 8 | `themes/assets/amd-logo-white.png` | Logo image | Extract from template |

## Success Criteria

1. `/create-deck` produces a valid, non-corrupted `.pptx` from any existing outline in `outlines/`
2. pptxgenjs output uses varied layouts (no two consecutive slides use the same format)
3. AMD theme produces slides with correct brand colors, fonts, and logo placement
4. python-pptx output uses the corporate template's layouts and branding
5. Generated scripts are readable and re-runnable
6. Output deck can be ingested by `aippt ingest` and reviewed by `/deck-review`
