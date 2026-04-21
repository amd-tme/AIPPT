# PRD: Hide UUID Prefix from Deck Display Names

**Date:** 2026-03-03
**Author:** Matt
**Status:** Draft

---

## Summary

When decks are uploaded via the web UI, a 32-character UUID hex prefix is prepended to the filename for collision safety (e.g., `44dc98ea57f240efaabca1333f166d0b_4Q25 - AI SW Story`). This UUID leaks into every place the deck name is displayed: the deck list, the slide browser header, toast notifications, and downloaded filenames. This PRD adds a `display_name()` helper that strips the UUID prefix, and surfaces a clean `display_name` field through the API and UI.

## Motivation

- **What problem does this solve?** Users see ugly UUID-prefixed names everywhere in the UI, making it hard to identify decks at a glance. Downloaded files also carry the UUID prefix.
- **Who benefits?** End users of the web UI.
- **What happens if we don't do this?** The UI continues to show `44dc98ea..._{filename}` instead of just `{filename}`.

## Requirements

### Must Have

- [ ] Python helper `display_name(name: str) -> str` that strips a leading `[0-9a-f]{32}_` prefix
- [ ] `/api/decks` response includes `display_name` field for each deck
- [ ] `/api/decks/{id}/download` uses the stripped name in `Content-Disposition`
- [ ] Deck list table in the web UI shows `display_name` instead of raw `name`
- [ ] Slide browser header shows `display_name`
- [ ] Upload/create toast notifications show `display_name`
- [ ] Search results show `display_name` for the deck name

### Nice to Have

- [ ] Upload response (`/api/decks/upload`) also returns `display_name`
- [ ] SSE stream events for upload and create include `display_name`

### Out of Scope

- Renaming files on disk (UUID prefix stays for collision safety)
- Database schema changes (no new columns)
- Changing the ingest pipeline's `deck_name` derivation
- Retroactive rename of images directories

---

## Design

### Approach

Add a pure-function `display_name()` in `catalog.py` that uses a regex to strip a leading 32-char hex UUID prefix. The API layer in `routes.py` calls this function and includes a `display_name` key in all deck-related responses. The frontend uses `display_name` (falling back to `name`) for all user-facing text.

On-disk filenames, database `name` column, and image directory names remain unchanged. The UUID prefix is a display concern only.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/catalog.py` | New function | Add `display_name(name: str) -> str` |
| `outline2ppt/web/routes.py` | Modified | Add `display_name` to API responses; strip UUID in download header |
| `outline2ppt/web/static/index.html` | Modified | Use `display_name` in deck list, browser header, toasts |

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
| Deck list | Display column | Show `display_name` instead of `name` |
| Slide browser | Header text | `browseDeck()` passes `display_name` |
| Upload toast | Notification | Use `display_name` in success message |
| Create toast | Notification | Use `display_name` in success message |
| Search results | Deck label | Show `display_name` in `deck_name` small text |

### Modified API Endpoints

| Method | Path | Change |
|--------|------|--------|
| GET | `/api/decks` | Each deck dict gains `display_name` field |
| POST | `/api/decks/upload` | Response gains `display_name` field |
| GET | `/api/decks/{id}/download` | `Content-Disposition` filename uses stripped name |
| GET | `/api/search` | `deck_name` in results uses stripped name |

### No New API Endpoints

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_catalog.py` | `TestDisplayName` | `display_name()` with UUID prefix, without prefix, edge cases |

### Test Cases for `display_name()`

| Input | Expected Output |
|-------|-----------------|
| `"44dc98ea57f240efaabca1333f166d0b_Deck Name"` | `"Deck Name"` |
| `"Regular Deck Name"` | `"Regular Deck Name"` |
| `""` | `""` |
| `"abcdef1234567890abcdef1234567890_"` | `""` (trailing underscore stripped, empty remainder) |
| `"ABCDEF1234567890abcdef1234567890_Name"` | `"ABCDEF1234567890abcdef1234567890_Name"` (uppercase hex = no match) |
| `"abc_short_prefix"` | `"abc_short_prefix"` (too short = no match) |

### Integration Tests

Add a test to `tests/test_web.py` that verifies `/api/decks` response includes `display_name` with the UUID stripped.

### Manual Testing

1. Upload a deck via the web UI -- deck list should show the original filename without UUID prefix
2. Click a deck -- slide browser header should show the clean name
3. Download a deck -- downloaded file should be named without the UUID prefix
4. Search for slides -- deck name in results should be clean

---

## Changelog Entry

```markdown
### Fixed
- Deck names in the web UI no longer show the internal UUID prefix from uploaded files
- Downloaded deck files now use the original filename instead of the UUID-prefixed name
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add `display_name()` helper | `outline2ppt/catalog.py` | -- |
| 2 | Add unit tests for `display_name()` | `tests/test_catalog.py` | 1 |
| 3 | Add `display_name` to `/api/decks` response | `outline2ppt/web/routes.py` | 1 |
| 4 | Strip UUID in download `Content-Disposition` | `outline2ppt/web/routes.py` | 1 |
| 5 | Add `display_name` to upload/create/search responses | `outline2ppt/web/routes.py` | 1 |
| 6 | Update `index.html` to use `display_name` everywhere | `outline2ppt/web/static/index.html` | 3, 5 |
| 7 | Add integration test for API `display_name` field | `tests/test_web.py` | 3 |
| 8 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** A file whose original name genuinely starts with 32 hex chars + underscore would be incorrectly stripped -- **Mitigation:** This pattern is extremely unlikely in real presentation filenames. The regex is precise (exactly 32 lowercase hex chars).
- **Risk:** Non-uploaded decks (cataloged via CLI) don't have UUID prefixes, so `display_name()` is a no-op for them -- **Mitigation:** This is correct and expected behavior.

---

## References

- Upload endpoint: `outline2ppt/web/routes.py:606-659`
- Deck list API: `outline2ppt/web/routes.py:41-50`
- Download endpoint: `outline2ppt/web/routes.py:916-950`
- Deck name derivation in catalog: `outline2ppt/catalog.py:79-96`
- UI deck list rendering: `outline2ppt/web/static/index.html:617-618`
