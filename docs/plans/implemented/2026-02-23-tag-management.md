# PRD: Tag Management

**Date:** 2026-02-23
**Author:** Matt Elliott
**Status:** Draft

---

## Summary

Add full tag lifecycle management -- create, edit, delete tags on slides, and manage a persistent taxonomy of predefined tags. Today, tags can be added (manually or via AI) but never removed, renamed, or organized. The taxonomy table exists in the schema but is never populated. This feature fills those gaps with CLI commands, API endpoints, and web UI for both taxonomy administration and per-slide tag management.

## Motivation

- **Problem:** Tags can only be added, never removed or renamed. The taxonomy is loaded from a CSV at analysis time but not persisted, so there is no single source of truth for allowed tags. The web UI can add a tag to a slide but can't remove one.
- **Who benefits:** Users who curate slide libraries and need consistent, well-organized metadata across decks.
- **What happens if we don't do this:** Tag lists grow unbounded with typos and duplicates. Users must manually edit the SQLite database or re-catalog to fix tagging mistakes. The taxonomy table remains unused.

## Requirements

### Must Have

- [ ] Persist taxonomy to the `taxonomy` table in SQLite (not just ephemeral CSV loading)
- [ ] CLI commands to list, add, and remove taxonomy tags
- [ ] CLI commands to add and remove tags from a specific slide
- [ ] Import taxonomy from CSV into the database (existing `load_taxonomy` CSV format)
- [ ] Export taxonomy from the database to CSV
- [ ] Web UI: taxonomy management view (list, add, remove tags; organized by category)
- [ ] Web UI: remove individual tags from a slide in the slide detail dialog
- [ ] API endpoints for taxonomy CRUD and per-slide tag add/remove
- [ ] `analyze --mode tags` uses DB taxonomy when no `--taxonomy` CSV is provided

### Nice to Have

- [ ] Tag rename (updates all slide associations)
- [ ] Tag autocomplete in web UI (suggest from taxonomy when adding tags manually)
- [ ] Tag usage counts displayed in taxonomy view
- [ ] Bulk tag/untag: apply or remove a tag across multiple slides from search results

### Out of Scope

- Tag hierarchies or parent-child relationships
- Tag-based access control or permissions
- OR/NOT logic in tag search (current AND logic stays)
- Automated tagging rules or triggers

---

## Design

### Approach

Populate and manage the existing `taxonomy` table as the authoritative list of predefined tags. Add `remove_tags` and `remove_tag_from_slide` functions to `catalog.py`. Add a `tags` CLI subcommand (similar to the `models` subcommand from the model management PRD) for taxonomy operations, and a `tag` / `untag` pair for per-slide operations. Extend the web UI slide detail dialog with tag removal, and add a Taxonomy management section to the Settings page.

### Taxonomy vs. Tags

These are related but distinct concepts:

| Concept | Table | Purpose |
|---------|-------|---------|
| **Taxonomy** | `taxonomy` | The master list of allowed/suggested tags, organized by category. Managed by the user. Fed to the LLM during constrained tagging. |
| **Tags** | `tags` + `slide_tags` | Actual tags applied to slides. May come from taxonomy, AI freeform, or manual entry. |

When `analyze --mode tags` runs without a `--taxonomy` CSV flag, it checks the `taxonomy` table. If populated, it uses those tags to constrain the LLM. If empty, it falls back to freeform tagging.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/catalog.py` | Modified | Add `remove_slide_tag`, `list_taxonomy`, `add_taxonomy_tags`, `remove_taxonomy_tag`, `import_taxonomy_csv`, `export_taxonomy_csv`, `rename_tag` |
| `outline2ppt/analyze.py` | Modified | Fall back to DB taxonomy when no CSV provided |
| `outline2ppt/cli.py` | Modified | Add `tags` subcommand (taxonomy CRUD), add `tag`/`untag` subcommands (per-slide) |
| `outline2ppt/web/routes.py` | Modified | Add taxonomy and tag-removal endpoints |
| `outline2ppt/web/static/index.html` | Modified | Add taxonomy view to Settings, add tag removal to slide detail |

### Data Model Changes

No schema changes needed. The `taxonomy` table already exists with the right structure:

```sql
CREATE TABLE taxonomy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT ''
);
```

Currently this table is never populated. This feature populates and manages it.

---

## CLI Changes

### New Commands

**Taxonomy management (`tags` subcommand):**

```
outline2ppt tags                                    # List all taxonomy tags (grouped by category)
outline2ppt tags add <tag> [--category <category>]  # Add a tag to the taxonomy
outline2ppt tags remove <tag>                       # Remove a tag from the taxonomy
outline2ppt tags import <csv_file>                  # Import taxonomy from CSV
outline2ppt tags export <csv_file>                  # Export taxonomy to CSV
outline2ppt tags rename <old_name> <new_name>       # Rename a tag in taxonomy and all slide associations
```

**Per-slide tag management (`tag` / `untag` subcommands):**

```
outline2ppt tag <slide_id> <tag1,tag2,...>           # Add tags to a slide
outline2ppt untag <slide_id> <tag1,tag2,...>         # Remove tags from a slide
outline2ppt untag <slide_id> --all                  # Remove all tags from a slide
```

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `outline2ppt analyze --mode tags` | Taxonomy fallback | Uses DB taxonomy when no `--taxonomy` CSV flag is provided; CSV flag still overrides |

### Example Usage

```bash
# --- Taxonomy management ---

