# PRD: Sphinx Documentation

**Date:** 2026-03-04
**Author:** Matt
**Status:** Draft

---

## Summary

Add Sphinx-based documentation covering app overview, CLI usage, web UI guide, backup/restore, and configuration. Docs are built to static HTML, served at `/docs` via the web UI with a dedicated "Docs" tab in the nav bar, and automatically built during Docker image builds.

## Motivation

- **What problem does this solve?** All project documentation currently lives in CLAUDE.md, README.md, and scattered PRD files. There is no structured, browsable user documentation. New team members and users must read source code or markdown files to understand features.
- **Who benefits?** End users of the web UI and CLI, especially team members accessing a shared view-only instance.
- **What happens if we don't do this?** Users rely on README.md and trial-and-error to learn the tool. The web UI provides no inline help.

## Requirements

### Must Have

- [ ] Sphinx project in `docs/` with `conf.py`, `Makefile`, `index.rst`
- [ ] Documentation sections:
  - Overview / Getting Started
  - CLI Reference (all subcommands with examples)
  - Web UI Guide (browsing, searching, tagging, notes)
  - Backup & Restore
  - Configuration (dirs.yaml, models.yaml, gateway.yaml)
- [ ] Build to `docs/_build/html/`
- [ ] FastAPI static mount at `/docs` serving the built HTML
- [ ] "Docs" tab in web UI nav bar linking to `/docs/index.html`
- [ ] `sphinx` and `sphinx-rtd-theme` added to a `docs-requirements.txt`
- [ ] `make docs` or `make -C docs html` builds the documentation
- [ ] Docs built during Docker image build

### Nice to Have

- [ ] API Reference section (auto-generated from docstrings via `sphinx.ext.autodoc`)
- [ ] Search within docs (Sphinx built-in search)
- [ ] Version number pulled from `aippt/__init__.py`

### Out of Scope

- Hosting docs externally (ReadTheDocs, GitHub Pages)
- Internationalization / translations
- Video tutorials or interactive guides
- Migrating existing PRD files into Sphinx

---

## Design

### Directory Structure

```
docs/
  conf.py              # Sphinx configuration
  Makefile              # Build targets (html, clean)
  make.bat              # Windows build support
  index.rst             # Documentation root / table of contents
  overview.rst          # Project overview and getting started
  cli.rst               # CLI reference with all subcommands
  web-ui.rst            # Web UI guide
  backup-restore.rst    # Backup, export, restore workflow
  configuration.rst     # dirs.yaml, models.yaml, gateway.yaml
  api.rst               # API endpoint reference (nice to have)
  _static/              # Custom CSS, images
  _build/               # Build output (gitignored)
    html/               # Static HTML served at /docs
```

### Sphinx Configuration (conf.py)

```python
project = "AIPPT"
copyright = "2026"
author = "Matt"
version = "2.0.0"  # or pulled from aippt.__version__

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
```

### Web UI Integration

FastAPI mounts the built docs as a static directory:

```python
# In app.py create_app()
docs_dir = Path(__file__).parent.parent.parent / "docs" / "_build" / "html"
if docs_dir.is_dir():
    app.mount("/docs", StaticFiles(directory=str(docs_dir), html=True), name="docs")
```

Nav bar in `index.html` gets a new "Docs" link:

```html
<li><a href="/docs/index.html" target="_blank">Docs</a></li>
```

The `target="_blank"` opens docs in a new tab since Sphinx generates a full standalone site that doesn't integrate with the SPA navigation.

### Docker Build Integration

In the Dockerfile:

```dockerfile
COPY docs/ docs/
RUN pip install --no-cache-dir sphinx sphinx-rtd-theme && \
    make -C docs html
```

This ensures every container image includes pre-built documentation accessible at `/docs`.

### Documentation Content Outline

**Overview (overview.rst)**
- What is AIPPT
- Key features (catalog, search, tags, analysis, remix)
- Quick start: install, ingest a deck, launch web UI

**CLI Reference (cli.rst)**
- Each subcommand as a section: create, reverse, catalog, analyze, search, remix, ingest, export, export-images, serve, models, tags, migrate-paths, db-info, write-notes
- Arguments, options, defaults, examples for each

**Web UI Guide (web-ui.rst)**
- Launching the server
- Deck list: browsing, uploading, downloading
- Slide browser: viewing, detail modal
- Search: by title, by tags
- Tag sidebar: filtering across decks
- Notes editing: save, history, write-back
- Settings: models, templates, taxonomy
- View-only mode: what's available, what's disabled

