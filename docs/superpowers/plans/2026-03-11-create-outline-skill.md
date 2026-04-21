# Create-Outline Skill Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Claude Code skill that generates aippt-format presentation outlines from source material (docs, codebases, GitHub repos, web apps) with integrated Playwright screenshot capture.

**Architecture:** Four markdown files — one main SKILL.md and three reference docs — plus a slash command entry point and a CLAUDE.md update. No Python code; this is pure skill authoring. The skill follows the same patterns as the existing `create-deck` and `deck-reviewer` skills.

**Tech Stack:** Claude Code skills (markdown), `markitdown` (venv), `gh` CLI, Playwright MCP server

**Spec:** `docs/superpowers/specs/2026-03-11-create-outline-skill-design.md`

---

## Chunk 1: Reference Files

All commands run from the project root: `/home/matt/git/shamsway/aippt`

These are the supporting documents that the SKILL.md will reference. They must exist before SKILL.md since the skill reads them at runtime.

### Task 1: Create directory structure

**Files:**
- Create: `.claude/skills/create-outline/references/` (directory)

- [ ] **Step 1: Create the skill directory tree**

```bash
mkdir -p .claude/skills/create-outline/references
```

- [ ] **Step 2: Verify structure**

```bash
ls -la .claude/skills/create-outline/references/
```

Expected: empty `references/` directory exists.

Note: `.claude/` is gitignored — must use `git add -f` for all skill files. No commit needed here — the first real file (Task 2) will create the directory implicitly.

---

### Task 2: Write outline-format-reference.md

**Files:**
- Create: `.claude/skills/create-outline/references/outline-format-reference.md`
- Source: `README.md` lines 222-493 (the "Outline Format" section)

This file is an extraction of the outline format specification from README.md. It must be self-contained so the skill doesn't depend on README.md at runtime. Additionally, it must include the Pattern B (`#`/`##`/`###`) heading structure documented in the create-deck skill but absent from README.md.

- [ ] **Step 1: Extract outline format from README.md**

Copy the entire "Outline Format" section from README.md — starts at the `## Outline Format` heading and ends before the `## Dependencies` heading. Preserve all content exactly: frontmatter, structure modes, content formatting, bold lead-ins, directives (LAYOUT, IMAGE), writing guidelines, and the complete example.

- [ ] **Step 2: Add Pattern B heading documentation**

After the "Structure modes" section (which covers Simple mode and Hierarchical mode from README), add a new subsection documenting Pattern B. The content below is sourced from the "Outline Format Reference" section of create-deck SKILL.md (search for "Pattern B" in that file). Add:

```markdown
### Pattern B: Three-level headings (`#` / `##` / `###`)

When a deck needs a prominent overall title distinct from section headings, use three heading levels:

- `#` = deck title (becomes title slide)
- `##` = section heading (becomes section divider)
- `###` = slide title

Use Pattern B when the deck has a distinct overall title AND deep section nesting. The downstream
`/create-deck` skill detects Pattern B by checking whether `###` headings are present.

Most outlines should use Pattern A (`#`/`##`). Only use Pattern B when the hierarchical depth is
genuinely needed.
```

- [ ] **Step 3: Add a heading at the top with usage context**

```markdown
# Outline Format Reference

This is the authoritative format specification for aippt markdown outlines. Generated outlines
must conform exactly to this format. Extracted from README.md with additions from the create-deck
skill for Pattern B headings.