# Import taxonomy from CSV
python outline2ppt.py tags import tags.csv
# Output: Imported 24 tags (8 new, 16 existing)

# List taxonomy
python outline2ppt.py tags
# Output:
#   Category: topic
#     security, cloud, networking, storage, compute
#   Category: audience
#     executive, technical, sales
#   Category: (uncategorized)
#     overview, demo

# Add a tag
python outline2ppt.py tags add "zero-trust" --category security
# Output: Added 'zero-trust' to taxonomy (category: security)

# Remove a tag
python outline2ppt.py tags remove "overview"
# Output: Removed 'overview' from taxonomy

# Export taxonomy to CSV
python outline2ppt.py tags export my-taxonomy.csv
# Output: Exported 25 tags to my-taxonomy.csv

# Rename a tag
python outline2ppt.py tags rename "cloud" "cloud-computing"
# Output: Renamed 'cloud' -> 'cloud-computing' (updated 12 slide associations)

# --- Per-slide tagging ---

# Add tags to a slide
python outline2ppt.py tag 42 "security,zero-trust"
# Output: Tagged slide 42: security, zero-trust

# Remove a tag from a slide
python outline2ppt.py untag 42 "zero-trust"
# Output: Untagged slide 42: zero-trust

# Remove all tags from a slide
python outline2ppt.py untag 42 --all
# Output: Removed all tags from slide 42

# --- Analyze now uses DB taxonomy automatically ---
python outline2ppt.py analyze deck.pptx --mode tags --images-dir images/
# Uses taxonomy table if populated; freeform if empty

# CSV flag still overrides DB taxonomy
python outline2ppt.py analyze deck.pptx --mode tags --taxonomy custom.csv --images-dir images/
```

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Nav bar (Settings) | Taxonomy section | Add taxonomy management below model defaults in Settings view |
| Slide detail dialog | Tag removal | Add "x" button on each tag badge to remove it |
| Slide detail dialog | Tag autocomplete | Suggest taxonomy tags when typing in the add-tag input |

### New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/taxonomy` | List all taxonomy tags grouped by category |
| POST | `/api/taxonomy` | Add a tag to the taxonomy |
| DELETE | `/api/taxonomy/{tag_name}` | Remove a tag from the taxonomy |
| PUT | `/api/taxonomy/{tag_name}` | Rename a taxonomy tag (updates slide associations) |
| POST | `/api/taxonomy/import` | Import taxonomy from uploaded CSV |
| GET | `/api/taxonomy/export` | Export taxonomy as CSV download |
| DELETE | `/api/slides/{slide_id}/tags/{tag_name}` | Remove a specific tag from a slide |

### Wireframe / Mockup

**Settings page -- Taxonomy section (below Model Defaults):**

```
+----------------------------------------------------------+
| Outline2PPT           Decks  Search  Settings  Export CSV |
+----------------------------------------------------------+
|                                                          |
| Model Defaults                                           |
| (... from model management PRD ...)                      |
|                                                          |
| ──────────────────────────────────────────────            |
|                                                          |
| Taxonomy                              [Import CSV]       |
|                                       [Export CSV]       |
|                                                          |
| Add tag: [_______________] Category: [___________] [Add] |
|                                                          |
| topic                                                    |
|   security [x]  cloud [x]  networking [x]  compute [x]  |
|                                                          |
| audience                                                 |
|   executive [x]  technical [x]  sales [x]                |
|                                                          |
| (uncategorized)                                          |
|   overview [x]  demo [x]                                 |
|                                                          |
+----------------------------------------------------------+
```

**Slide detail dialog -- tag removal:**

```
+------------------------------------------------------+
|  [x] Slide 5: Zero Trust Architecture                |
|                                                      |
|  [slide image]                                       |
|                                                      |
|  Tags:                                               |
|    [security x] [architecture x] [zero-trust x]     |
|                                                      |
|  Add tag: [______________|v] [Add Tag]               |
|           ^-- dropdown suggests taxonomy tags        |
|                                                      |
|  > Speaker Notes                                     |
+------------------------------------------------------+
```

