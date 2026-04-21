# PRD: Portable Library Export & Import

**Date:** 2026-03-04
**Author:** Matt
**Status:** Draft

---

## Summary

Extend the project with three connected changes to enable portable slide library sharing between workstations:

1. **`dirs.yaml`** — A standardized directory configuration file that defines where all content directories live (outlines, templates, uploads, output, backups, images, database).
2. **Relative paths in DB** — Change `catalog.py` to store relative paths instead of absolute paths, with a migration for existing data.
3. **`backup.sh` tar.gz export + `restore.sh` import** — Extend `backup.sh` to produce a portable `tar.gz` archive and create `restore.sh` to import it on another machine, enabling view-only library sharing.

## Motivation

- **What problem does this solve?** Deck analysis happens on one workstation (with LLM access), but the resulting catalog needs to be shared with multiple users on other machines for browsing, searching, and reviewing. Currently there is no portable export format, and absolute paths in the database make it impossible to move the library to a different location.
- **Who benefits?** Teams that analyze decks centrally and share the catalog for read-only browsing.
- **What happens if we don't do this?** Libraries are tied to the machine and directory where they were created. Sharing requires manual file copying and database path surgery.

## Requirements

### Must Have

#### dirs.yaml
- [ ] New `dirs.yaml` config file with default directory mappings
- [ ] Default values: `outlines/`, `templates/`, `uploads/`, `output/`, `backups/`, `images/`, `slides.db`
- [ ] New `outline2ppt/config.py` module that loads `dirs.yaml` with defaults
- [ ] CLI commands and `create_app()` read directory paths from config
- [ ] `dirs.yaml` is auto-created with defaults on first run if it doesn't exist

#### Relative Paths
- [ ] `catalog_deck()` stores `file_path` and `image_path` as relative paths (relative to project root)
- [ ] Web app resolves relative paths to absolute at serve time
- [ ] `slide-image` endpoint resolves relative `image_path` before serving
- [ ] Download endpoint resolves relative `file_path` before serving
- [ ] New CLI subcommand `migrate-paths` converts existing absolute paths in the DB to relative
- [ ] Migration is idempotent (running twice is safe)

#### Export / Import
- [ ] `backup.sh --export` produces a `tar.gz` archive in `backups/`
- [ ] Archive contains: `slides.db`, `images/`, `uploads/`, `dirs.yaml`, `dbinfo.json`
- [ ] Archive filename: `outline2ppt-export-YYYY-MM-DD.tar.gz`
- [ ] `restore.sh <archive.tar.gz> [target-dir]` extracts and sets up a working library
- [ ] `restore.sh` creates target directory if needed
- [ ] `restore.sh` updates `dirs.yaml` paths to match the target location
- [ ] After restore, `outline2ppt serve --view-only` works immediately

### Nice to Have

- [ ] `backup.sh --export` runs `migrate-paths` automatically before archiving
- [ ] `restore.sh --serve` starts the view-only server after restore
- [ ] Archive includes a `manifest.json` with export metadata (date, source machine, deck count, slide count)

### Out of Scope

- Incremental/differential exports
- Remote transfer (scp, rsync, S3 upload)
- Merge/sync between two libraries
- Docker container packaging

---

## Design

### dirs.yaml Format

```yaml
# Outline2PPT directory configuration
directories:
  outlines: outlines/
  templates: templates/
  uploads: uploads/
  output: output/
  backups: backups/
  images: images/
  db: slides.db
```

All paths are relative to the project root (the directory containing `dirs.yaml`). Absolute paths are also supported for advanced use cases.

### config.py Module

```python
DEFAULTS = {
    "outlines": "outlines/",
    "templates": "templates/",
    "uploads": "uploads/",
    "output": "output/",
    "backups": "backups/",
    "images": "images/",
    "db": "slides.db",
}

def load_config(config_path="dirs.yaml") -> dict:
    """Load dirs.yaml, falling back to defaults for missing keys."""
    ...

def resolve_path(relative_path: str, base_dir: str = None) -> str:
    """Resolve a relative path to absolute using project root."""
    ...
```

### Relative Path Storage

