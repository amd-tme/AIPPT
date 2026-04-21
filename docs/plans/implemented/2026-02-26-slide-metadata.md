# PRD: Slide & Deck Metadata (Author, Creation Date, Updated Date)

**Date:** 2026-02-26
**Author:** Matt
**Status:** Draft

---

## Summary

Add author, creation date, and last-updated-date metadata to decks and slides. Author and creation date are populated from the PPTX file properties during ingest, with sensible defaults (blank/null) for unknown values. The updated date is tracked automatically as changes are made to slides through the application.

## Motivation

- **What problem does this solve?** There is no way to know who created a deck or when individual slides were originally authored. The existing `created_at` and `updated_at` fields track when records entered the *catalog*, not when the content was actually created.
- **Who benefits?** End users managing slide libraries who need to track provenance, filter by author, or identify stale content.
- **What happens if we don't do this?** Users cannot distinguish between "when a slide was cataloged" and "when a slide was actually created," and have no author attribution.

## Requirements

### Must Have

- [ ] `author` field on `decks` table — populated from PPTX `core_properties.author` on ingest, defaults to `''` (empty string) if not present
- [ ] `created_date` field on `decks` table — populated from PPTX `core_properties.created` on ingest, defaults to `NULL` if not present in file metadata; falls back to file modification time
- [ ] `modified_date` field on `decks` table — populated from PPTX `core_properties.modified` on ingest, defaults to `NULL` if not present
- [ ] `author` field on `slides` table — inherits from deck author on ingest, defaults to `''`
- [ ] `slide_created_date` field on `slides` table — set to deck's `created_date` on initial ingest (best available approximation), defaults to `NULL`
- [ ] `slides.updated_at` continues to be updated automatically when slide data changes (already exists)
- [ ] Display author and dates in the web UI (deck list, slide detail modal)
- [ ] API responses include the new metadata fields
- [ ] Schema migration adds columns with defaults so existing databases are not broken

### Nice to Have

- [ ] Edit author field from web UI
- [ ] Filter/sort decks by author in the UI
- [ ] Show "last modified by" when a slide is updated through the app (future: track per-operation author)

### Out of Scope

- Per-slide author tracking from PPTX (PowerPoint does not store per-slide authors in a standard way)
- Version history / audit log of who changed what
- Extracting author from revision history or comments

---

## Design

### Approach

