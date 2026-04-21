# PRD: Tag Browsing Sidebar

**Date:** 2026-03-04
**Author:** Matt
**Status:** Draft

---

## Summary

Add a toggleable sidebar panel to the web UI that displays all tags in use across ingested decks, grouped by taxonomy category, with slide counts. Clicking tags filters the main content area using multi-select AND logic, letting users discover and browse slides by tag across the entire library without needing the search form.

## Motivation

- **What problem does this solve?** Users have no way to discover or browse by tags. The only tag interaction is typing comma-separated names into the search box — you need to already know the tag name. There's no visibility into what tags exist or how many slides have each tag.
- **Who benefits?** End users browsing a slide library, especially when exploring unfamiliar decks.
- **What happens if we don't do this?** Tags remain a hidden feature — users must memorize tag names and use the search form to filter by them.

## Requirements

### Must Have

- [ ] New API endpoint `GET /api/tags` returning all tags used on slides, with slide counts
- [ ] Toggleable sidebar panel showing tags grouped by taxonomy category
- [ ] Uncategorized tags shown in an "Other" group
- [ ] Each tag displays its slide count as a badge
- [ ] Multi-select: clicking a tag toggles its selection state
- [ ] AND logic: when multiple tags are selected, only slides with ALL selected tags are shown
- [ ] Tag filter applies to the slide grid (filtered across all decks)
- [ ] "Clear all" button to reset tag selection
- [ ] Sidebar toggle button in the top navigation bar

### Nice to Have

- [ ] Tag counts update dynamically as tags are selected (showing intersection counts)
- [ ] Persist sidebar open/closed state in localStorage
- [ ] Collapse/expand individual category groups

### Out of Scope

- Tag cloud visualization (word cloud with size scaling)
- Tag editing/management from the sidebar (use Settings > Taxonomy for that)
- OR logic mode toggle

---

## Design

### Approach

Add a `GET /api/tags` endpoint in `routes.py` that queries the `tags` + `slide_tags` tables to return all tags with slide counts, grouped by category from the `taxonomy` table. The frontend renders a sidebar panel that sits alongside the main content area. When tags are selected, a new fetch to `/api/search?tags=...` retrieves matching slides and displays them in the main grid, replacing the deck list or slide browser content.

The sidebar is a simple HTML panel toggled via a nav button. No new framework or library dependencies are needed — this follows the existing Pico CSS + vanilla JS pattern.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/catalog.py` | New function | `get_all_tags(db_path)` — returns tags with counts and categories |
| `outline2ppt/web/routes.py` | New endpoint | `GET /api/tags` — serves tag list with counts |
| `outline2ppt/web/static/index.html` | Modified | Add sidebar HTML, toggle logic, tag click handlers, filtered grid |

### Data Model Changes

No data model changes. The query joins existing `tags`, `slide_tags`, and `taxonomy` tables.

---

## CLI Changes

No CLI changes.

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Top nav | New toggle button | "Tags" button toggles the sidebar |
| Main content area | Layout change | When sidebar is open, content shifts right or shrinks to accommodate |
| Deck list / Slide browser | Filtered mode | When tags are selected, the main area shows matching slides across all decks |

### New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/tags` | Returns all tags with slide counts, grouped by category |

### Response Format for `GET /api/tags`

```json
{
  "tags": [
    {"name": "security", "category": "topic", "count": 42},
    {"name": "architecture", "category": "topic", "count": 31},
    {"name": "diagram", "category": "", "count": 15}
  ]
}
```

### Wireframe

```
+--Tags-toggle--+  Decks  |  Search  |  Settings  |  Export CSV
+===============+==========================================+
| Tags          |  Slide Grid (filtered)                   |
|               |                                          |
| [Clear all]   |  +--------+  +--------+  +--------+     |
|               |  | Slide  |  | Slide  |  | Slide  |     |
| ▼ Topic       |  | image  |  | image  |  | image  |     |
| [x] security  |  +--------+  +--------+  +--------+     |
| [ ] arch   31 |                                          |
| [ ] cloud  18 |  +--------+  +--------+  +--------+     |
|               |  | Slide  |  | Slide  |  | Slide  |     |
| ▼ Type        |  | image  |  | image  |  | image  |     |
| [ ] diagram15 |  +--------+  +--------+  +--------+     |
| [ ] chart   8 |                                          |
|               |                                          |
| ▼ Other       |                                          |
| [ ] misc    3 |                                          |
+===============+==========================================+
```

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_catalog.py` | `TestGetAllTags` | `get_all_tags()` with various tag/taxonomy states |

### Integration Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_web.py` | `test_api_tags_endpoint` | `/api/tags` returns correct structure, counts, categories |

### Manual Testing

1. Ingest 2+ decks with overlapping tags -- sidebar should show union of all tags with correct counts
2. Click a tag -- main grid filters to matching slides across all decks
3. Click a second tag -- results narrow (AND logic)
4. Click "Clear all" -- grid returns to normal deck list view
5. Toggle sidebar closed -- content area expands back to full width

---

## Changelog Entry

```markdown
### Added
- Tag browsing sidebar in the web UI for filtering slides by tag across all decks
- New `/api/tags` endpoint returning all tags with slide counts
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add `get_all_tags()` function | `outline2ppt/catalog.py` | -- |
| 2 | Add unit tests for `get_all_tags()` | `tests/test_catalog.py` | 1 |
| 3 | Add `GET /api/tags` endpoint | `outline2ppt/web/routes.py` | 1 |
| 4 | Add integration test for `/api/tags` | `tests/test_web.py` | 3 |
| 5 | Add sidebar HTML and CSS | `outline2ppt/web/static/index.html` | -- |
| 6 | Add sidebar toggle, tag click, and filter logic | `outline2ppt/web/static/index.html` | 3, 5 |
| 7 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Large tag sets could make the sidebar unwieldy -- **Mitigation:** Category grouping with collapse/expand keeps it organized. Could add a search-within-sidebar filter later if needed.
- **Risk:** AND logic with many tags selected could return zero results -- **Mitigation:** "Clear all" button is always visible. Could show a "No matching slides" message.
- **Question:** Should selecting tags in the sidebar update the Search view's tag input too (keeping them in sync)? -- **Recommendation:** No, keep them independent for now. The sidebar is a separate browsing flow.

---

## References

- Tag schema: `outline2ppt/schema.sql:35-51`
- Tag functions: `outline2ppt/catalog.py:344-546`
- Search backend: `outline2ppt/catalog.py:249-303`
- Search API: `outline2ppt/web/routes.py:72-79`
- Search UI: `outline2ppt/web/static/index.html:454-470, 643-664`
- Nav bar: `outline2ppt/web/static/index.html:340-350`
