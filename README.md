# AIPPT

A modular Python toolkit for creating, analyzing, and managing PowerPoint presentations. Convert markdown outlines into slide decks, use AI to enhance and improve existing presentations, catalog slides into a searchable database, and remix slides across decks.

## Installation

1. Ensure you have Python 3.x installed
2. Create a virtualenv and install dependencies:
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    pip install -r requirements.txt
    ```
3. Set up API keys for AI features (or configure a gateway — see below):
    ```bash
    export ANTHROPIC_API_KEY='your-key'   # For Claude models
    export OPENAI_API_KEY='your-key'      # For OpenAI/DALL-E models
    ```
4. Initialize model configuration:
    ```bash
    python aippt.py models init     # Creates models.yaml from example
    ```

## CLI Overview

All commands use the unified entry point:

```bash
python aippt.py <command> [options]
```

Use `--debug` on any command for detailed logging.

### Creating Presentations

**`create`** — Build a PowerPoint deck from a markdown outline.

```bash
# Basic: outline + template → presentation
python aippt.py create outline.md template.pptx output.pptx

# With AI enhancement (LLM picks layouts, adds speaker notes)
python aippt.py create outline.md template.pptx output.pptx --enhance

# With a specific model and diagram generation
python aippt.py create outline.md template.pptx output.pptx --enhance --model gpt-4o --image-gen dalle

# Test run: only process first 3 slides
python aippt.py create outline.md template.pptx output.pptx --enhance --test 3
```

When `--enhance` is enabled, the LLM analyzes each slide and selects from five layout types (`bullet`, `numbered`, `two_column`, `diagram`, `basic`), generates speaker notes, and suggests visuals. Original outline content is preserved on the slide body.

**`reverse`** — Convert an existing PowerPoint back to a markdown outline.

```bash
python aippt.py reverse presentation.pptx output.md
python aippt.py reverse presentation.pptx output.md --no-notes
```

### AI Analysis and Improvement

These commands use LLMs to analyze and improve existing presentations. They support multimodal input (slide images + text) when images are available, and fall back to text-only analysis otherwise.

**`analyze`** — Run AI analysis on a cataloged deck. Four modes available:

```bash
# Get presentation feedback (printed to stdout)
python aippt.py analyze deck.pptx --mode feedback --images-dir images/deck/

# Generate speaker notes (written back to the PPTX)
python aippt.py analyze deck.pptx --mode notes --images-dir images/deck/

# Auto-tag slides using a taxonomy (tags stored in the database)
python aippt.py analyze deck.pptx --mode tags --taxonomy tags.csv

# Get improvement suggestions
python aippt.py analyze deck.pptx --mode improvements --images-dir images/deck/
```

**`improve`** — Rewrite slide content using LLM analysis. The LLM sees each slide's image (when available) and text, then rewrites the body content. Revision history is tracked in speaker notes.

```bash
# Preview changes without modifying
python aippt.py improve deck.pptx --dry-run

# Improve specific slides with a focus area
python aippt.py improve deck.pptx --slides 3,5,8 --focus brevity

# Multiple improvement passes, save to a new file
python aippt.py improve deck.pptx --output improved.pptx --passes 2

# Focus options: general, accuracy, detail, brevity, structure
```

### Slide Catalog and Remix

These commands manage a SQLite database of slides for searching and remixing across decks.

**`ingest`** — One-step pipeline: export slide images, catalog the deck, and optionally generate AI tags.

```bash
# Basic ingest (images + catalog)
python aippt.py ingest deck.pptx

# With AI tagging
python aippt.py ingest deck.pptx --tags --model gpt-4o

# With taxonomy-constrained tags
python aippt.py ingest deck.pptx --tags --taxonomy tags.csv
```

Image export requires PowerPoint (Windows or WSL with PowerPoint installed).

**`search`** — Query cataloged slides by tags, title, or section.

```bash
python aippt.py search --tags "security,architecture"
python aippt.py search --title-contains "zero trust"

