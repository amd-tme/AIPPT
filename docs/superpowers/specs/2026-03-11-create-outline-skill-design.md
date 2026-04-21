# Create-Outline Skill Design

**Date:** 2026-03-11
**Status:** Draft
**Skill location:** `.claude/skills/create-outline/`

## Purpose

A Claude Code skill that takes raw source material — documents, codebases, GitHub repos, running web apps — and produces a well-formatted markdown outline ready for deck generation via `/create-deck` or `aippt create`.

### Position in the Pipeline

```
Source Material → /create-outline → outline.md → /create-deck or aippt create → deck.pptx
```

`create-outline` is the **upstream** entry point. It handles content analysis, structure planning, and visual asset gathering. It outputs an outline that conforms exactly to the aippt outline format (documented in README.md).

## Environment Setup

Before running any commands, locate the virtualenv Python:

```bash
if [ -f venv/bin/python ]; then
    VENV_PYTHON=venv/bin/python
elif [ -f venv/Scripts/python.exe ]; then
    VENV_PYTHON=venv/Scripts/python.exe
else
    echo "venv not found -- create one or check the path"
fi
```

All examples below use `$VENV_PYTHON`. On Linux/WSL2 that's `venv/bin/python`; on Windows it's `venv/Scripts/python.exe`.

## Input Sources

The skill accepts any combination of:

| Source Type | How It's Processed |
|---|---|
| Local markdown files | Read directly |
| Local documents (PDF, DOCX, XLSX, HTML) | Convert via `markitdown` |
| Local codebase / directory | Scan for README, docs/, key source files; convert via `markitdown` where needed |
| GitHub repo URL | Fetch README, docs, tree via `gh` CLI; fall back to `git clone --depth 1` |
| Web page URL | Extract text via `markitdown` (for content); Playwright screenshots captured separately in visual pass |
| Existing outline (for refinement) | Read and restructure |

### markitdown as Universal Converter

`markitdown` is already installed in the venv and handles PDF, DOCX, PPTX, XLSX, HTML, and more. Any non-markdown file gets converted to markdown first, producing a uniform intermediate representation for content analysis.

```bash
# Convert any supported format
$VENV_PYTHON -m markitdown input.pdf -o /tmp/converted.md
$VENV_PYTHON -m markitdown input.docx -o /tmp/converted.md

# Pipe for inline processing
$VENV_PYTHON -m markitdown input.pdf
```

### GitHub Repos

For GitHub URLs, prefer `gh` CLI over cloning:

```bash
# Fetch README content
gh api repos/{owner}/{repo}/readme --jq '.content' | base64 -d

# List repo tree (find docs, key files)
gh api repos/{owner}/{repo}/git/trees/HEAD?recursive=1 --jq '.tree[] | select(.type=="blob") | .path'

# Fetch specific file content
gh api repos/{owner}/{repo}/contents/{path} --jq '.content' | base64 -d
```

Fall back to `git clone --depth 1` for complex repos or when `gh` is unavailable.

## Interactive Flow

### Phase 1: Content Gathering

**Step 1: Gather Sources**

Prompt the user for what they're working with. Scan the current directory for likely candidates (README.md, docs/, outlines/) and offer them. Accept multiple sources.

If `$ARGUMENTS` is provided, parse it as space-separated source paths/URLs and skip the gathering prompt.

Otherwise, present the user with options:
- Local files/directories (let user specify paths)
- GitHub repo URL
- Web app URL (for later screenshot capture)
- Let me describe what I want (freeform)

**Step 2: Analyze Source Material**

- Convert all non-markdown sources via `markitdown`
- For codebases: identify README, docs/, architecture, key modules, CLI commands
- For GitHub repos: fetch and analyze README, docs, release notes
- For URLs: extract text content via `markitdown` (visual capture deferred to Phase 3)
- Summarize findings: key themes, features, concepts identified
- Present the summary to the user for validation ("Here's what I found — does this capture the key topics?")

### Phase 2: Outline Generation

**Step 3: Define Presentation Context**

