# AIPPT v2 - Expected Workflows

This document describes the typical workflows supported by the current implementation.

---

## Workflow 1: Quick Presentation Creation (Basic)

**Use Case:** Convert a simple markdown outline into a PowerPoint presentation without AI enhancement.

**Steps:**
1. Create markdown outline with `# Title` headers
2. Choose a PowerPoint template
3. Run: `python aippt.py create outline.md template.pptx output.pptx`

**Output:** PowerPoint with slides matching outline structure.

**When to use:** Quick deck creation, no AI budget, simple content.

---

## Workflow 2: AI-Enhanced Presentation Creation

**Use Case:** Create a polished presentation with AI-suggested layouts, enhanced content, and optional diagrams.

**Steps:**
1. Create markdown outline
2. Set up API credentials (or gateway)
3. Run with enhancement:
   ```bash
   python aippt.py create outline.md template.pptx output.pptx \
     --enhance \
     --model claude-3.5-sonnet
   ```
4. Optionally add diagram generation:
   ```bash
   python aippt.py create outline.md template.pptx output.pptx \
     --enhance \
     --image-gen claude \
     --model claude-3.5-sonnet
   ```

**Output:**
- PowerPoint with AI-enhanced content
- Layout suggestions applied (bullet, two-column, diagram, basic)
- SVG diagrams converted to PNG (if enabled)
- Enhanced speaker notes with narrative, visuals, talking points

**When to use:** High-quality presentations, technical content, need layout variety.

---

## Workflow 3: Reverse Engineering Existing Decks

**Use Case:** Extract content from existing PowerPoint decks into editable markdown format.

**Steps:**
1. Run: `python ppt2outline.py existing-deck.pptx extracted-outline.md`
2. Edit markdown as needed
3. Regenerate deck: `python aippt.py create extracted-outline.md template.pptx new-deck.pptx`

**Output:** Markdown outline that can be edited and regenerated.

**When to use:** Content reuse, format migration, bulk editing, version control of slide content.

---

## Workflow 4: Deck Cataloging & Organization

**Use Case:** Build a searchable catalog of presentation decks for content reuse and analysis.

**Steps:**
1. Export slide images from PowerPoint (File → Export → PNG)
2. Catalog the deck:
   ```bash
   python aippt.py catalog my-deck.pptx \
     --images-dir images/my-deck \
     --db slides.db
   ```
3. Repeat for all decks in your library

**Output:**
- SQLite database with all deck metadata
- Content hashing for version tracking
- Slide positions, titles, notes stored

**When to use:**
- Large presentation library (10+ decks)
- Need to track content changes over time
- Want to search across multiple decks
- Building a slide content management system

---

## Workflow 5: AI-Powered Slide Tagging

**Use Case:** Automatically categorize slides by topic for searchability.

**Steps:**
1. Catalog deck (see Workflow 4)
2. Run tagging:
   ```bash
   python aippt.py analyze my-deck.pptx \
     --mode tags \
     --images-dir images/my-deck \
     --model gpt-4o
   ```
3. Query tags:
   ```bash
   sqlite3 slides.db "SELECT name, COUNT(*) FROM tags JOIN slide_tags ON tags.id = slide_tags.tag_id GROUP BY name;"
   ```

**Output:** Each slide tagged with 3-7 descriptive keywords (e.g., "security", "cloud", "architecture").

**When to use:**
- Large slide library without manual tagging
- Need topic-based search/filtering
- Building presentation analytics

---

## Workflow 6: Constrained Tagging with Taxonomy

**Use Case:** Tag slides using a predefined set of categories (company taxonomy, product names, etc.).

**Steps:**
1. Create taxonomy CSV:
   ```csv
   name,category
   security,topic
   compliance,topic
   aws,provider
   solution-architecture,content-type
   ```
2. Run constrained tagging:
   ```bash
   python aippt.py analyze my-deck.pptx \
     --mode tags \
     --taxonomy company-taxonomy.csv \
     --images-dir images/my-deck
   ```

**Output:** Slides tagged only with approved taxonomy terms.

**When to use:**
- Enterprise environments with controlled vocabularies
- Need consistent tagging across teams
- Compliance/governance requirements

---

## Workflow 7: Design Feedback & Review

**Use Case:** Get AI feedback on slide design quality before presenting.

**Steps:**
1. Catalog deck with images
2. Run feedback analysis:
   ```bash
   python aippt.py analyze my-deck.pptx \
     --mode feedback \
     --images-dir images/my-deck \
     --model gpt-4o
   ```
3. Review console output for design suggestions

**Output:** 3-5 bullet points per slide with feedback on:
- Visual clarity
- Content density
- Layout effectiveness
- Improvement suggestions

**When to use:**
- Pre-presentation review
- Design quality assessment
- Learning presentation best practices

---

## Workflow 8: Automated Speaker Notes Generation

