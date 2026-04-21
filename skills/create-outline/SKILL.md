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

# Create Outline

Turn raw source material into a polished presentation outline in aippt markdown format. Accepts documents, codebases, GitHub repos, running web apps, or a freeform description, and produces a structured outline ready to hand off to `/create-deck` or `aippt create`.

**Pipeline position:**

```
Source Material → /create-outline → outline.md → /create-deck or aippt create → deck.pptx
```

This skill is the upstream entry point. It handles content analysis, structure planning, and visual asset gathering. Deck generation and deck review are handled by downstream skills.

## Quick Reference

| Task | Where to go |
|------|-------------|
| Gather source material | [Phase 1: Content Gathering](#phase-1-content-gathering) |
| Convert documents to markdown | [Step 2: Analyze Source Material](#step-2-analyze-source-material) |
| Fetch a GitHub repo | [Step 2: Analyze Source Material](#step-2-analyze-source-material) |
| Define audience, goal, tone | [Step 3: Define Presentation Context](#step-3-define-presentation-context) |
| Plan sections and layouts | [Step 4: Propose Structure](#step-4-propose-structure) |
| Generate the outline file | [Step 5: Generate Outline](#step-5-generate-outline) |
| Capture screenshots | [Phase 3: Visual Enrichment](#phase-3-visual-enrichment) |
| Add TODO placeholders for diagrams | [Step 8: Capture Screenshots](#step-8-capture-screenshots) |
| Outline format rules | [Outline Format Summary](#outline-format-summary) |
| Source type analysis patterns | Read [references/source-analysis-guide.md](references/source-analysis-guide.md) |
| Playwright capture patterns | Read [references/screenshot-capture-guide.md](references/screenshot-capture-guide.md) |
| Full outline format specification | Read [references/outline-format-reference.md](references/outline-format-reference.md) |

---

## Environment Setup

Before running any commands, locate the virtualenv Python:

```bash
if [ -f venv/bin/python ]; then
    VENV_PYTHON=venv/bin/python
elif [ -f venv/Scripts/python.exe ]; then
    VENV_PYTHON=venv/Scripts/python.exe
else
    echo "venv not found"
fi
```

All examples below use `$VENV_PYTHON`. On Linux/WSL2 that's `venv/bin/python`; on Windows it's `venv/Scripts/python.exe`. Run commands from the project root (wherever `aippt.py` lives).

---

## Phase 1: Content Gathering

### Step 1: Gather Sources

If `$ARGUMENTS` is provided, parse it as space-separated source paths/URLs and skip the gathering prompt — use those as the sources for analysis.

Otherwise, scan the current directory for likely candidates (README.md, docs/, outlines/) and present them to the user. Accept any combination of:

- Local files or directories (markdown, PDF, DOCX, PPTX, XLSX, HTML, code)
- GitHub repo URLs (e.g., `https://github.com/owner/repo`)
- Web app URLs (e.g., `http://localhost:3000`) — visual capture deferred to Phase 3
- "Let me describe what I want" — freeform description, no files needed

Multiple sources can be combined. For example: README.md + a GitHub repo + a running web app.

### Step 2: Analyze Source Material

Convert all non-markdown sources and extract the content:

```bash
# Convert any supported format (PDF, DOCX, PPTX, XLSX, HTML)
$VENV_PYTHON -m markitdown input.pdf -o /tmp/converted.md
$VENV_PYTHON -m markitdown input.docx

# Pipe for quick inspection
$VENV_PYTHON -m markitdown input.pdf | head -100
```

**For codebases:** Identify README, docs/, architecture overview, key modules, CLI commands, and public APIs. Skim source files for structure; don't read every file.

**For GitHub repos:** Use the `gh` CLI to fetch content without cloning:

```bash
# Fetch README
gh api repos/{owner}/{repo}/readme --jq '.content' | base64 -d

# List repo tree (find docs, key files)
gh api repos/{owner}/{repo}/git/trees/HEAD?recursive=1 --jq '.tree[] | select(.type=="blob") | .path'

# Fetch a specific file
gh api repos/{owner}/{repo}/contents/{path} --jq '.content' | base64 -d
```

Fall back to `git clone --depth 1` if `gh` is unavailable or the API is rate-limited.

**For URLs:** Extract text via `markitdown`. Visual capture (screenshots) is deferred to Phase 3.

After analysis, summarize the key themes, features, and concepts you found. Present the summary to the user: "Here's what I found — does this capture the key topics?" Iterate until the user confirms the source material is understood.

Read [references/source-analysis-guide.md](references/source-analysis-guide.md) for detailed patterns by source type.

---

## Phase 2: Outline Generation

### Step 3: Define Presentation Context

Ask the user about their presentation in a single conversational prompt. Cover all five points but let the user answer naturally — they can say "15 slides for engineers, technical deep-dive" and you'll extract all five.

- **Audience** — who is this for? (engineers, executives, mixed, sales, general) → goes in frontmatter
- **Goal** — what should it accomplish? (introduce, persuade, teach, update, pitch) → goes in frontmatter
- **Tone** — what style? (professional, conversational, technical, casual) → goes in frontmatter
- **Scope** — how deep? (overview, deep-dive, tutorial, demo walkthrough, pitch) → planning only, NOT frontmatter
- **Length** — how many slides? (short: 5-8, medium: 10-15, long: 16-25) → planning only, NOT frontmatter

Only audience, goal, and tone go into the YAML frontmatter. Scope and length guide structure decisions internally.

### Step 4: Propose Structure

Based on analyzed content and presentation context, propose a section and slide structure:

**Choose a heading pattern:**

- **Pattern A (`#` / `##`)** — Most common. `#` = section (first becomes title slide, subsequent become section dividers). `##` = slide title. Use for decks with 6+ slides and 2+ logical groupings.
- **Pattern B (`#` / `##` / `###`)** — Hierarchical. `#` = deck title, `##` = section heading, `###` = slide title. Use when a prominent overall title distinct from any section is needed.
- **Simple (`#` only)** — Flat. `#` = slide title directly. Use for short decks (5 or fewer slides) with no section groupings.

**Recommend `LAYOUT:` directives** based on content signals:

| Content Signal | Suggested Layout |
|---|---|
| Sequential steps, installation, process flow | `numbered` |
| Two categories, comparison, pros/cons, side-by-side | `two_column` |
| Feature list with bold lead-ins, mixed content | `bullet` (default) |
| Architecture diagram, system view, UI screenshot | `diagram` (requires `IMAGE:` — flag for Phase 3) |
| Short intro, agenda, overview, closing | `basic` |

**Flag slides that will need visuals** — mark them clearly in the proposed structure so they can be addressed in Phase 3.

Present the proposed structure as a numbered list. Iterate with the user until the structure is approved before writing the outline.

### Step 5: Generate Outline

Write the complete outline following the aippt format exactly:

- YAML frontmatter with `audience`, `goal`, `tone`
- Heading pattern chosen in Step 4
- Bold lead-ins (`**Term** —` or `**Term:**`) on feature/benefit/category lists — all or none within a slide
- `LAYOUT:` directives based on content analysis
- `|||` column separators for two-column slides; column headers where applicable (`LAYOUT: two_column | Left Header | Right Header`)
- No `IMAGE:` directives yet — visual enrichment is Phase 3
- Content density: 4-6 bullets per slide, one line per bullet (~80-100 chars)
- End with a summary, resources, or closing slide

**Saving the outline:**

```bash
mkdir -p outlines
```

Derive the filename from the primary source:
- File source: stem of the source filename (e.g., `README.md` → `readme`)
- GitHub repo: repo name (e.g., `amd/mcp-amdsmi` → `mcp-amdsmi`)
- Freeform description: short topic slug (e.g., "presentation about our new dashboard" → `new-dashboard`)

Confirm the filename with the user before saving to `outlines/{name}.md`.

Read [references/outline-format-reference.md](references/outline-format-reference.md) for the complete format specification.

### Step 6: Review Outline

Present the generated outline for user review. Offer specific revision options:

- Adjust slide content, add or remove slides
- Change structure or layout directives
- Reorder sections
- Adjust bullet density or wording

Iterate until the user approves the text content before moving to Phase 3.

---

## Phase 3: Visual Enrichment

### Step 7: Identify Visual Needs

Scan the approved outline and propose a visual plan. For each slide that would benefit from a visual asset, assess the type and source:

```
Slide  | Title                | Suggested Visual          | Source
-------|----------------------|---------------------------|------------------
4      | Dashboard Overview   | Screenshot of /dashboard  | http://localhost:3000/dashboard
7      | Architecture         | System diagram            | [TODO: Excalidraw]
9      | CLI Usage            | Terminal screenshot        | Capture CLI output
12     | Performance Results  | Chart                     | [TODO: create chart]
```

Present the table to the user. They approve which visuals to capture now vs. leave as placeholders.

### Step 8: Capture Screenshots

For each approved screenshot capture:

1. Confirm the target URL is accessible
2. Resize the browser to 1920x1080: use `browser_resize` (width: 1920, height: 1080)
3. Navigate to the target URL: use `browser_navigate`
4. Wait for content to load: use `browser_wait_for`
5. Optionally interact (dismiss modals, click tabs, expand sections) to get a clean view
6. Capture screenshot: use `browser_take_screenshot` with `type: "png"`
7. Save to `images/{outline-stem}/web-{N}-{description}.png`
8. Add `IMAGE: images/{outline-stem}/web-{N}-{description}.png` to the corresponding slide
9. Add `LAYOUT: diagram` to the same slide so the image fills the content area

For slides where visuals are deferred, do NOT add an `IMAGE:` directive or `LAYOUT: diagram` — a diagram layout without an image produces a blank gray placeholder box in the rendered deck. Instead, add a TODO comment and a speaker notes block:

```markdown
## Architecture Overview
<!-- TODO: Create system architecture diagram in Excalidraw, then add LAYOUT: diagram and IMAGE: directive -->
- Microservices communicate via event bus
- Each service owns its data store

*Notes: VISUAL PLACEHOLDER — This slide needs a system architecture diagram. Create in Excalidraw, then add LAYOUT: diagram and IMAGE: directives before generating the deck.*
```

The `<!-- TODO: -->` comment is invisible to the aippt parser but visible when editing. The `*Notes:*` block surfaces the placeholder reminder in speaker notes. The handoff summary counts these markers.

Read [references/screenshot-capture-guide.md](references/screenshot-capture-guide.md) for Playwright capture patterns.

### Step 9: Finalize & Handoff

Save the final outline with all `IMAGE:` directives added. Count `<!-- TODO:` markers in the file to report remaining placeholders.

Present the summary:

```
Outline created: outlines/{name}.md ({N} slides, {M} sections)
Screenshots saved: images/{name}/ ({K} captured)
Placeholders remaining: {P} (search for "<!-- TODO:" in the outline)

Next steps:
- /create-deck — Generate a polished deck (pptxgenjs or python-pptx)
- aippt create outlines/{name}.md template.pptx output/{name}.pptx --enhance
- Excalidraw — Create diagrams for placeholder slides (see TODO markers)
```

---

## Outline Format Summary

Quick reference for the aippt outline format. Read [references/outline-format-reference.md](references/outline-format-reference.md) for the full specification with examples.

**Frontmatter** (audience, goal, tone only):
```yaml
---
audience: engineers
goal: Explain the monitoring stack and get teams to adopt it
tone: technical
---
```

**Heading patterns:**
- Pattern A: `#` = sections, `##` = slides (most common)
- Pattern B: `#` = deck title, `##` = sections, `###` = slides (hierarchical)
- Simple: `#` = slides directly (short flat decks, 5 or fewer slides)

**Content elements:**
- `- item` = bullet (level 1)
- `  - sub-item` = sub-bullet (level 2, 2+ leading spaces)
- `1. step` = numbered item
- `**Term** — rest` or `**Term:** rest` = bold lead-in (1-4 words before separator)

**Directives** (uppercase, first occurrence wins):
- `LAYOUT: bullet` — standard bullet list (default)
- `LAYOUT: two_column` — side-by-side columns; supports `| Left Header | Right Header`
- `LAYOUT: numbered` — sequential/process flow
- `LAYOUT: basic` — simple title and content, no bullet formatting
- `LAYOUT: diagram` — image slide; requires `IMAGE:` directive
- `IMAGE: path/to/image.png` — path relative to outline file
- `|||` — column separator for two-column layouts

**Quality rules:**
- 4-6 bullets per slide (max 6 top-level)
- One line per bullet (~80-100 chars)
- Bold lead-ins: all or none within a slide, consistent separator style
- Two-column: always use `|||`, aim for balanced content (3-4 items per side)
- Do not use bold lead-ins on numbered/sequential content
- Do not add `LAYOUT: diagram` without a valid `IMAGE:` path

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `markitdown` not found | Use `$VENV_PYTHON -m markitdown` (not bare `markitdown`) |
| `gh` CLI not authenticated | Run `gh auth login` or fall back to `git clone --depth 1` |
| GitHub API rate limited | Fall back to `git clone --depth 1` |
| Playwright not available | Skip Phase 3 screenshot capture; leave all visuals as TODO placeholders |
| Target URL not accessible | Mark that screenshot as a TODO placeholder, continue with others |
| Empty markitdown output on JS-rendered page | Use Playwright to render the page first, then extract from snapshot |
| No source material found | Ask user to describe topic freeform; generate outline from the conversation |
| Generated outline too long | Reduce scope (overview vs. deep-dive) or split into multiple outlines |
| Screenshots not 16:9 | Ensure `browser_resize` to 1920x1080 before capturing |
| `diagram` layout produces gray box | Only add `LAYOUT: diagram` when `IMAGE:` path is ready; use `bullet` as interim |