# Export results as a remix manifest
python aippt.py search --tags "security" --export-manifest security-remix.yaml
```

**`remix`** — Assemble a new deck from a manifest of slides pulled from different source decks.

```bash
python aippt.py remix manifest.yaml output.pptx
```

### Utility Commands

**`catalog`** — Catalog a deck into the database (without image export).

```bash
python aippt.py catalog deck.pptx --images-dir images/deck/
```

**`export-images`** — Export slides as PNG images using PowerPoint COM automation (Windows/WSL).

```bash
python aippt.py export-images deck.pptx images/deck/
python aippt.py export-images deck.pptx --width 2560 --height 1440
```

**`export`** — Export slide metadata from the database to CSV.

```bash
python aippt.py export deck.pptx --output slides.csv
python aippt.py export --all --output catalog.csv
```

**`write-notes`** — Write speaker notes from the database back into a PPTX file (creates a backup first).

```bash
python aippt.py write-notes deck.pptx
```

**`tags`** — Manage the taxonomy of predefined tags.

```bash
python aippt.py tags                          # List all taxonomy tags
python aippt.py tags add "cloud" --category "Technology"
python aippt.py tags import taxonomy.csv
python aippt.py tags rename "old-name" "new-name"
```

**`tag` / `untag`** — Manually add or remove tags from individual slides.

```bash
python aippt.py tag 42 "security,compliance"
python aippt.py untag 42 "compliance"
python aippt.py untag 42 --all
```

**`models`** — View and manage model configuration.

```bash
python aippt.py models                        # Show current defaults
python aippt.py models list-available          # Show all registered models
python aippt.py models set enhance gpt-4o      # Change default for an operation
python aippt.py models init                    # Create models.yaml from example
```

**`serve`** — Launch the web UI (FastAPI + htmx).

```bash
python aippt.py serve --port 8000
python aippt.py serve --port 8000 --gateway-config gateway.yaml
```

## Model Configuration

Models are configured in `models.yaml`. Run `aippt.py models init` to create it from the included example.

The file has two sections:
- **registry** — Every model the system can use, with provider, context window, and capability flags
- **defaults** — Which model to use for each operation (`enhance`, `improve`, `feedback`, `notes`, `tags`, `image`)

CLI `--model` flags override the defaults for a single invocation. Models from OpenAI, Anthropic, and Google are supported out of the box. Custom models can be added to the registry.

## Gateway Configuration

For corporate API gateways, create a `gateway.yaml` to route LLM calls through a centralized endpoint:

```yaml
gateway:
  base_url: "https://llm-api.example.com"
  auth_header: "Ocp-Apim-Subscription-Key"
  auth_value_env: "GATEWAY_API_KEY"
providers:
  openai:
    path: "/OpenAI"
  anthropic:
    path: "/Anthropic"
  google:
    path: "/VertexAI"
```

Pass `--gateway-config gateway.yaml` to any command that uses an LLM, or place it in the project root (the default path).

## Outline Format

The input outline is a markdown file. This section covers everything needed to write high-quality outlines — structure, formatting, directives, and best practices. It is designed to be self-contained so that an LLM can generate outlines from source material (a GitHub repo, a document, meeting notes, etc.) without additional context.

### Frontmatter

Optional YAML frontmatter at the top of the file provides metadata used by `--enhance`:

```markdown
---
audience: engineers
goal: Explain the migration strategy and get buy-in
tone: professional
---
```

| Field | Purpose | Examples |
|-------|---------|---------|
| `audience` | Who the slides are for — affects language level and detail depth | `engineers`, `executives`, `mixed`, `sales` |
| `goal` | What the presentation should accomplish | `Introduce the product`, `Get budget approval` |
| `tone` | Communication style | `professional`, `conversational`, `technical` |

All fields are optional. When present, the enhancement LLM uses them to tailor layout choices, speaker notes, and narrative structure.

### Structure modes

The parser supports two modes, selected automatically based on whether `## ` (H2) headers are present.

**Simple mode (H1 = slides)** — Each `# ` header becomes a slide title; everything below it becomes the slide body.

```markdown
# Introduction
- Welcome to the presentation
- Today's agenda

# Key Findings
- Revenue grew 15% year-over-year
- Customer satisfaction at an all-time high
  - NPS score of 72
  - Support ticket volume down 30%
```

**Hierarchical mode (H1 = sections, H2 = slides)** — When any `## ` header is present, H1 headers become PowerPoint sections and H2 headers become slide titles. Use this for longer decks with logical groupings.

```markdown
# Introduction
## Welcome
- About the team
- Meeting objectives

## Agenda
- Review Q1 results
- Discuss roadmap
- Q&A

# Q1 Results
## Revenue
- Total revenue: $4.2M
- 15% growth over Q4
```

### Content formatting

| Syntax | Result on slide |
|--------|----------------|
| `- item` or `* item` | Bullet point (level 1) |
| `  - sub-item` (2+ leading spaces) | Sub-bullet (level 2, smaller font) |
| `1. step` | Numbered item |
| `**bold text**` | Converted to UPPERCASE in plain text |
| `*italic text*` | Stripped to plain text |
| `[link text](url)` | Link text only (URL removed) |
| `` `code` `` | Inline code markers removed |
| Plain text lines | Rendered as-is |

### Bold lead-ins