**Backup & Restore (backup-restore.rst)**
- backup.sh usage (copy mode vs --export mode)
- Archive contents
- restore.sh usage
- Workflow: analyze on workstation, export, deploy view-only

**Configuration (configuration.rst)**
- dirs.yaml: directory paths and defaults
- models.yaml: per-operation model defaults
- gateway.yaml: corporate LLM gateway setup
- Environment variables: API keys, AIPPT_VIEW_ONLY

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `docs/conf.py` | New | Sphinx configuration |
| `docs/Makefile` | New | Build targets |
| `docs/index.rst` | New | Root TOC |
| `docs/*.rst` | New | Content pages (5-6 files) |
| `docs-requirements.txt` | New | Sphinx dependencies |
| `aippt/web/app.py` | Modified | Mount docs static directory |
| `aippt/web/static/index.html` | Modified | Add "Docs" nav link |
| `Dockerfile` | Modified | Build docs during image build |
| `.gitignore` | Modified | Exclude `docs/_build/` |

### Data Model Changes

No data model changes.

---

## CLI Changes

No CLI changes.

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Nav bar | New link | "Docs" tab linking to `/docs/index.html` (opens in new tab) |

### New Routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/docs/*` | Static file serving of Sphinx HTML (only when built docs exist) |

---

## Testing

### Unit Tests

No unit tests needed for documentation content. The Sphinx build itself validates RST syntax.

### Build Verification

```bash
# Verify docs build without errors
make -C docs html

# Verify the output exists
ls docs/_build/html/index.html
```

### Integration Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_web.py` | `test_docs_route_serves_html` | `/docs/index.html` returns 200 when docs are built |
| `tests/test_web.py` | `test_docs_route_missing_gracefully` | No crash when `docs/_build/html/` doesn't exist |

### Manual Testing

1. `make -C docs html` -- builds without errors or warnings
2. Open `docs/_build/html/index.html` in browser -- all pages render correctly
3. Start web server -- click "Docs" tab -- docs open in new tab
4. `docker compose build` -- docs built during image build
5. Run container -- `/docs` route serves documentation

---

## Changelog Entry

```markdown
### Added
- Sphinx-based documentation covering CLI, web UI, backup/restore, and configuration
- "Docs" tab in web UI nav bar linking to built documentation
- Documentation automatically built during Docker image build
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Create `docs-requirements.txt` with sphinx dependencies | `docs-requirements.txt` | -- |
| 2 | Create Sphinx project skeleton (`conf.py`, `Makefile`, `index.rst`) | `docs/` | 1 |
| 3 | Write overview.rst | `docs/overview.rst` | 2 |
| 4 | Write cli.rst | `docs/cli.rst` | 2 |
| 5 | Write web-ui.rst | `docs/web-ui.rst` | 2 |
| 6 | Write backup-restore.rst | `docs/backup-restore.rst` | 2 |
| 7 | Write configuration.rst | `docs/configuration.rst` | 2 |
| 8 | Mount docs in FastAPI app | `aippt/web/app.py` | 2 |
| 9 | Add "Docs" tab to web UI nav | `aippt/web/static/index.html` | 8 |
| 10 | Add docs build to Dockerfile | `Dockerfile` | 2 |
| 11 | Add `docs/_build/` to `.gitignore` | `.gitignore` | 2 |
| 12 | Add integration tests for /docs route | `tests/test_web.py` | 8 |
| 13 | Update CHANGELOG.md | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Sphinx adds build complexity and dependencies — **Mitigation:** Docs dependencies are in a separate `docs-requirements.txt`, only installed during Docker build or explicit `make docs`. Not required for running the app.
- **Risk:** Documentation goes stale as features evolve — **Mitigation:** PRD process already documents features. Docs can be updated as part of each feature's implementation tasks.
- **Risk:** `docs/` directory already contains `plans/` subdirectory — **Mitigation:** Sphinx's `conf.py` can exclude `plans/` from the build. The `docs/plans/` PRD files and `docs/*.rst` Sphinx pages coexist in the same directory.
- **Question:** Should the existing `docs/plans/` directory be moved elsewhere to avoid confusion? — **Recommendation:** No. Keep `docs/plans/` as-is. Sphinx's `exclude_patterns` in `conf.py` will ignore it. They serve different purposes (planning vs user docs).

---

## References

- Current documentation: `CLAUDE.md`, `README.md`
- Web UI nav: `aippt/web/static/index.html` (nav bar section)
- App factory: `aippt/web/app.py` (static mount point)
- Docker PRD: `docs/plans/2026-03-04-docker-deployment.md` (docs build step)
- dirs.yaml: `dirs.yaml` (documented in configuration.rst)
