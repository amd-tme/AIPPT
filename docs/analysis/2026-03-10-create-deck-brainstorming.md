# Create-Deck Skill: Brainstorming Notes

**Date:** 2026-03-10
**Outcome:** PRD written at `docs/plans/2026-03-10-create-deck-skill.md`

## Context: pptxgenjs vs python-pptx Experiment

We ran an experiment generating a deck from `outlines/Q1/Q126 - AMD GPU Operator and Kubernetes.md` using two approaches:

### Approach 1: pptxgenjs (from scratch)

- Generated `output/gpu-operator-deck.js` → `output/AMD-GPU-Operator.pptx`
- **18 slides** with custom visual layouts: card grids, stat callouts, code blocks, process flows, icon rows
- AMD-inspired color palette (dark charcoal + teal accent), Trebuchet MS / Calibri fonts
- Used `react-icons` + `sharp` for inline icon rendering
- **Result:** Visually impressive, varied layouts, rich design. PowerPoint initially reported corruption (likely shadow object mutation pitfall) but opened after repair and looked good.
- **Key pitfall:** pptxgenjs mutates option objects in-place. Must use factory functions for shadows, not shared objects.

### Approach 2: python-pptx (corporate template)

- Generated `output/build-gpu-operator.py` → `output/AMD-GPU-Operator-v2.pptx`
- **21 slides** using `templates/corp.pptx` layouts (Title, Content, Two Content, Divider, Code, Three-column, Closing)
- Perfect corporate branding (AMD logo, footer, colors)
- **Result:** Clean, professional, brand-compliant. Content top-loaded on many slides (bottom 40-50% empty — template spacing issue). No corruption.

### Key Findings

| Aspect | pptxgenjs | python-pptx |
|--------|-----------|-------------|
| Visual richness | Excellent (cards, icons, shadows) | Limited (template placeholders) |
| Brand compliance | Manual (must recreate) | Perfect (uses actual template) |
| File stability | Fragile (shadow mutation bug) | Robust |
| Layout flexibility | Total freedom | Constrained |
| Best for | Creative, visually rich decks | Strict brand requirements |

### Template Analysis: `templates/corp.pptx`

- 13.33" × 7.50" (widescreen)
- 31 slide layouts available
- Key layouts used: Title (0), Content (3), Two Content (5), Three-column (17), Divider (26), Code (28), Closing (30)
- AMD template uses OBJECT (type 7) placeholders, not BODY (type 2)
- Two-column body placeholders are idx 12 and 13
- Simple black/white design with AMD logo — feasible to recreate in pptxgenjs

## Design Decisions

### Q: Primary generation engine?
**A: Hybrid (user chooses).** Both engines available. pptxgenjs is default for visual richness; python-pptx for strict brand compliance.

### Q: Full lifecycle or generation only?
**A: Generation only.** QA, notes, tags, and refinement handled by deck-reviewer and aippt CLI. Clean separation of concerns.

### Q: How to define corporate styling for pptxgenjs?
**A: YAML theme config.** Portable across brands. Stored in `themes/` directory.

### Q: Invocation style?
**A: Interactive.** `/create-deck` walks through options. Smart defaults minimize prompts.

### Q: Architecture approach?
**A: Monolithic Script Generator.** Claude generates a complete, tailored script per invocation. No reusable template library — maximum creative flexibility. Can extract common patterns later.

**Alternatives rejected:**
- **Template Library + Content Injection** — consistent but inflexible, requires building a layout library upfront
- **AI-Driven Layout Selection + Template Library** — best of both but higher initial scope. Good evolution target.

## User Feedback

> "This deck is nice and clean - looks like something I would consider a clean first attempt (and would take me quite a bit of time to create from scratch!) It's not perfect but very well done and exactly the proof of concept I was looking for."

> "This deck could be imported into AIPPT to generate slide notes and tags, which is a good workflow."

> "If the hybrid workflow doesn't work, I am interested in finding a way to build the AMD corporate template from scratch in pptxgenjs - it's a very simple template, mostly black and white."

## Visual Companion Screenshots

Brainstorming visual companion files saved in `.superpowers/brainstorm/` (architecture overview, interactive flow, theme/layout strategy, compatibility matrix, skill structure).