Text matching the pattern `Term: rest of text` or `Term — rest of text` (1-4 words before a colon-space or em-dash) is automatically rendered with the lead-in in **bold** and the remainder in regular weight. This creates strong visual hierarchy on slides without manual formatting.

```markdown
## Why Containers?
- **Reproducibility** — consistent environments across dev, staging, and production
- **Driver decoupling** — container carries ROCm toolkit, host only needs the kernel module
- **Version flexibility** — run multiple ROCm versions side-by-side
- **Orchestration-ready** — standard deployment unit for Kubernetes
```

**Guidelines:**
- Use bold lead-ins on every bullet when presenting a list of features, benefits, concepts, or categories
- Keep lead-ins to 1-4 words — they should be scannable at a glance
- Use either `: ` or ` — ` (space-emdash-space) as the separator, not both in the same slide
- Apply consistently within a slide — either all bullets have lead-ins or none do
- Omit lead-ins when bullets are short, self-explanatory, or part of a sequential process

### Outline directives

Add `LAYOUT:` and `IMAGE:` directives to any slide's content to control its appearance. Directives are stripped from the slide body before rendering — they only affect how the slide is built.

#### `LAYOUT: <type>`

Sets the slide layout type. Must be one of:

| Type | When to use | PowerPoint Layout |
|------|-------------|-------------------|
| `basic` | Default. Short bullet lists, simple content | Title and Content |
| `bullet` | Explicit choice for bullet-heavy slides (same rendering as basic) | Title and Content |
| `numbered` | Sequential steps, procedures, workflows, installation instructions | Title and Content |
| `two_column` | Comparisons, category/example pairs, before/after, pros/cons | Two Content |
| `diagram` | Full content area for images or diagrams | Title Only |

When used with `--enhance`, the author's `LAYOUT:` directive overrides the LLM's layout suggestion.

**Choosing the right layout:**
- If content describes steps in order (Step 1, Step 2...) or a process flow → `numbered`
- If content compares two things or groups items into two categories → `two_column`
- If a slide has an image that should fill the content area → `diagram`
- For everything else → `bullet` or omit the directive and let `--enhance` decide

#### `LAYOUT: numbered` — numbered lists

Use for any sequential or procedural content. The layout auto-numbers top-level bullets (1., 2., 3...) and preserves sub-bullets without numbering.

```markdown
## Installing the Server
LAYOUT: numbered
- Install ROCm (provides the kernel driver and Python bindings)
- Clone the repository: git clone https://github.com/org/project.git
- Install dependencies: pip install -r requirements.txt
- Run the server: python server.py
```

**Do not** include inline numbers (`1.`, `2.`) in the bullet text when using `LAYOUT: numbered` — the layout adds them automatically.

#### `LAYOUT: two_column` — side-by-side content

Use `|||` on its own line to explicitly separate left and right column content. Without `|||`, content is split at the midpoint automatically, which may not produce the desired grouping.

Add pipe-separated column headers after the layout type:

```markdown
## Feature Comparison
LAYOUT: two_column | Open Source | Enterprise
- Community support only
- Self-hosted infrastructure
- Manual scaling and updates
|||
- 24/7 vendor support with SLA
- Managed cloud deployment
- Auto-scaling and rolling updates
```

**Guidelines:**
- Always use `|||` for explicit column breaks — don't rely on auto-splitting
- Aim for roughly equal content in each column (3-4 bullets per side)
- Keep individual bullets short (one line) to avoid overflow in narrow columns
- Column headers are optional but strongly recommended for comparison slides

#### `IMAGE: <path>`

Embeds a local image file onto the slide. The path is resolved relative to the outline file's directory.

```markdown
# Architecture Overview
LAYOUT: diagram
IMAGE: images/architecture.png
- Microservices communicate via event bus
- Each service owns its data store
```

When an image is present with `diagram` or `two_column` layout, it occupies the full content area (8" x 4") and the bullet text is moved to speaker notes. With other layouts, the image and text are displayed side-by-side.

**Rules:**
- Directives are case-sensitive (`LAYOUT:` and `IMAGE:`, uppercase)
- Place directives in the slide's content block (after the header line), before or among bullet content
- One of each per slide (first occurrence wins if duplicated)
- Missing images log a warning and the slide is created without the image
- Invalid layout types log a warning and fall back to `basic`
- Supported image formats: PNG, JPG, JPEG, GIF, BMP, TIFF, SVG

### Writing effective outlines

These guidelines produce outlines that render well as slides — whether generated by hand or by an LLM from source material.

**Content density:**
- Aim for 4-6 bullets per slide. More than 6 top-level bullets risks text overflow on most templates.
- Keep each bullet to one line of text (roughly 80-100 characters). Multi-sentence bullets become unreadable at presentation font sizes.
- If a slide has more than 6 bullets, split it into two slides or use a two-column layout.

