# PRD: Data Model v2 — Schema Evolution, Edit History & Migration Process

**Date:** 2026-03-02
**Author:** Matt
**Status:** Draft

---

## Summary

Evolve the SQLite schema to capture additional PPTX metadata at ingest, record the layout type for generated slides, and introduce a lightweight edit history table. Establish a documented migration process so future schema changes are safe, testable, and predictable.

## Motivation

- **What problem does this solve?** The current schema was grown organically — metadata columns were added via ad-hoc `ALTER TABLE` migrations in `get_db()`. There is no edit history, so web UI changes to notes (or future editable fields) silently overwrite previous values. Additional PPTX `core_properties` fields (`subject`, `description`) are available at ingest but discarded. Layout type is determined during enhancement but not persisted, forcing the improve pipeline to guess.
- **Who benefits?** End users get richer metadata for search and filtering. Developers get a documented migration process and a schema changelog. The improve pipeline benefits from knowing the layout type. Web UI editing (starting with notes) gets an audit trail.
- **What happens if we don't do this?** Schema drift continues, metadata is lost at ingest, web edits have no undo history, and every future PRD that touches the schema must re-invent migration logic.

## Requirements

### Must Have

- [ ] Add `subject` and `description` columns to `decks` table, populated from `core_properties` at ingest
- [ ] Add `layout_type` column to `slides` table, populated during enhanced creation (nullable for externally ingested slides)
- [ ] Create `edit_history` table for append-only change tracking
- [ ] Idempotent migration logic in `get_db()` for all new columns/tables
- [ ] Update `catalog_deck()` to extract and store `subject` and `description`
- [ ] Update enhance/create pipeline to persist `layout_type` on generated slides
- [ ] Update `get_deck_by_id()`, `list_decks()`, and API endpoints to include new deck fields
- [ ] Update CSV export to include new fields
- [ ] Schema documentation: maintain `schema.sql` as the canonical reference with inline comments
- [ ] Unit tests for migration logic (verify columns added idempotently)
- [ ] Unit tests for new metadata extraction

### Nice to Have

- [ ] `layout_type` detection for externally ingested slides (heuristic based on placeholder count/type)
- [ ] Schema version table (`schema_version`) for tracking applied migrations by number
- [ ] CLI command `outline2ppt schema-info` to display current schema version and column inventory

### Out of Scope

- Relative path storage (file_path/image_path) — separate concern requiring config changes
- Per-slide author override editing — future PRD when web editing expands
- Deck-level tags — no current consumer
- Layout parameter storage (column headers, etc.) — only relevant during generation

---

## Design

### Approach

Extend the existing pattern: `schema.sql` defines the full schema for new databases; `get_db()` runs idempotent `ALTER TABLE` / `CREATE TABLE IF NOT EXISTS` for existing databases. New metadata fields are populated at their natural extraction points — `catalog_deck()` for PPTX properties, the create/enhance pipeline for layout type.

The `edit_history` table is append-only and decoupled from the core tables. Writing history entries is the responsibility of the code that performs the mutation (e.g., the notes save endpoint), not a database trigger. This keeps the write path explicit and testable.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/schema.sql` | Modified | Add `subject`, `description` to `decks`; add `layout_type` to `slides`; add `edit_history` table and index |
| `outline2ppt/catalog.py` | Modified | `get_db()`: add migration for new columns. `catalog_deck()`: extract `subject` and `description` from `core_properties`. `get_deck_by_id()` and `list_decks()`: include new fields in SELECT. |
| `outline2ppt/layouts.py` | Modified | Return layout type string from `select_layout()` / `apply_*_layout()` so the caller can persist it |
| `outline2ppt/enhancer.py` | Modified | Pass layout type through to slide creation; store on slide record after insert |
| `outline2ppt/export.py` | Modified | Add `subject`, `description`, `layout_type` to CSV columns |
| `outline2ppt/web/routes.py` | Modified | Include new fields in deck and slide API responses |

### Data Model Changes

#### New columns on existing tables

```sql
-- decks: additional core_properties fields
ALTER TABLE decks ADD COLUMN subject TEXT NOT NULL DEFAULT '';
ALTER TABLE decks ADD COLUMN description TEXT NOT NULL DEFAULT '';