**Current** (catalog.py:95,197):
```python
deck_path = os.path.abspath(deck_path)        # stores /home/matt/git/.../uploads/deck.pptx
image_path = os.path.abspath(candidate)        # stores /home/matt/git/.../images/deck/Slide1.PNG
```

**New:**
```python
deck_path = os.path.relpath(deck_path, project_root)   # stores uploads/deck.pptx
image_path = os.path.relpath(candidate, project_root)   # stores images/deck/Slide1.PNG
```

**Web app resolution** (routes.py, at serve time):
```python
abs_path = os.path.join(project_root, slide["image_path"])
```

### Migration Command

```bash
python outline2ppt.py migrate-paths [--db slides.db] [--base-dir /home/matt/git/shamsway/aippt]
```

Rewrites all `decks.file_path` and `slides.image_path` values from absolute to relative:
- Detects the common base directory from existing paths (or uses `--base-dir`)
- Applies `os.path.relpath()` to each path
- Skips paths that are already relative
- Reports count of paths updated

### Archive Structure

```
outline2ppt-export-2026-03-04.tar.gz
├── dirs.yaml
├── dbinfo.json
├── slides.db
├── uploads/
│   ├── 44dc98ea..._Deck Name.pptx
│   └── ...
└── images/
    ├── 44dc98ea..._Deck Name/
    │   ├── Slide1.PNG
    │   ├── Slide2.PNG
    │   └── ...
    └── ...
```

### backup.sh Changes

Current behavior (no flags) preserved as-is. New `--export` flag:

```bash
# Existing behavior: copy to backup/ directory
./backup.sh

# New: create portable tar.gz archive
./backup.sh --export

# Output: backups/outline2ppt-export-2026-03-04.tar.gz
```

### restore.sh Flow

```bash
./restore.sh outline2ppt-export-2026-03-04.tar.gz [/path/to/target]
```

1. Validate archive exists and is a tar.gz
2. Create target directory (defaults to current directory)
3. Extract archive to target
4. Verify `slides.db` and `dirs.yaml` exist
5. Print summary: deck count, slide count, total size
6. Print instructions for starting the server

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/config.py` | New | Load `dirs.yaml`, resolve paths, defaults |
| `outline2ppt/catalog.py` | Modified | Store relative paths; add `migrate_paths()` function |
| `outline2ppt/cli.py` | Modified | Add `migrate-paths` subcommand; wire config into existing commands |
| `outline2ppt/web/app.py` | Modified | Load config, resolve paths at serve time |
| `outline2ppt/web/routes.py` | Modified | Resolve relative paths before serving files/images |
| `backup.sh` | Modified | Add `--export` flag for tar.gz creation |
| `restore.sh` | New | Extract archive and set up working library |
| `dirs.yaml` | New | Default directory configuration |

### Data Model Changes

No schema changes. The `file_path` and `image_path` columns store relative paths instead of absolute paths. The column types (TEXT) remain the same.

---

## CLI Changes

### New Commands

| Command | Description |
|---------|-------------|
| `outline2ppt migrate-paths` | Convert absolute DB paths to relative |

### Modified Commands

| Command | Change |
|---------|--------|
| `outline2ppt serve` | Reads `dirs.yaml` for directory config |
| `outline2ppt catalog` | Stores relative paths |
| `outline2ppt ingest` | Stores relative paths |
| `outline2ppt export-images` | Uses `dirs.yaml` images directory default |

---

## UI Changes

No UI changes. Path resolution is transparent to the frontend.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_config.py` | `TestLoadConfig` | Load dirs.yaml, defaults, missing file, absolute paths |
| `tests/test_catalog.py` | `TestRelativePaths` | `catalog_deck()` stores relative paths |
| `tests/test_catalog.py` | `TestMigratePaths` | Migration from absolute to relative, idempotency |

### Test Cases

| Test | Description |
|------|-------------|
| `test_load_config_defaults` | Missing `dirs.yaml` returns all defaults |
| `test_load_config_partial` | Partial `dirs.yaml` fills in missing defaults |
| `test_resolve_path_relative` | Relative path resolved against project root |
| `test_resolve_path_absolute` | Absolute path returned as-is |
| `test_catalog_stores_relative` | New deck cataloged with relative `file_path` |
| `test_image_path_relative` | Image paths stored as relative |
| `test_migrate_absolute_to_relative` | Migration rewrites absolute paths |
| `test_migrate_idempotent` | Running migration twice doesn't break paths |
| `test_migrate_skips_relative` | Already-relative paths are untouched |