---
```

- [ ] **Step 4: Verify the file**

Read the file and confirm it includes: frontmatter spec, both structure modes (Simple + Hierarchical), Pattern B documentation, content formatting table, bold lead-in guidelines, all directive documentation (LAYOUT types, numbered, two_column, IMAGE), writing guidelines, and the complete example outline.

- [ ] **Step 5: Commit**

```bash
git add -f .claude/skills/create-outline/references/outline-format-reference.md
git commit -m "docs: add outline format reference for create-outline skill"
```

---

### Task 3: Write source-analysis-guide.md

**Files:**
- Create: `.claude/skills/create-outline/references/source-analysis-guide.md`

This reference covers how to analyze each type of source material to extract content for an outline. It tells the agent what to look for and how to process each source type.

- [ ] **Step 1: Write the source analysis guide**

The file should cover four source types with specific, actionable guidance:

**1. Codebase / Local Directory Analysis**
- Which files to prioritize: README.md, docs/, CHANGELOG, architecture docs, main entry points
- How to identify key modules: look for `__init__.py`, `main.py`, CLI entry points, API routes
- How to detect architecture: directory structure patterns (MVC, microservices, monolith)
- What to extract: project purpose, key features, installation steps, configuration, API surface
- Skip: test files, vendor/node_modules, generated files, binary assets

**2. GitHub Repo Analysis**
- `gh` CLI commands for fetching content:
  ```bash
  # Fetch README
  gh api repos/{owner}/{repo}/readme --jq '.content' | base64 -d

  # List repo tree
  gh api repos/{owner}/{repo}/git/trees/HEAD?recursive=1 --jq '.tree[] | select(.type=="blob") | .path'

  # Fetch specific file
  gh api repos/{owner}/{repo}/contents/{path} --jq '.content' | base64 -d

  # Get repo metadata
  gh repo view {owner}/{repo} --json name,description,url,languages,topics

  # Get latest release
  gh release view --repo {owner}/{repo} --json tagName,name,body 2>/dev/null
  ```
- Fallback: `git clone --depth 1 {url} /tmp/{repo-name}` if `gh` unavailable
- What to fetch: README, docs/, CONTRIBUTING, key source files from tree listing

**3. Document Conversion (markitdown)**
- Supported formats: PDF, DOCX, XLSX, PPTX, HTML, RTF, CSV, JSON, XML, images (OCR)
- Command pattern:
  ```bash
  $VENV_PYTHON -m markitdown input.pdf -o /tmp/converted.md
  $VENV_PYTHON -m markitdown input.docx
  ```
- Handling conversion artifacts: strip excessive whitespace, normalize heading levels, remove page break markers
- For multi-file inputs: convert each file, then merge key themes across all converted content

**4. Web Page Content Extraction**
- Use `markitdown` for text extraction from URLs (it handles HTML):
  ```bash
  $VENV_PYTHON -m markitdown https://example.com/docs
  ```
- For JavaScript-heavy pages where markitdown gets empty content, use Playwright to render first, then extract text from the snapshot
- Distinguish content extraction (text, done here) from visual capture (screenshots, done in Phase 3)

- [ ] **Step 2: Verify the file**

Read and confirm all four source types are covered with specific commands and patterns.

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/create-outline/references/source-analysis-guide.md
git commit -m "docs: add source analysis guide for create-outline skill"
```

---

### Task 4: Write screenshot-capture-guide.md

**Files:**
- Create: `.claude/skills/create-outline/references/screenshot-capture-guide.md`
- Source: `.claude/skills/deck-reviewer/SKILL.md` lines 180-219 (Screenshot Capture section)

This reference consolidates screenshot capture guidance from the deck-reviewer skill and extends it with naming conventions specific to create-outline.

- [ ] **Step 1: Write the screenshot capture guide**

Use the Screenshot Capture section from deck-reviewer/SKILL.md (the "Screenshot Capture" heading through "Tips for Good Screenshots") as the starting point for Playwright mechanics, then extend significantly with the following additional sections:

**Browser Setup**
- Resize to 1920x1080 before capturing: `browser_resize` with width 1920, height 1080
- This produces 16:9 images that match slide dimensions
- For element-specific captures, use the `ref` parameter to crop to just the relevant area

**Capture Workflow**
```
1. Confirm URL is accessible (navigate, check for errors)
2. Resize browser to 1920x1080
3. Navigate to target URL
4. Wait for content to load (browser_wait_for with key text)
5. Dismiss modals/welcome screens if present (Escape key or click dismiss)
6. Hide dev tools, cookie banners, or other overlays
7. Optionally interact (click tabs, expand sections, scroll to content)
8. Capture screenshot (browser_take_screenshot, type: png)
9. Save to images/{outline-stem}/ directory
```

**Naming Convention**
- Pattern: `web-{N}-{description}.png` where N is the slide number and description is a short slug
- Examples: `web-04-dashboard-overview.png`, `web-07-api-docs.png`
- The `web-` prefix distinguishes Playwright captures from auto-exported slide images (which use `Slide{N}.PNG`)

