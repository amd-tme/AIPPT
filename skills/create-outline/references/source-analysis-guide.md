# Source Analysis Guide

This guide describes how to analyze each source type when building a presentation outline.
Follow the appropriate section based on what the user provides.

## Environment Setup

Before running any Python commands, locate the virtualenv Python:

```bash
if [ -f venv/bin/python ]; then
    VENV_PYTHON=venv/bin/python
elif [ -f venv/Scripts/python.exe ]; then
    VENV_PYTHON=venv/Scripts/python.exe
else
    echo "venv not found"
fi
```

---

## 1. Codebase / Local Directory Analysis

### Files to Prioritize

Read these first, in order:

1. `README.md` or `README.rst` — project purpose, feature list, quickstart
2. `docs/` directory — architecture docs, API references, design decisions
3. `CHANGELOG.md` or `CHANGELOG` — feature history, version milestones
4. `CLAUDE.md`, `CONTRIBUTING.md`, `ARCHITECTURE.md` — contributor context
5. Main entry points: `main.py`, `app.py`, `cli.py`, `__main__.py`, `index.js`
6. Package manifest: `pyproject.toml`, `setup.py`, `package.json`, `Cargo.toml`

### Identifying Key Modules

- Python packages: look for `__init__.py` files; each directory with one is a module
- CLI entry points: search for `argparse`, `click`, `typer`, `@app.command()`
- API routes: search for `@app.get`, `@router.post`, `app.use()`, `@Controller`
- Core logic: modules imported by multiple other modules are usually central

```bash
# Find Python entry points
grep -rl "if __name__" /path/to/project --include="*.py" | head -20

# Find API route definitions
grep -rl "@app\.\|@router\." /path/to/project --include="*.py" | head -20

# Find module structure
find /path/to/project -name "__init__.py" | head -30
```

### Detecting Architecture Patterns

Look at the top-level directory structure:

- **MVC / layered**: directories named `models/`, `views/`, `controllers/`, `services/`, `repositories/`
- **Microservices**: multiple top-level service directories, each with their own `Dockerfile` or `pyproject.toml`
- **Monolith with modules**: one main package directory, submodules by feature
- **CLI tool**: single `__main__.py` or entry point, no HTTP routes
- **Library**: no `main.py` or `cli.py`, exposes a public API via `__init__.py`

### What to Extract

- **Project purpose**: What problem does this solve? Who is the audience?
- **Key features**: What are the top 5-8 capabilities?
- **Installation**: How does a user get started?
- **Configuration**: Environment variables, config files, required credentials
- **API surface**: Public functions, CLI commands, REST endpoints
- **Dependencies**: Key third-party libraries and what they're used for
- **Deployment**: Docker, cloud targets, packaging format

### What to Skip

- `tests/`, `test_*/`, `spec/` directories
- `vendor/`, `node_modules/`, `.venv/`, `venv/`
- Generated files: `*.pyc`, `__pycache__/`, `dist/`, `build/`, `.next/`
- Binary assets: images, fonts, compiled binaries
- Lock files: `poetry.lock`, `package-lock.json`, `Cargo.lock`

---

## 2. GitHub Repo Analysis

### Fetching Content with the `gh` CLI

Use `gh` commands to pull content without cloning:

```bash
# Repo metadata (name, description, languages, topics)
gh repo view {owner}/{repo} --json name,description,url,languages,topics

# Fetch README content
gh api repos/{owner}/{repo}/readme --jq '.content' | base64 -d

# List all files in the repo (full tree)
gh api repos/{owner}/{repo}/git/trees/HEAD?recursive=1 \
  --jq '.tree[] | select(.type=="blob") | .path'

# Fetch a specific file by path
gh api repos/{owner}/{repo}/contents/{path} --jq '.content' | base64 -d

# Latest release notes
gh release view --repo {owner}/{repo} --json tagName,name,body 2>/dev/null

# Recent commits (for changelog / recent activity)
gh api repos/{owner}/{repo}/commits --jq '.[0:10] | .[] | .commit.message'

# Open issues / PRs for roadmap context
gh api repos/{owner}/{repo}/issues?state=open --jq '.[0:20] | .[] | .title'
```

### Fallback: Clone if `gh` is Unavailable

```bash
git clone --depth 1 {url} /tmp/{repo-name}
```

Then treat as a local directory (see Section 1 above).

### Analysis Order

1. Fetch repo metadata first — description and topics give fast orientation
2. Fetch the README — most important single file
3. List the repo tree — identify docs, key source paths, and config files
4. Fetch `docs/` files, `CONTRIBUTING.md`, `ARCHITECTURE.md` if present
5. Fetch a handful of key source files identified from the tree
6. Check latest release notes for recent additions and version context
7. Skim open issues for roadmap and known pain points (optional, for future-looking slides)

