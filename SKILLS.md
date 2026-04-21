# Claude Code Skills

AIPPT includes three [Claude Code](https://claude.ai/code) skills that form a presentation pipeline. Each skill is an interactive workflow invoked via a slash command.

```
Source Material → /create-outline → outline.md → /create-deck → deck.pptx → /deck-review → feedback
```

## `/create-outline` — Generate an outline from source material

Takes raw source material and produces a structured markdown outline in aippt format.

**Accepts:** Local files (markdown, PDF, DOCX, XLSX), codebases/directories, GitHub repo URLs, web app URLs, or a freeform topic description.

**Workflow (3 phases):**

1. **Content Gathering** — Collects and analyzes source material. Converts documents via `markitdown`, scans codebases for key files, fetches GitHub repos via `gh` CLI, extracts web page text.
2. **Outline Generation** — Asks about audience, goal, and tone, then proposes a slide structure and generates a full outline in aippt format. Saves to `outlines/{name}.md`. Iterates with the user until approved.
3. **Visual Enrichment** — Scans the approved outline for slides that need visuals, presents a plan, then captures screenshots via Playwright. Deferred visuals get TODO placeholders.

**Usage:**

```
/create-outline                          # Interactive — prompts for sources
/create-outline path/to/docs             # Start with a local path
/create-outline https://github.com/org/repo  # Start with a GitHub repo
```

**Output:** A markdown outline in `outlines/` ready for `/create-deck` or `aippt create`.

## `/create-deck` — Generate a PowerPoint deck from an outline

Takes a markdown outline and produces a `.pptx` presentation.

**Two engines:**

| Engine | Best for | How it works |
|--------|----------|--------------|
| **pptxgenjs** (default) | Creative, polished decks | Generates a Node.js script that builds slides with icons, cards, stat callouts. Uses a theme YAML for colors/fonts/logo. |
| **python-pptx** | Strict brand compliance | Generates a Python script that fills placeholders in an existing corporate `.pptx` template. |

**Workflow:**

1. **Select outline** — Scans `outlines/` for `.md` files.
2. **Choose engine** — pptxgenjs (default) or python-pptx if a template is involved.
3. **Choose theme/template** — Picks a theme YAML (pptxgenjs) or `.pptx` template (python-pptx).
4. **Generate** — Analyzes each slide's content, selects layouts (cards, columns, numbered steps, code panels, etc.), generates and runs the build script.

**Usage:**

```
/create-deck                             # Interactive — prompts for outline
/create-deck outlines/my-outline.md      # Start with a specific outline
```

**Output:** A `.pptx` file in `output/` plus the generated build script for reproducibility.

## `/deck-review` — Visual QA and presentation lifecycle

Full-lifecycle skill for reviewing and improving generated decks.

**Capabilities:**

- **Visual QA** — Converts deck to images, reviews each slide for layout issues, text overflow, color contrast, and alignment.
- **AI Analysis** — Runs `aippt analyze` for feedback, speaker notes, tagging, or improvement suggestions.
- **Screenshot Capture** — Captures web app screenshots via Playwright for use in outlines.
- **Web UI** — Starts the aippt web server and navigates the slide library via Playwright.
- **Excalidraw Diagrams** — Creates diagrams for `IMAGE:` directives in outlines.

**Usage:**

```
/deck-review                             # Interactive — prompts for task
/deck-review output/my-deck.pptx         # Review a specific deck
```

## Prerequisites

All skills require the Python virtualenv (`venv/`) to be set up with dependencies installed. See the main [README.md](README.md) for installation instructions.

| Dependency | Required by | Install |
|------------|------------|---------|
| Python venv + requirements.txt | All skills | `pip install -r requirements.txt` |
| `pptxgenjs` (npm) | `/create-deck` (pptxgenjs engine) | `npm install -g pptxgenjs react-icons react react-dom sharp` |
| `markitdown` (pip, in venv) | `/create-outline` | Included in requirements.txt |
| `gh` CLI | `/create-outline` (GitHub repos) | [cli.github.com](https://cli.github.com) |
| Playwright MCP server | `/create-outline`, `/deck-review` | Configured in Claude Code MCP settings |
| Excalidraw MCP server | `/deck-review` (diagrams) | Configured in Claude Code MCP settings |