-- slides: layout classification from enhance pipeline
ALTER TABLE slides ADD COLUMN layout_type TEXT DEFAULT NULL;
```

#### New table: edit_history

```sql
CREATE TABLE IF NOT EXISTS edit_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slide_id INTEGER NOT NULL REFERENCES slides(id) ON DELETE CASCADE,
    field TEXT NOT NULL,                     -- 'notes', 'title', 'tags', etc.
    old_value TEXT,
    new_value TEXT,
    source TEXT NOT NULL DEFAULT 'web',      -- 'web', 'cli', 'ingest', 'ai'
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_edit_history_slide ON edit_history(slide_id);
```

#### Column semantics

| Column | Source | Default | Updated When |
|--------|--------|---------|-------------|
| `decks.subject` | `core_properties.subject` | `''` | Ingest / re-catalog |
| `decks.description` | `core_properties.description` | `''` | Ingest / re-catalog |
| `slides.layout_type` | Enhance pipeline | `NULL` | Initial creation only |
| `edit_history.*` | Write endpoints | n/a | Any field mutation via web/CLI |

#### Migration process

All migrations run inside `get_db()` using the existing pattern:

```python
existing_deck_cols = {
    row[1] for row in conn.execute("PRAGMA table_info(decks)").fetchall()
}
for col_ddl, col_name in (
    # ... existing migrations ...
    ("subject TEXT NOT NULL DEFAULT ''", "subject"),
    ("description TEXT NOT NULL DEFAULT ''", "description"),
):
    if col_name not in existing_deck_cols:
        conn.execute(f"ALTER TABLE decks ADD COLUMN {col_ddl}")

existing_slide_cols = {
    row[1] for row in conn.execute("PRAGMA table_info(slides)").fetchall()
}
for col_ddl, col_name in (
    # ... existing migrations ...
    ("layout_type TEXT DEFAULT NULL", "layout_type"),
):
    if col_name not in existing_slide_cols:
        conn.execute(f"ALTER TABLE slides ADD COLUMN {col_ddl}")

# edit_history is handled by CREATE TABLE IF NOT EXISTS in schema.sql
```

This is idempotent — safe to run against any database version, from empty to current.

---

## CLI Changes

No new CLI commands or options. All changes are internal to existing commands:
- `catalog` / `ingest` will populate `subject` and `description` automatically
- `create --enhance` will persist `layout_type` automatically
- `export` CSV output will include new columns

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Deck List | Show subject if non-empty | Displayed as subtitle under deck name |
| Slide Detail Modal | Show layout type badge | e.g., "two_column" shown as a small label if non-null |

### Modified API Responses

| Endpoint | New Fields |
|----------|-----------|
| `GET /api/decks` | `subject`, `description` added to each deck object |
| `GET /api/decks/{id}/slides` | `layout_type` added to each slide object |
| `GET /api/slides/{id}` | `layout_type` added |

No new API endpoints required for this PRD. The `edit_history` table is written to by existing mutation endpoints (notes save, tag add/remove) but is not exposed via its own read endpoint yet (future: history/undo PRD).

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_catalog.py` | `TestMigrationIdempotent` | Run `get_db()` twice on same DB; verify no errors, columns present |
| `tests/test_catalog.py` | `TestMigrationFromScratch` | Run `get_db()` on empty DB; verify all columns present |
| `tests/test_catalog.py` | `TestCatalogSubjectDescription` | Catalog PPTX with subject/description set; verify stored correctly |
| `tests/test_catalog.py` | `TestCatalogSubjectDescriptionDefaults` | Catalog PPTX without subject/description; verify empty string defaults |
| `tests/test_catalog.py` | `TestEditHistoryTable` | Verify table exists after `get_db()`; insert and read back a row |
| `tests/test_export.py` | `TestExportNewColumns` | Verify CSV output includes subject, description, layout_type columns |