---

## 3. Document Conversion (markitdown)

### Supported Formats

PDF, DOCX, XLSX, PPTX, HTML, RTF, CSV, JSON, XML, images (OCR via tesseract if installed).

### Conversion Command

```bash
$VENV_PYTHON -m markitdown input.pdf -o /tmp/converted.md

# For URLs, markitdown can fetch and convert directly:
$VENV_PYTHON -m markitdown https://example.com/page -o /tmp/page.md
```

If the `-o` flag is not supported by the installed version, capture stdout:

```bash
$VENV_PYTHON -m markitdown input.pdf > /tmp/converted.md
```

### Handling Conversion Artifacts

After conversion, watch for and clean up:

- **Excessive blank lines**: multiple consecutive newlines from page breaks
- **Page break markers**: strings like `---`, `\f`, or `[Page N]` inserted by the converter
- **Garbled headings**: heading level normalization may be off (re-level if needed)
- **Table noise**: ASCII table formatting from XLSX/CSV may need simplification
- **Header/footer repetition**: running headers repeat on every page in PDFs; identify and ignore them
- **Footnote clutter**: footnote text appended at end of sections; usually skip for outline purposes

When reading the converted markdown, focus on sections with clear headings and substantive paragraphs. Skip boilerplate legal text, repeated disclaimers, and appendix tables unless they contain key data the user asked to cover.

### Multi-File Inputs

When the user provides multiple files:

1. Convert each file independently with markitdown
2. Read all converted files
3. Identify the major themes present across all files
4. Look for overlap and contradiction between documents
5. Organize the outline around unified themes, not file-by-file structure (unless that structure is meaningful)

---

## 4. Web Page Content Extraction

### Standard Extraction with markitdown

`markitdown` handles HTML pages directly via URL:

```bash
$VENV_PYTHON -m markitdown https://example.com/docs/overview
```

This is the preferred method — it strips navigation, ads, and boilerplate, returning main content as clean markdown.

### JavaScript-Heavy Pages (Playwright Fallback)

If markitdown returns empty or minimal content (the page renders content via JavaScript), use Playwright to render first:

```python
# Via the Playwright MCP tools:
# 1. Navigate to the page
# 2. Wait for key content to appear
# 3. Use browser_snapshot to capture the accessibility tree (text-based, no screenshot needed)
# 4. Extract the text from the snapshot
```

The accessibility snapshot (`browser_snapshot`) returns structured text that can be read for outline extraction. This is a text operation — do not take a screenshot here. Screenshots are for Phase 3 (visual capture), not content extraction.

### Distinguishing Content Extraction from Visual Capture

- **Content extraction** (this phase): Text, structure, headings, lists — use markitdown or Playwright snapshot
- **Visual capture** (Phase 3 of the skill): Screenshots for diagram slides — use `browser_take_screenshot`

Do not conflate these. Extract text content here; defer screenshots to the visual capture step.

### Multiple Pages

If the user provides a landing page with links to sub-pages (e.g., a docs site):

1. Extract the landing page first to understand the navigation structure
2. Identify the 3-5 most relevant sub-pages based on the outline goal
3. Extract those sub-pages individually
4. Synthesize across all pages into a unified set of themes

---

## 5. Existing Outline (Refinement)

### Reading the Outline

This is the simplest case — read the file directly:

```bash
# The outline is a markdown file; read it with the Read tool
```

No conversion needed.

### Analysis Steps

1. **Identify structure**: Count slides, check heading hierarchy, note layout directives (`LAYOUT:`, `IMAGE:`)
2. **Assess coverage**: Does the outline address the user's stated goal? Are key topics missing?
3. **Check balance**: Are some sections too long, others too thin?
4. **Spot redundancy**: Are any slides covering the same point from different angles?
5. **Evaluate flow**: Does the narrative move logically from intro → problem → solution → proof → call-to-action?

### Preserving Existing Content

When refining an outline:

- Keep existing slide titles unless they are clearly wrong or off-topic
- Keep existing `LAYOUT:` and `IMAGE:` directives unchanged
- Add new slides to fill gaps; do not delete slides without explicit user instruction
- If reorganizing, note the original order so the user can compare

### Common Gaps to Look For

- Missing title slide or agenda slide
- No problem statement or motivation section
- Benefits claimed but not substantiated (no evidence slide)
- No clear call-to-action or next steps at the end
- Technical depth inconsistent with stated audience
