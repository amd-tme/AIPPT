# PRD: Rebrand outline2ppt to aippt

**Date:** 2026-03-04
**Author:** Matt
**Status:** Draft

---

## Summary

Rename the Python package from `outline2ppt` to `aippt` to match the repository name and intended framework identity. This is a clean break — no legacy wrappers. The user-facing brand name is "AIPPT" in the web UI and documentation.

## Motivation

- **What problem does this solve?** The package name `outline2ppt` reflects the original scope (convert outlines to PowerPoint). The project has grown into a full slide catalog, analysis, and library management framework. The name `aippt` matches the repo and better represents the broader capabilities.
- **Who benefits?** All users — cleaner naming, consistent with the repo URL and project identity.
- **What happens if we don't do this?** Continued confusion between the repo name (`aippt`) and the package/command name (`outline2ppt`).

## Requirements

### Must Have

- [ ] Rename `outline2ppt/` package directory to `aippt/`
- [ ] Rename `outline2ppt.py` entry point to `aippt.py`
- [ ] Delete `ppt2outline.py` legacy wrapper
- [ ] Update all Python imports (`from outline2ppt` to `from aippt`)
- [ ] Update `pyproject.toml` package name and CLI entry point
- [ ] Update `cli.py` argparse `prog="aippt"`
- [ ] Update web UI title and nav heading to "AIPPT"
- [ ] Update FastAPI app title to "AIPPT"
- [ ] Update CLAUDE.md with new command examples
- [ ] Update README.md with new command examples
- [ ] Update shell scripts (backup.sh, restore.sh, serve.sh)
- [ ] Update all test file imports
- [ ] All tests pass after rename

### Nice to Have

- [ ] Update CHANGELOG.md references (current and historical)
- [ ] Rename `examples/outline2ppt-overview.md` to `examples/aippt-overview.md`

### Out of Scope

- Renaming historical PRD documents in `docs/plans/` (they are historical records)
- Renaming backup/ directory artifacts
- PyPI publishing considerations
- Backwards compatibility wrappers

---

## Design

### Approach

This is a mechanical rename with three phases:

1. **Directory and file renames**: `outline2ppt/` to `aippt/`, entry point scripts
2. **Find-and-replace**: All Python imports, CLI references, documentation examples
3. **Verification**: Run full test suite, manual smoke test of web UI and CLI

The rename is straightforward because:
- No external consumers depend on the package name (not published to PyPI)
- All imports are internal to the repository
- The project uses `pyproject.toml` with a simple `[project.scripts]` entry

### Rename Mapping

| Old | New | Type |
|-----|-----|------|
| `outline2ppt/` | `aippt/` | Directory rename |
| `outline2ppt.py` | `aippt.py` | File rename |
| `ppt2outline.py` | (deleted) | File delete |
| `from outline2ppt` | `from aippt` | Import (226 occurrences, 43 files) |
| `import outline2ppt` | `import aippt` | Import |
| `outline2ppt.cli:main` | `aippt.cli:main` | pyproject.toml entry point |
| `prog="outline2ppt"` | `prog="aippt"` | CLI prog name |
| `Outline2PPT` | `AIPPT` | User-facing brand (web UI, FastAPI, docs) |
| `outline2ppt.py <cmd>` | `aippt.py <cmd>` | Documentation examples |

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `aippt/` (was `outline2ppt/`) | Renamed | Package directory |
| `aippt/__init__.py` | Modified | Update docstring and module name |
| `aippt/cli.py` | Modified | Update `prog=`, help strings |
| `aippt/web/app.py` | Modified | FastAPI title "AIPPT" |
| `aippt/web/static/index.html` | Modified | Page title, nav heading |
| `aippt.py` (was `outline2ppt.py`) | Renamed + Modified | Update imports |
| `pyproject.toml` | Modified | Package name, CLI entry point |
| All 26 test files | Modified | Update imports |
| `backup.sh`, `restore.sh`, `serve.sh` | Modified | Update command references |
| `CLAUDE.md`, `README.md` | Modified | Update all command examples |

### Data Model Changes

No data model changes.

---

## CLI Changes

### Modified Commands

All commands change from `outline2ppt` to `aippt`:

```bash
# Before
python outline2ppt.py create outline.md template.pptx output.pptx
python outline2ppt.py serve --port 8000
python outline2ppt.py ingest deck.pptx --tags

# After
python aippt.py create outline.md template.pptx output.pptx
python aippt.py serve --port 8000
python aippt.py ingest deck.pptx --tags
```

All subcommands, arguments, and options remain identical. Only the entry point name changes.

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| All pages | Title | `<title>AIPPT</title>` |
| Nav bar | Heading | `<h1>AIPPT</h1>` |

### No New API Endpoints

---

## Testing

### Verification Strategy

Since this is a rename, the primary test is: **do all existing tests pass after the rename?**

1. Rename directory and files
2. Run find-and-replace on all imports
3. Run `python -m pytest tests/ -v` — all 704+ tests must pass
4. Manual smoke test: `python aippt.py serve`, verify web UI loads with "AIPPT" branding

### Rename Validation Script

Before committing, verify no stale references remain:

```bash
# Should return zero results after rename
grep -rn "outline2ppt" --include="*.py" --include="*.toml" --include="*.html" --include="*.sh" . \
  | grep -v docs/plans/ | grep -v backup/ | grep -v .git/
```

---

## Changelog Entry

```markdown
### Changed
- Rebranded from "Outline2PPT" to "AIPPT" — package, CLI, web UI, and all documentation
- Package directory renamed from `outline2ppt/` to `aippt/`
- CLI entry point renamed from `outline2ppt.py` to `aippt.py`
- Removed legacy `ppt2outline.py` wrapper script
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Rename `outline2ppt/` directory to `aippt/` | Directory | -- |
| 2 | Rename `outline2ppt.py` to `aippt.py`, delete `ppt2outline.py` | Root scripts | -- |
| 3 | Find-and-replace all Python imports (`from outline2ppt` to `from aippt`) | All .py files | 1 |
| 4 | Update `pyproject.toml` package name and entry point | `pyproject.toml` | 1 |
| 5 | Update CLI prog name and help strings | `aippt/cli.py` | 3 |
| 6 | Update web UI title, nav heading, FastAPI title | `aippt/web/app.py`, `aippt/web/static/index.html` | 3 |
| 7 | Update shell scripts | `backup.sh`, `restore.sh`, `serve.sh` | 2 |
| 8 | Update CLAUDE.md and README.md | Documentation | 2 |
| 9 | Update all test imports | `tests/*.py` | 3 |
| 10 | Run full test suite and verify | -- | all |
| 11 | Validate no stale references (grep check) | -- | 10 |
| 12 | Update CHANGELOG.md | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Missed occurrences cause import errors — **Mitigation:** Grep validation script (task 11) catches any stragglers. Test suite covers all code paths.
- **Risk:** Git history becomes harder to trace across the rename — **Mitigation:** `git log --follow` handles file renames. Single commit for the rename keeps history clean.
- **Question:** Should this be done as a single atomic commit or broken into smaller commits? — **Recommendation:** Single commit. A partial rename (directory renamed but imports not updated) leaves the project in a broken state.

---

## References

- Package directory: `outline2ppt/` (15 Python modules + `web/` subpackage)
- Entry points: `outline2ppt.py`, `ppt2outline.py`
- Config: `pyproject.toml:2,8`
- CLI prog: `outline2ppt/cli.py:1263`
- Web UI: `outline2ppt/web/static/index.html:6,424`
- FastAPI: `outline2ppt/web/app.py:39`
- Test files: 26 files in `tests/`