**File Format Guidance**
- PNG: UI screenshots, diagrams, text-heavy content (lossless, sharp edges)
- JPEG: photographs, complex images with gradients (smaller file size)
- Always use `type: "png"` for app screenshots

**Tips for Clean Screenshots**
- Dismiss cookie consent banners before capturing
- Close browser dev tools
- Expand collapsed sections if they contain key content
- Use a clean browser profile (no extensions, bookmarks bar)
- For dark-themed apps, verify contrast will work on slide backgrounds
- Consider taking both light and dark mode screenshots if the app supports it

- [ ] **Step 2: Verify the file**

Read and confirm it covers browser setup, capture workflow, naming conventions, format guidance, and tips.

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/create-outline/references/screenshot-capture-guide.md
git commit -m "docs: add screenshot capture guide for create-outline skill"
```

---

## Chunk 2: SKILL.md and Integration

### Task 5: Write SKILL.md

**Files:**
- Create: `.claude/skills/create-outline/SKILL.md`
- Reference: `docs/superpowers/specs/2026-03-11-create-outline-skill-design.md` (the full spec)
- Pattern: `.claude/skills/create-deck/SKILL.md` (for structure and style)

This is the main skill definition. It follows the same pattern as create-deck/SKILL.md: YAML frontmatter, then structured sections covering the interactive flow.

- [ ] **Step 1: Write the SKILL.md frontmatter**

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

- [ ] **Step 2: Write the skill body**

The body must cover these sections in order, following the spec. Each section corresponds to a phase/step from the design spec:

**1. Quick Reference** — Table mapping tasks to sections (same pattern as deck-reviewer)

**2. Environment Setup** — Cross-platform venv detection block (same as create-deck/deck-reviewer)

**3. Phase 1: Content Gathering**
- Step 1: Gather Sources — check for `$ARGUMENTS`, scan directory for candidates, present options
- Step 2: Analyze Source Material — markitdown conversion, codebase scanning, GitHub API, summarize findings
- Reference: "Read [references/source-analysis-guide.md](references/source-analysis-guide.md) for detailed patterns"

**4. Phase 2: Outline Generation**
- Step 3: Define Presentation Context — single prompt for audience/goal/tone + scope/length as planning constraints
- Step 4: Propose Structure — heading pattern choice (A/B/Simple), section/slide layout, LAYOUT directive recommendations
- Step 5: Generate Outline — full format spec adherence, save to `outlines/{name}.md`
- Step 6: Review Outline — present for user review, iterate
- Reference: "Read [references/outline-format-reference.md](references/outline-format-reference.md) for the complete format specification"

**5. Phase 3: Visual Enrichment**
- Step 7: Identify Visual Needs — scan outline, propose visual plan table
- Step 8: Capture Screenshots — Playwright workflow, `web-{N}-{description}.png` naming, TODO placeholders for deferred visuals
- Step 9: Finalize & Handoff — summary with slide count, screenshots captured, placeholders remaining
- Reference: "Read [references/screenshot-capture-guide.md](references/screenshot-capture-guide.md) for Playwright capture patterns"

**6. Outline Format Summary** — Condensed format rules (frontmatter, heading patterns, content formatting, directives, quality rules). Point to the full reference for details.

**7. Troubleshooting** — Table of common problems and solutions (same pattern as create-deck/deck-reviewer)

Key implementation details for the SKILL.md body:

- The `$ARGUMENTS` handling must match create-deck's pattern: "If `$ARGUMENTS` is provided, parse it as space-separated source paths/URLs and skip the gathering prompt."
- The environment setup must be the exact same cross-platform venv detection block used in both sibling skills.
- The visual plan table format from the spec (Slide | Title | Suggested Visual | Source) must be included verbatim.
- The TODO placeholder pattern must use `<!-- TODO: -->` comments + `*Notes:*` blocks, NOT invalid `IMAGE:` directives.
- The handoff message must reference both `/create-deck` and `aippt create` as next steps.
- Section references use relative markdown links: `[references/name.md](references/name.md)`.

- [ ] **Step 3: Verify the file**

Read SKILL.md and check:
1. Frontmatter has `name` and `description`
2. All three phases are present with all steps
3. Reference links point to files that exist in `references/`
4. Environment setup matches create-deck pattern
5. `$ARGUMENTS` handling is present
6. TODO placeholder pattern is correct (no invalid `IMAGE:` directives)
7. Handoff message includes next steps

- [ ] **Step 4: Commit**

```bash
git add -f .claude/skills/create-outline/SKILL.md
git commit -m "feat: add create-outline skill definition"
```

---

### Task 6: Create slash command entry point

**Files:**
- Create: `.claude/commands/create-outline.md`
- Pattern: `.claude/commands/create-deck.md`

The slash command is the entry point that routes `/create-outline` to the skill.

- [ ] **Step 1: Write the command file**

Follow the same format as `.claude/commands/create-deck.md`: frontmatter with `description`, then a short prose block that names the skill, then the `$ARGUMENTS` line.

```markdown
---
description: Create a presentation outline from source material (docs, code, repos, URLs)
---