Ask the user about their presentation in a single conversational prompt. Cover:
- **Audience** — who is this for? (engineers, executives, mixed, sales, general)
- **Goal** — what should it accomplish? (introduce, persuade, teach, update, pitch)
- **Tone** — what style? (professional, conversational, technical, casual)

These three map to YAML frontmatter fields (`audience`, `goal`, `tone`).

Additionally, gather two planning constraints (used to guide outline structure but NOT written to frontmatter):
- **Scope** — how deep? (overview, deep-dive, tutorial, demo walkthrough, pitch)
- **Length** — how many slides? (short: 5-8, medium: 10-15, long: 16-25)

Present all five as a single prompt. The user can answer conversationally ("it's for engineers, about 15 slides, technical deep-dive") or answer each individually.

**Step 4: Propose Structure**

Based on analyzed content + presentation context, propose a section/slide outline:
- Choose the heading pattern (Pattern A, Pattern B, or Simple — see Structure section below)
- Recommend `LAYOUT:` directives where content signals a clear layout type (see decision table below)
- Flag slides that will likely need visuals (deferred to Phase 3)
- Present the proposed structure as a numbered list for easy reference
- Iterate with the user until the structure is approved

Layout signal detection (same as create-deck):

| Content Signal | Suggested Layout |
|---|---|
| Sequential steps, installation, process | `numbered` |
| Two categories, comparison, pros/cons | `two_column` |
| Feature list with bold lead-ins | `bullet` (default) |
| Architecture, system diagram, UI view | `diagram` (needs IMAGE:) |
| Short intro, agenda, overview | `basic` |

**Step 5: Generate Outline**

Write the complete outline following the aippt format exactly:

- YAML frontmatter (`audience`, `goal`, `tone`)
- Hierarchical mode (`#` sections, `##` slides) for decks > 5-6 slides; simple mode (`#` slides) for shorter decks
- Bold lead-ins (`**Term** —` or `**Term:**`) on feature/benefit/category lists
- `LAYOUT:` directives based on content analysis
- `|||` column separators for two-column slides with balanced content
- Column headers where applicable (`LAYOUT: two_column | Header1 | Header2`)
- No `IMAGE:` directives yet — visual enrichment happens in Phase 3
- Content density: 4-6 bullets per slide, one line per bullet (~80-100 chars)
- Create the `outlines/` directory if it does not exist (`mkdir -p outlines`)
- Save to `outlines/{name}.md`

Derive `{name}` from the primary source: the source filename stem (e.g., `README.md` → `readme`), the GitHub repo name (e.g., `amd/mcp-amdsmi` → `mcp-amdsmi`), or a short topic slug generated from the user's description (e.g., "presentation about our new dashboard" → `new-dashboard`). Confirm with the user before saving.

**Step 6: Review Outline**

Present the generated outline for user review. Offer specific revision options:
- Adjust slide content, add/remove slides
- Change structure or layout directives
- Reorder sections
- Iterate until the user approves the text content

### Phase 3: Visual Enrichment

**Step 7: Identify Visual Needs**

Scan the approved outline and propose a visual plan. For each slide, assess whether it would benefit from a visual asset:

| Visual Type | When to Suggest | Action |
|---|---|---|
| App screenshot | Slide about UI, dashboard, user flow | Capture via Playwright |
| Web page screenshot | Slide referencing external docs, tools | Capture via Playwright |
| Architecture diagram | Slide about system design, data flow | Placeholder → Excalidraw later |
| Code screenshot | Slide showing CLI output, API response | Capture via Playwright or code panel |
| Logo/brand image | Title slide, about-us | User provides or placeholder |
| Chart/graph | Data-driven slides | Placeholder → create separately |

Present the visual plan as a table:

```
Slide  | Title                | Suggested Visual          | Source
-------|----------------------|---------------------------|------------------
4      | Dashboard Overview   | Screenshot of /dashboard  | http://localhost:3000/dashboard
7      | Architecture         | System diagram            | [placeholder: Excalidraw]
9      | CLI Usage            | Terminal screenshot        | Capture CLI output
12     | Performance Results  | Chart                     | [placeholder: create chart]
```