**Use Case:** Generate speaker notes from slide visuals to help presenters.

**Steps:**
1. Catalog deck with images
2. Generate notes:
   ```bash
   python aippt.py analyze my-deck.pptx \
     --mode notes \
     --images-dir images/my-deck \
     --model gpt-4o
   ```
3. Open PowerPoint to review notes in presenter view

**Output:** Speaker notes added to each slide (3-5 sentences) explaining key points and context.

**When to use:**
- Preparing for presentation delivery
- Onboarding new presenters
- Creating training materials

---

## Workflow 9: Version Tracking & Change Detection

**Use Case:** Track how slide content changes over time across deck versions.

**Steps:**
1. Catalog initial version:
   ```bash
   python aippt.py catalog deck-v1.pptx --db slides.db
   ```
2. Make edits to deck, save as `deck-v2.pptx`
3. Catalog updated version:
   ```bash
   python aippt.py catalog deck-v2.pptx --db slides.db
   ```
4. Database now tracks both versions with content hashes

**Output:**
- Content hash changes indicate modified slides
- `updated_at` timestamps show when changes occurred
- `check_newer_versions()` API detects newer versions of same content

**When to use:**
- Tracking presentation evolution
- Identifying stale content
- Auditing slide changes

---

## Workflow 10: Corporate Gateway Integration

**Use Case:** Use company LLM gateway instead of direct API access.

**Setup:**
1. Create `gateway.yaml`:
   ```yaml
   gateway:
     base_url: "https://llm-api.company.com"
     auth_header: "X-API-Key"
     auth_value_env: "COMPANY_LLM_KEY"
   providers:
     openai:
       path: "/openai"
     anthropic:
       path: "/anthropic"
   ```
2. Set environment variable:
   ```bash
   export COMPANY_LLM_KEY=your-key
   ```

**Usage:**
All commands automatically use gateway:
```bash
python aippt.py create outline.md template.pptx output.pptx \
  --enhance \
  --model gpt-4o \
  --gateway-config gateway.yaml
```

**Benefits:**
- Centralized authentication
- Usage tracking/billing
- Compliance with corporate IT policies
- Support for multiple providers through single gateway

---

## Expected Workflow Combinations

### Content Creation Pipeline
1. **Create** outline in markdown → **Enhance** with AI → **Review** with feedback mode → **Present**

### Deck Library Management
1. **Catalog** all decks → **Tag** with AI → **Search** by topic → **Remix** best slides (future)

### Continuous Improvement
1. **Create** deck → **Get feedback** → **Edit** markdown → **Regenerate** → **Compare versions**

### Knowledge Management
1. **Catalog** historical decks → **Tag** by topic → **Extract** to markdown → **Reuse** content

---

## Not Yet Implemented (Tasks 9-16)

The following workflows are planned but not yet available:

### Workflow: Search & Filter Slides
- Search by tags: `python aippt.py search --tags security,cloud`
- Search by title: `python aippt.py search --title-contains "Architecture"`
- Export search results to manifest

### Workflow: Remix - Assemble Custom Decks
1. Search for relevant slides
2. Export manifest YAML
3. Edit manifest to select slides
4. Assemble new deck: `python aippt.py remix manifest.yaml output.pptx`

### Workflow: CSV Export for Analysis
- Export metadata: `python aippt.py export --all --output slides.csv`
- Analyze in Excel/Tableau/etc.

### Workflow: Web UI Dashboard
- Browse cataloged decks
- Visual tag editing
- Search and preview
- Remix via drag-and-drop

---

## Design Patterns & Principles

### Progressive Enhancement
- Basic features work without AI (create, reverse)
- AI features are opt-in (--enhance, analyze)
- Graceful degradation on API failures

### Catalog-Centric Architecture
- Catalog is the central data store
- All analysis flows through catalog
- Enables cross-deck search and analytics

### Idempotent Operations
- Cataloging same deck twice is safe (hash check)
- Duplicate tags are ignored
- Re-running analysis updates existing data

### Gateway Abstraction
- All providers (Anthropic, OpenAI, Google) use same interface
- Gateway config is optional
- API keys auto-resolve from environment

### Fail-Safe File Operations
- Progress saved after each slide
- Partial presentations survive failures
- Original files never modified (except notes mode)

---

## Questions for Validation

1. **Is the catalog workflow optional?** Can users skip cataloging and just use create/reverse?
2. **Should remix be search-first or manifest-first?** Search → auto-generate manifest, or manual manifest creation?
3. **Are there other analysis modes needed?** Beyond feedback/notes/tags?
4. **Should the web UI be read-only or support deck creation?**
5. **Is version tracking a primary use case or secondary?** Should we add more features for diffing?
6. **Should export support formats beyond CSV?** (JSON, Excel, etc.)
7. **Are there team collaboration workflows?** Shared catalog, review workflows, etc.?
8. **Should analyze support batch mode?** Process multiple decks at once?