Use the create-outline skill to generate a presentation outline from source material.
Walk the user through source gathering, outline generation, and screenshot capture.

If arguments are provided, treat them as source paths or URLs: $ARGUMENTS
```

- [ ] **Step 2: Verify the file**

```bash
cat .claude/commands/create-outline.md
```

Confirm it has frontmatter with `description` and references `$ARGUMENTS`.

- [ ] **Step 3: Commit**

```bash
git add -f .claude/commands/create-outline.md
git commit -m "feat: add /create-outline slash command"
```

---

### Task 7: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` — add `/create-outline` to the Skills / Slash Commands section

- [ ] **Step 1: Add the new skill to CLAUDE.md**

In the "Skills / Slash Commands" section, insert the new line immediately before the line `- \`/create-deck\``:

```markdown
- `/create-outline` — Generate a presentation outline from source material (docs, code, repos, URLs)
```

This puts the pipeline in logical order: create-outline → create-deck → deck-review.

- [ ] **Step 2: Verify the change**

```bash
grep -n "create-outline" CLAUDE.md
```

Expected: the new line appears in the Skills / Slash Commands section.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add create-outline skill to CLAUDE.md"
```

---

### Task 8: Validate the skill end-to-end

**Files:** None (validation only)

- [ ] **Step 1: Verify all skill files exist**

```bash
ls -la .claude/skills/create-outline/SKILL.md
ls -la .claude/skills/create-outline/references/outline-format-reference.md
ls -la .claude/skills/create-outline/references/source-analysis-guide.md
ls -la .claude/skills/create-outline/references/screenshot-capture-guide.md
ls -la .claude/commands/create-outline.md
```

All five files must exist.

- [ ] **Step 2: Verify file sizes are reasonable**

```bash
wc -l .claude/skills/create-outline/SKILL.md
wc -l .claude/skills/create-outline/references/*.md
wc -l .claude/commands/create-outline.md
```

Expected sizes:
- SKILL.md: 200-400 lines (comparable to create-deck's 308 lines and deck-reviewer's 417 lines)
- outline-format-reference.md: 250-350 lines (README excerpt ~270 lines + Pattern B addition)
- source-analysis-guide.md: 80-150 lines
- screenshot-capture-guide.md: 60-120 lines
- create-outline.md (command): 8-12 lines

- [ ] **Step 3: Verify SKILL.md references resolve**

```bash
# Check that all referenced files exist
grep -oP 'references/[a-z-]+\.md' .claude/skills/create-outline/SKILL.md | sort -u | while read f; do
  if [ -f ".claude/skills/create-outline/$f" ]; then
    echo "OK: $f"
  else
    echo "MISSING: $f"
  fi
done
```

Expected: all references show "OK".

- [ ] **Step 4: Verify CLAUDE.md has all three skills**

```bash
grep -n "create-outline\|create-deck\|deck-review" CLAUDE.md
```

Expected: all three slash commands listed in the Skills section.

- [ ] **Step 5: Verify SKILL.md frontmatter is valid**

```bash
head -15 .claude/skills/create-outline/SKILL.md
```

Confirm the first line is `---`, the frontmatter contains `name: create-outline` and a multi-line `description:`, and closes with `---`. This is what Claude Code parses to discover the skill.
