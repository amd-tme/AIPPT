# AIPPT
- AI-Powered Markdown to PowerPoint
- Turn structured text into polished presentations
- Open source Python toolkit for content creators and teams

# The Problem
- Creating presentations is tedious and time-consuming
- Content often exists in text form but needs to become slides
- Existing tools lack AI enhancement and enterprise LLM support
- Slide reuse across decks is manual and error-prone

# How It Works
- Write your content as a simple markdown outline
- Choose a PowerPoint template for branding
- Run a single CLI command to generate your deck
- Optionally enhance with AI for better narrative and visuals

# Markdown In, PowerPoint Out
- H1 headers become slide titles
- Bullet points become slide content
- Nested bullets preserve hierarchy
- Sections supported via H2 headers for larger decks

# AI-Powered Enhancement
- LLM generates narrative context and talking points
- Automatic layout selection: bullets, two-column, diagrams
- Speaker notes added to every slide
- Supports OpenAI, Anthropic, and Google models

# Enterprise LLM Gateway Support
- Route AI calls through corporate API gateways
- YAML-based configuration for base URL, auth, and providers
- No API keys hardcoded; environment variable driven
- Compatible with any OpenAI-compatible endpoint

# Reverse Engineering Decks
- Convert existing PowerPoint files back to markdown
- Preserves slide structure, content, and speaker notes
- Edit in your favorite text editor, then regenerate
- LLM-enhanced reverse mode for cleaner outlines

# Slide Cataloging and Search
- Ingest decks into a SQLite database with content hashing
- AI-powered tagging with custom taxonomy support
- Search by tags, titles, or content across all cataloged decks
- Deduplication detects reused and modified slides

# Remix: Build New Decks from Existing Slides
- Search and export slide manifests in YAML format
- Assemble new presentations from slides across multiple decks
- Version detection warns when newer slide versions exist
- Preserve original formatting and embedded content

# Multimodal Analysis
- Export slides as images for visual AI analysis
- Four analysis modes: feedback, notes, tags, and improvements
- AI examines both visual design and text content
- Batch processing with graceful error handling

# Web UI
- Browser-based interface powered by FastAPI and htmx
- Upload, create, catalog, and search from one dashboard
- Real-time progress feedback during deck generation
- No complex frontend build step; single-page app design

# Architecture and Design
- Modular Python package with clean separation of concerns
- Unified CLI with subcommands for every feature
- Graceful degradation: individual failures never crash the batch
- Content hashing (SHA-256) for deduplication and versioning

# Typical Workflow
- Write or reverse-engineer a markdown outline
- Run create with --enhance to generate a polished deck
- Ingest the deck to catalog and tag slides
- Search and remix slides across your library over time

# Get Started
- Install dependencies: pip install -r requirements.txt
- Create your first deck: aippt.py create outline.md template.pptx output.pptx
- Explore the web UI: aippt.py serve --port 8000
- Full documentation and source available on GitHub