### Integration Tests

Add to `tests/test_integration.py`:
- Catalog a deck, verify `subject` and `description` in DB match PPTX core_properties
- Verify `GET /api/decks` response includes `subject` and `description`
- Verify `GET /api/slides/{id}` response includes `layout_type`
- Create a deck with `--enhance`, verify `layout_type` is set on generated slides
- Verify CSV export contains new columns with correct values

### Manual Testing

1. Open existing `slides.db`, start web server — verify no migration errors, new columns appear
2. Catalog a deck with populated Subject/Description in file properties — verify values appear in `GET /api/decks`
3. Catalog a deck without Subject/Description — verify empty strings in response
4. Run `export --all` — verify new columns in CSV output
5. Delete `slides.db`, re-catalog — verify clean schema with all columns

---

## Changelog Entry

```markdown
### Added
- Database: `subject` and `description` columns on `decks` table, populated from PPTX core_properties
- Database: `layout_type` column on `slides` table, populated during enhanced deck creation
- Database: `edit_history` table for tracking field changes (append-only audit log)
- CSV export: `subject`, `description`, and `layout_type` columns
- API: New fields in deck and slide responses

### Changed
- `catalog_deck()` extracts `subject` and `description` from PPTX core_properties
- Schema migration in `get_db()` extended with new columns (backward-compatible)
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add new columns and `edit_history` table to `schema.sql` | `schema.sql` | -- |
| 2 | Add migration logic for new columns in `get_db()` | `catalog.py` | 1 |
| 3 | Extract `subject` and `description` in `catalog_deck()` | `catalog.py` | 2 |
| 4 | Include new deck fields in `get_deck_by_id()` and `list_decks()` | `catalog.py` | 2 |
| 5 | Return layout type from layout application functions | `layouts.py` | -- |
| 6 | Persist `layout_type` during enhanced deck creation | `enhancer.py` | 2, 5 |
| 7 | Include new fields in API responses | `routes.py` | 4 |
| 8 | Add new columns to CSV export | `export.py` | 2 |
| 9 | Add migration and metadata extraction tests | `tests/test_catalog.py` | 3 |
| 10 | Add export tests for new columns | `tests/test_export.py` | 8 |
| 11 | Add integration tests | `tests/test_integration.py` | 7, 8 |
| 12 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** `core_properties.subject` and `.description` may be None on many files — mitigate with `(cp.subject or "").strip()` pattern, same as existing author extraction.
- **Risk:** `layout_type` is only set for decks created via `--enhance`. Externally ingested decks will have `NULL` for all slides — this is acceptable; the field is informational. A future heuristic could classify existing slides, but that's out of scope.
- **Risk:** `edit_history` grows unbounded — mitigate later with a retention policy or periodic cleanup. For the current scale (hundreds of slides, occasional edits), this is not a concern.
- **Question:** Should `edit_history` track deck-level field changes (e.g., editing deck description in a future PRD)? — Recommend adding a nullable `deck_id` column now to avoid a migration later. **Decision: defer** — keep it slide-scoped for v1; add `deck_id` when a deck editing PRD arrives.
- **Question:** Should the enhance pipeline set `layout_type` on the catalog DB record, or on the PPTX slide as a custom property? — Recommend DB only. Custom PPTX properties would be overwritten on re-catalog and aren't useful outside our system.

---

## References

- Related PRDs: `docs/plans/2026-02-26-slide-metadata.md` (author/dates — already implemented)
- Related PRDs: `docs/plans/2026-02-26-web-file-management.md` (upload/download — already implemented)
- Related PRDs: `docs/plans/2026-03-02-web-notes-editing.md` (first consumer of edit_history)
- Future work: `docs/plans/2026-03-02-test-results-and-future-work.md`
- Existing schema: `outline2ppt/schema.sql`
- Existing migrations: `outline2ppt/catalog.py:get_db()`
- python-pptx core_properties: `.subject`, `.description`, `.keywords`, `.category`, `.comments`
- PRD Template: `docs/plans/PRD-TEMPLATE.md`