Extend `catalog_deck()` to read PPTX `core_properties` (already available via `python-pptx`'s `Presentation.core_properties`) during ingest. Store the extracted metadata in new columns on `decks` and `slides`. For slides, author and creation date are inherited from the deck level since PPTX does not provide per-slide authorship.

Default values follow the user's specification:
- **Author:** empty string `''` when unknown
- **Dates:** `NULL` when unknown (not a synthetic date)
- **Fallback for creation date:** file system modification time (`os.path.getmtime()`) if PPTX metadata is missing

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/schema.sql` | Modified | Add `author`, `created_date`, `modified_date` to `decks`; add `author` and `slide_created_date` to `slides` |
| `outline2ppt/catalog.py` | Modified | Extract `core_properties` in `catalog_deck()`, populate new columns |
| `outline2ppt/web/routes.py` | Modified | Include new fields in `GET /api/decks` and `GET /api/slides/{id}` responses |
| `outline2ppt/web/static/index.html` | Modified | Display author and dates in deck list table and slide detail modal |
| `outline2ppt/export.py` | Modified | Include author and dates in CSV export |

### Data Model Changes

New columns added to existing tables:

```sql
-- Decks: add author and source-file dates
ALTER TABLE decks ADD COLUMN author TEXT NOT NULL DEFAULT '';
ALTER TABLE decks ADD COLUMN created_date TEXT DEFAULT NULL;
ALTER TABLE decks ADD COLUMN modified_date TEXT DEFAULT NULL;

-- Slides: add author and original creation date
ALTER TABLE slides ADD COLUMN author TEXT NOT NULL DEFAULT '';
ALTER TABLE slides ADD COLUMN slide_created_date TEXT DEFAULT NULL;
```

The `schema.sql` CREATE TABLE statements will be updated to include these columns for new databases. For existing databases, the `ALTER TABLE` statements will be applied via a migration check in `get_db()`.

**Column semantics:**
| Column | Source | Default | Updated When |
|--------|--------|---------|-------------|
| `decks.author` | `core_properties.author` | `''` | Ingest / re-catalog |
| `decks.created_date` | `core_properties.created` or file mtime | `NULL` | Ingest only (immutable) |
| `decks.modified_date` | `core_properties.modified` | `NULL` | Ingest / re-catalog |
| `slides.author` | Inherited from `decks.author` | `''` | Ingest / re-catalog |
| `slides.slide_created_date` | Inherited from `decks.created_date` | `NULL` | Ingest only (immutable) |
| `slides.updated_at` | (existing) Auto-set | `datetime('now')` | Any slide modification |

---

## CLI Changes

No new CLI commands or options. The metadata is automatically extracted during the existing `catalog` command. Existing `catalog` and `analyze` commands will populate the new fields without any flag changes.

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Deck List | Add Author column | Show `decks.author` (or "Unknown" if blank) |
| Deck List | Add Created column | Show `decks.created_date` formatted as date |
| Slide Detail Modal | Show metadata section | Author, created date, last updated |

### Wireframe / Mockup

**Deck list with new columns:**
```
┌──────────────────┬────────┬──────────┬────────────┬────────────┐
│  Name            │ Slides │ Author   │ Created    │ Updated    │
├──────────────────┼────────┼──────────┼────────────┼────────────┤
│  Q4 Strategy     │   12   │ J. Smith │ 2026-01-15 │ 2026-02-20 │
│  Product Launch  │    8   │          │ 2026-02-10 │ 2026-02-25 │
│  Team Onboard    │   15   │ A. Lee   │            │ 2026-02-26 │
└──────────────────┴────────┴──────────┴────────────┴────────────┘
```

**Slide detail modal metadata section:**
```
┌─────────────────────────────────────────┐
│  Slide 3: Key Metrics                   │
│  ─────────────────────────────────────  │
│  Author: J. Smith                       │
│  Created: 2026-01-15                    │
│  Last Updated: 2026-02-20 14:32         │
│  ─────────────────────────────────────  │
│  [slide image]                          │
│  ...                                    │
└─────────────────────────────────────────┘
```

Blank/null values render as empty cells in the table and "—" in the detail modal.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_catalog.py` | `TestCatalogMetadata` | Verify author, created_date, modified_date extraction from PPTX core_properties |
| `tests/test_catalog.py` | `TestCatalogMetadataDefaults` | Verify defaults when core_properties are missing/empty |
| `tests/test_catalog.py` | `TestCatalogMetadataFallback` | Verify file mtime fallback for creation date |

### Integration Tests

Add to `tests/test_integration.py`:
- Catalog a deck with full core_properties, verify all metadata fields populated in DB
- Catalog a deck with empty core_properties, verify defaults applied
- Re-catalog a deck with changed author, verify author updates but `created_date` is preserved
- Verify API responses include metadata fields
- Verify CSV export includes metadata fields

### Manual Testing

1. Catalog a deck with known author in file properties — verify author shows in deck list and slide detail
2. Catalog a deck with no file properties — verify blank/null defaults display correctly
3. Re-catalog same deck after editing it — verify `modified_date` updates, `created_date` preserved
4. Check CSV export includes author and date columns

---

## Changelog Entry

```markdown
### Added
- Deck metadata: author, creation date, and modified date extracted from PPTX file properties during catalog
- Slide metadata: author (inherited from deck) and creation date displayed in slide detail view
- Web UI: Author and date columns in deck list table
- Web UI: Metadata section in slide detail modal
- CSV export: Author and date columns included

### Changed
- `catalog_deck()` now reads PPTX `core_properties` for metadata extraction
- Database schema updated with new columns (backward-compatible with defaults)
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add new columns to schema.sql and migration logic in get_db() | `schema.sql`, `catalog.py` | -- |
| 2 | Extract core_properties in catalog_deck() and populate new columns | `catalog.py` | 1 |
| 3 | Include metadata fields in API responses | `routes.py` | 1 |
| 4 | Display metadata in deck list and slide detail modal | `index.html` | 3 |
| 5 | Include metadata in CSV export | `export.py` | 1 |
| 6 | Add unit tests for metadata extraction and defaults | `tests/test_catalog.py` | 2 |
| 7 | Add integration tests for API and export | `tests/test_integration.py` | 3, 5 |
| 8 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Existing databases lack the new columns — mitigate with `ALTER TABLE` migration in `get_db()` that runs idempotently (check if column exists before adding).
- **Risk:** `core_properties.created` may be `None` on some PPTX files (especially those generated programmatically) — mitigate with file mtime fallback and `NULL` default.
- **Risk:** File mtime fallback for creation date is unreliable (file copies reset mtime) — acceptable as a best-effort approximation; the field can always be `NULL`.
- **Question:** Should `slides.author` be independently editable, or always inherited from deck? — Recommend inherited-only for v1, since PPTX has no per-slide author concept. Future PRD can add per-slide override if needed.

---

## References

- python-pptx core_properties: `Presentation.core_properties` provides `.author`, `.created`, `.modified`, `.title`, `.subject`, `.keywords`
- Related PRDs: `docs/plans/2026-02-26-web-file-management.md`
- Existing schema: `outline2ppt/schema.sql`
- Existing ingest: `outline2ppt/catalog.py:catalog_deck()`
- PRD Template: `docs/plans/PRD-TEMPLATE.md`