### Integration Tests

| Test | Description |
|------|-------------|
| `test_web_serves_relative_images` | `/slide-image/{id}` resolves relative path and serves PNG |
| `test_web_download_relative` | `/api/decks/{id}/download` resolves relative `file_path` |

### Manual Testing

1. Run `migrate-paths` on existing DB -- verify paths converted to relative
2. Start web server -- verify images and downloads still work
3. Run `backup.sh --export` -- verify tar.gz created in `backups/`
4. Extract on a different machine -- run `restore.sh` -- verify `serve --view-only` works
5. Upload a new deck after migration -- verify paths stored as relative

---

## Changelog Entry

```markdown
### Added
- `dirs.yaml` configuration file for standardized directory paths
- `outline2ppt/config.py` module for directory configuration management
- `migrate-paths` CLI command to convert absolute DB paths to relative
- `backup.sh --export` creates portable tar.gz archive
- `restore.sh` imports an archive and sets up a working library

### Changed
- Database paths (`file_path`, `image_path`) now stored as relative paths for portability
- `backup.sh` defaults backup location to `backups/` directory
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Create `dirs.yaml` with defaults | `dirs.yaml` | -- |
| 2 | Create `config.py` module (load, resolve, defaults) | `outline2ppt/config.py` | 1 |
| 3 | Add unit tests for `config.py` | `tests/test_config.py` | 2 |
| 4 | Change `catalog_deck()` to store relative paths | `outline2ppt/catalog.py` | 2 |
| 5 | Add `migrate_paths()` function and CLI subcommand | `outline2ppt/catalog.py`, `outline2ppt/cli.py` | 2 |
| 6 | Add unit tests for relative paths and migration | `tests/test_catalog.py` | 4, 5 |
| 7 | Update web app to resolve relative paths at serve time | `outline2ppt/web/app.py`, `outline2ppt/web/routes.py` | 2, 4 |
| 8 | Add integration tests for web path resolution | `tests/test_web.py` | 7 |
| 9 | Extend `backup.sh` with `--export` flag | `backup.sh` | 1 |
| 10 | Create `restore.sh` | `restore.sh` | 9 |
| 11 | Wire `dirs.yaml` config into CLI commands | `outline2ppt/cli.py` | 2 |
| 12 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Changing path storage is a breaking change for existing databases -- **Mitigation:** `migrate-paths` command provides a clean upgrade path. The web app can detect and handle both absolute and relative paths during the transition.
- **Risk:** Relative path resolution depends on knowing the project root -- **Mitigation:** `config.py` determines project root from the location of `dirs.yaml` or the current working directory.
- **Risk:** Large `images/` directories could make tar.gz archives very large (100s of MB to GBs) -- **Mitigation:** Document expected sizes. Future work could add `--no-images` flag for metadata-only export.
- **Question:** Should `restore.sh` require Python/venv to be installed, or just extract files? -- **Recommendation:** Just extract files. The user is responsible for having the app installed on the target machine. `restore.sh` is a pure bash script.
- **Question:** Should `dirs.yaml` be checked into git or `.gitignore`d? -- **Recommendation:** Check in a `dirs.yaml.example` with defaults. The actual `dirs.yaml` should be in `.gitignore` since it may contain machine-specific paths.

---

## References

- Existing backup script: `backup.sh`
- Path storage in catalog: `outline2ppt/catalog.py:95` (deck_path), `catalog.py:197` (image_path)
- App factory: `outline2ppt/web/app.py:13-31`
- CLI serve command: `outline2ppt/cli.py:722-732`, `1244-1248`
- Image serving: `outline2ppt/web/routes.py` (slide-image endpoint)
- Download endpoint: `outline2ppt/web/routes.py` (deck download)
- DB schema: `outline2ppt/schema.sql:7` (file_path), `schema.sql:27` (image_path)
- Database info: `outline2ppt/cli.py` (db-info subcommand)