Clicking the "x" on a tag badge calls `DELETE /api/slides/{id}/tags/{name}` and removes the badge. The add-tag input suggests matching taxonomy tags as the user types.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_catalog.py` | `TestTagRemoval` | `remove_slide_tag`, remove nonexistent tag, remove all tags |
| `tests/test_catalog.py` | `TestTaxonomy` | `list_taxonomy`, `add_taxonomy_tags`, `remove_taxonomy_tag`, `import_taxonomy_csv`, `export_taxonomy_csv`, `rename_tag` |
| `tests/test_analyze.py` | `TestTaxonomyFallback` | DB taxonomy used when no CSV; CSV overrides DB; empty DB falls back to freeform |

### Integration Tests

Add to `tests/test_integration.py`:
- `test_taxonomy_import_list_export_roundtrip` -- import CSV, list, export, compare
- `test_tag_untag_slide_cli` -- CLI `tag` and `untag` commands
- `test_tags_add_remove_cli` -- CLI taxonomy `add` and `remove`
- `test_analyze_uses_db_taxonomy` -- analyze with populated taxonomy table, no CSV flag

### Manual Testing

1. Import a taxonomy CSV via CLI -- verify tags appear in DB and in web UI Settings
2. Add a taxonomy tag via web UI -- verify it appears in CLI `tags` output
3. Remove a taxonomy tag via web UI -- verify it's gone from CLI `tags` output
4. Open slide detail, click "x" on a tag -- verify tag is removed from the slide
5. Type in the add-tag input -- verify taxonomy suggestions appear
6. Run `analyze --mode tags` without `--taxonomy` flag with a populated taxonomy table -- verify LLM uses the DB taxonomy
7. Run `analyze --mode tags --taxonomy custom.csv` -- verify CSV overrides DB taxonomy
8. Rename a tag via CLI -- verify all slide associations update

---

## Changelog Entry

```markdown
### Added
- Taxonomy management: `outline2ppt tags` CLI commands to list, add, remove, import, export, and rename taxonomy tags
- Per-slide tag management: `outline2ppt tag` and `outline2ppt untag` CLI commands
- Tag removal in web UI slide detail dialog (click "x" on tag badge)
- Taxonomy management section in web UI Settings page
- Tag autocomplete from taxonomy in web UI
- `/api/taxonomy` and `/api/slides/{id}/tags/{name}` API endpoints

### Changed
- `analyze --mode tags` now uses the database taxonomy table when no `--taxonomy` CSV is provided
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add taxonomy CRUD functions to `catalog.py` (`list_taxonomy`, `add_taxonomy_tags`, `remove_taxonomy_tag`, `import_taxonomy_csv`, `export_taxonomy_csv`) | `outline2ppt/catalog.py` | -- |
| 2 | Add `remove_slide_tag` and `rename_tag` functions to `catalog.py` | `outline2ppt/catalog.py` | -- |
| 3 | Add `tags` subcommand to CLI (list, add, remove, import, export, rename) | `outline2ppt/cli.py` | 1, 2 |
| 4 | Add `tag` and `untag` subcommands to CLI | `outline2ppt/cli.py` | 2 |
| 5 | Update `analyze --mode tags` to fall back to DB taxonomy | `outline2ppt/analyze.py`, `outline2ppt/cli.py` | 1 |
| 6 | Add taxonomy API endpoints (GET/POST/DELETE/PUT `/api/taxonomy`, import/export) | `outline2ppt/web/routes.py` | 1 |
| 7 | Add tag removal endpoint (`DELETE /api/slides/{id}/tags/{name}`) | `outline2ppt/web/routes.py` | 2 |
| 8 | Add taxonomy management UI to Settings page | `outline2ppt/web/static/index.html` | 6 |
| 9 | Add tag removal ("x" buttons) and autocomplete to slide detail dialog | `outline2ppt/web/static/index.html` | 7 |
| 10 | Add unit tests for taxonomy and tag removal functions | `tests/test_catalog.py` | 1, 2 |
| 11 | Add integration tests for CLI commands and analyze fallback | `tests/test_integration.py` | 3, 4, 5 |
| 12 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Renaming a tag that exists with different sources (ai, manual, taxonomy) in the `tags` table -- the `tags.name` column has a UNIQUE constraint, so rename must update the single row and all `slide_tags` references follow via foreign key. Straightforward.
- **Risk:** Importing a large taxonomy CSV could create many tags that clutter autocomplete -- mitigated by category grouping and alphabetical ordering.
- **Question:** Should removing a taxonomy tag also remove it from all slides that have it? Recommend no -- taxonomy removal means "stop suggesting this tag," but existing slide tags remain. The user can bulk-untag separately if needed.
- **Question:** Should the `tag` / `untag` CLI commands accept slide IDs or also support selectors like `--deck` + `--position`? Slide ID is simpler and consistent with the API. Users can find slide IDs via `search`. Recommend slide ID only for v1, with deck+position as a nice-to-have.
- **Question:** CSV import behavior for existing tags -- should it skip, update category, or error? Recommend upsert: insert new tags, update category on existing ones. Print a summary (e.g., "8 new, 16 updated").

---

## References

- Existing design: `docs/plans/2026-02-18-outline2ppt-v2-design.md` (Section 6: Tagging System)
- Model management PRD: `docs/plans/2026-02-23-model-management.md`
- Schema: `outline2ppt/schema.sql` (tags, slide_tags, taxonomy tables)
- Current tag functions: `outline2ppt/catalog.py` (add_tags, get_slide_tags, search_slides)
- Current taxonomy loading: `outline2ppt/analyze.py` (load_taxonomy)