The user approves which visuals to capture now vs. leave as placeholders.

**Step 8: Capture Screenshots**

For approved screenshot captures:

1. Confirm the target URL is accessible (curl or Playwright navigate)
2. Resize browser to 1920x1080 (`browser_resize`)
3. Navigate to the target URL (`browser_navigate`)
4. Wait for content to load (`browser_wait_for`)
5. Optionally interact (click tabs, expand sections) per the visual plan
6. Capture screenshot (`browser_take_screenshot`, type: png)
7. Save to `images/{outline-stem}/web-{N}-{description}.png` (the `web-` prefix distinguishes Playwright captures from auto-exported slide images which use `Slide{N}.PNG`)
8. Add `IMAGE:` directive to the corresponding slide in the outline
9. Add `LAYOUT: diagram` if the image should fill the content area

For slides where visuals are deferred, do NOT use an `IMAGE:` directive (it would silently fail in aippt/create-deck). Instead, add a TODO comment and a speaker notes block to flag the need:

```markdown
## Architecture Overview
<!-- TODO: Create system architecture diagram in Excalidraw, then add LAYOUT: diagram and IMAGE: directive -->
- Microservices communicate via event bus
- Each service owns its data store

*Notes: VISUAL PLACEHOLDER — This slide needs a system architecture diagram. Create in Excalidraw, then add LAYOUT: diagram and IMAGE: directives before generating the deck.*
```

Note: Do NOT add `LAYOUT: diagram` until the `IMAGE:` path is ready. A `diagram` layout without an image produces a blank gray placeholder box in the rendered deck. Use the default `bullet` layout as the interim — the slide will render with bullets, and the TODO marker reminds the author to switch to `diagram` + `IMAGE:` when the visual is available.

This approach:
- Does not produce invalid `IMAGE:` directives that silently fail downstream
- The `<!-- TODO: -->` comment is visible when editing the outline but invisible to the parser
- The `*Notes:*` block surfaces the placeholder in speaker notes as a visible reminder
- The handoff summary (Step 9) counts these TODO markers and reports them as "placeholders remaining"

**Step 9: Finalize & Handoff**

Save the final outline with all `IMAGE:` directives. Count `<!-- TODO:` markers to report remaining placeholders. Present summary:

```
Outline created: outlines/{name}.md ({N} slides, {M} sections)
Screenshots saved: images/{name}/ ({K} captured)
Placeholders remaining: {P} (search for "<!-- TODO:" in the outline)

Next steps:
- /create-deck — Generate a polished deck (pptxgenjs or python-pptx)
- aippt create outlines/{name}.md template.pptx output/{name}.pptx --enhance
- Excalidraw — Create diagrams for placeholder slides (see TODO markers)
```

## Outline Format Reference

The generated outline must conform exactly to the format documented in README.md. Key rules:

### Frontmatter
```yaml
---
audience: engineers
goal: Explain the monitoring stack and get teams to adopt it
tone: technical
---
```

### Structure — Two Heading Patterns

The skill supports two heading patterns. Choose based on deck complexity:

**Pattern A: `#` / `##` (most common)**
- `#` = section heading (first `#` becomes title slide; subsequent `#` become section dividers)
- `##` = slide title
- Everything under a `##` until the next heading = slide content
- Use for most decks with logical section groupings

**Pattern B: `#` / `##` / `###` (hierarchical)**
- `#` = deck title (becomes title slide)
- `##` = section heading (becomes section divider)
- `###` = slide title
- Use when the deck needs a distinct overall title plus deep section nesting

**Simple mode** (short decks, no sections):
- `#` = slide titles directly, no `##` headings
- Use for decks with 5 or fewer slides that don't need section groupings

**How to choose:**
- If the deck has 6+ slides with 2+ logical groupings → Pattern A
- If the deck needs a prominent overall title distinct from any section → Pattern B
- If the deck is short and flat → Simple mode

The downstream `/create-deck` skill detects the pattern by checking whether `###` headings are present. Pattern A is the default; only use Pattern B when the hierarchical depth is genuinely needed.