**Slide structure:**
- Use hierarchical mode (`# sections`, `## slides`) for decks longer than 5-6 slides — sections create visual groupings in PowerPoint's slide sorter.
- The first slide under each `# section` acts as a section opener — keep it high-level.
- End with a summary or resources slide.

**Layout selection:**
- Prefer `LAYOUT: numbered` for any sequential, procedural, or step-by-step content. This includes installation guides, workflows, troubleshooting steps, and how-it-works explanations.
- Prefer `LAYOUT: two_column` for comparisons, before/after, category/example pairs, and pros/cons.
- Use `LAYOUT: diagram` only when you have an `IMAGE:` directive or when `--enhance` will generate a diagram.
- Omit `LAYOUT:` when content is a straightforward bullet list — let `--enhance` choose, or accept the default `basic` layout.

**Bold lead-ins:**
- Use `**Term** —` or `**Term:** ` patterns on every bullet when presenting features, benefits, tools, or categories.
- Don't use bold lead-ins on numbered/sequential content — the step numbers provide the visual anchor.
- Be consistent within each slide: either all bullets have lead-ins or none do.

**Two-column best practices:**
- Always include `|||` to mark the column break explicitly.
- Add column headers: `LAYOUT: two_column | Left Header | Right Header`
- Balance content across columns (3-4 bullets each).
- Shorten descriptions — columns are half-width, so long text wraps poorly.

### Example: complete outline

This example demonstrates all the formatting features in a realistic outline:

```markdown
---
audience: engineers
goal: Introduce the monitoring stack and get teams to adopt it
tone: technical
---

# Introduction

## GPU Monitoring Overview
- **Visibility** — real-time insight into GPU health, utilization, and errors
- **Proactive ops** — detect thermal, ECC, and power anomalies before they cause downtime
- **Standard tooling** — Prometheus and Grafana, no vendor lock-in

## Agenda
- Management tools and CLI
- Metrics exporter and dashboards
- Alerting patterns
- Enterprise integration

# Core Tools

## amd-smi CLI
- **Live monitoring** — real-time GPU metrics from the command line
- **Fleet queries** — query all GPUs on a node in one command
- **JSON output** — machine-readable for scripting and automation
- **Configuration** — set power limits, clock profiles, partition modes

## Deploying the Exporter
LAYOUT: numbered
- Install the Device Metrics Exporter container on each GPU node
- Configure Prometheus to scrape the exporter endpoint on port 5000
- Import the pre-built Grafana dashboards from the exporter repo
- Add Alertmanager rules for thermal and ECC thresholds

## Key Metrics
LAYOUT: two_column | Metric | Description
- GPU_GFX_ACTIVITY — compute utilization (%)
- GPU_JUNCTION_TEMPERATURE — hotspot temp (C)
- GPU_AVERAGE_SOCKET_POWER — power draw (W)
|||
- GPU_ECC_CORRECT_TOTAL — correctable ECC errors
- GPU_ECC_UNCORRECT_TOTAL — uncorrectable ECC errors
- GPU_USED_VRAM / GPU_TOTAL_VRAM — memory usage

# Operations

## Alerts to Configure
- **Thermal** — junction temperature exceeding safe thresholds
- **ECC errors** — any uncorrectable error triggers immediate investigation
- **Utilization** — sustained 0% may indicate workload failure
- **Power** — unexpected draw changes signal hardware issues

## Summary and Resources
- Standard Prometheus/Grafana stack — no custom tooling required
- **Resources:**
  - Metrics Exporter: github.com/ROCm/device-metrics-exporter
  - AMD SMI Docs: instinct.docs.amd.com
```

## Claude Code Skills

AIPPT includes interactive [Claude Code](https://claude.ai/code) skills that form a presentation pipeline — from source material to finished deck to visual QA. See [SKILLS.md](SKILLS.md) for detailed usage and workflow documentation.

| Slash Command | Purpose |
|---------------|---------|
| `/create-outline` | Generate a markdown outline from source material (docs, code, repos, URLs) |
| `/create-deck` | Generate a PowerPoint deck from a markdown outline |
| `/deck-review` | Visual QA, AI analysis, screenshot capture, and diagram creation |

## Dependencies

- python-pptx: PowerPoint file handling
- anthropic: Claude AI integration
- openai: OpenAI API integration
- tiktoken: Token counting for OpenAI models
- cairosvg: SVG to PNG conversion
- pillow: Image processing
- requests: HTTP requests
- fastapi + uvicorn: Web UI
- pyyaml: Configuration files