### Content Formatting
- `- item` = bullet (level 1)
- `  - sub-item` = sub-bullet (level 2, 2+ leading spaces)
- `1. step` = numbered item
- `**bold text**` = converted to UPPERCASE in plain text
- `**Term** — rest` or `**Term:** rest` = bold lead-in (1-4 words before separator)

### Directives
- `LAYOUT: <type>` — one of: `bullet`, `two_column`, `numbered`, `basic`, `diagram`
- `IMAGE: <path>` — image path relative to outline file
- `|||` — column separator for two-column layouts
- Column headers: `LAYOUT: two_column | Left Header | Right Header`

### Quality Rules
- 4-6 bullets per slide (max 6 top-level)
- One line per bullet (~80-100 chars)
- Bold lead-ins: all or none within a slide, consistent separator
- Two-column: always use `|||`, aim for balanced content (3-4 per side)
- Don't use bold lead-ins on numbered/sequential content
- End with a summary or resources slide

## Skill File Structure

```
.claude/skills/create-outline/
  SKILL.md                           # Main skill definition
  references/
    outline-format-reference.md      # Extracted outline format spec (from README.md)
    source-analysis-guide.md         # How to analyze different source types
    screenshot-capture-guide.md      # Playwright patterns for slide-quality screenshots
```

### SKILL.md Frontmatter

```yaml
---
name: create-outline
description: >
  Create a presentation outline from raw source material — documents, codebases, GitHub repos,
  or running web apps. Analyzes content, generates a structured markdown outline in aippt format,
  and captures screenshots via Playwright for visual slides. Use when the user wants to turn
  source material (code, docs, repos, URLs) into a presentation outline. Trigger on "create
  outline from", "outline from this repo", "presentation about this project", "turn this into
  slides", or "outline from docs". Does NOT trigger for reviewing existing outlines or decks
  (use deck-reviewer) or generating decks from existing outlines (use create-deck).
---
```

### Reference Files

**outline-format-reference.md** — The complete outline format specification extracted from README.md (frontmatter, structure modes, content formatting, directives, writing guidelines, and the full example). This is the authoritative format reference the skill uses when generating outlines. Extracted rather than linked so the skill is self-contained.

**source-analysis-guide.md** — Patterns for analyzing different source types:
- Codebase scanning (what files matter, how to identify architecture)
- GitHub repo analysis (which API endpoints to use, what to look for)
- Document conversion (markitdown usage, handling conversion artifacts)
- URL content extraction (markitdown for text, when to defer to Playwright)

**screenshot-capture-guide.md** — Playwright patterns for capturing slide-quality screenshots. Extract and consolidate the screenshot capture guidance from `deck-reviewer/SKILL.md` (Screenshot Capture section, lines 182-219) to avoid divergence. Cover:
- Browser sizing (1920x1080 for 16:9 slides)
- Navigation and wait strategies
- Element-specific captures vs. full-page
- Image naming conventions (`web-{N}-{description}.png` for Playwright captures)
- File format guidance (PNG for UI/diagrams, JPEG for photos)
- Tips for capturing clean screenshots (dismiss modals, hide dev tools, etc.)

## Non-Goals

- **Does not generate the deck.** That's create-deck's and aippt's job.
- **Does not create diagrams.** Flags them as placeholders for Excalidraw.
- **Does not enhance or analyze existing decks.** That's deck-reviewer's job.
- **Does not edit outlines post-generation.** The user can edit manually or re-run the skill.

## Dependencies

- `markitdown` — installed in the venv (for document conversion)
- `gh` CLI — for GitHub repo analysis (optional; falls back to git clone)
- Playwright MCP server — for screenshot capture (optional; skill works without it, just skips captures)
- Excalidraw MCP server — referenced for diagram placeholders but not directly used

## Error Handling

- **markitdown fails on a file** — warn and skip that file, continue with others
- **GitHub API rate limited** — fall back to git clone --depth 1
- **Playwright not available** — skip screenshot capture phase, leave all visuals as placeholders
- **Target URL not accessible** — mark that screenshot as a placeholder, continue with others
- **No source material found** — ask the user to describe the topic freeform, generate outline from the conversation
