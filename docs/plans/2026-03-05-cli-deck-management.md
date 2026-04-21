# PRD: CLI Deck Management Commands

**Date:** 2026-03-05
**Author:** Matt
**Status:** Draft

---

## Summary

The CLI has no commands for basic deck inventory management. Users must run raw SQL to list, rename, or delete cataloged decks. This PRD adds `aippt decks list`, `aippt decks rename`, and `aippt decks delete` subcommands for managing the slide catalog from the command line.

## Motivation

- **What problem does this solve?** There's no CLI way to see what's in the database, rename a deck's display name, or remove a deck and its associated data. Users must write SQL queries manually (documented in CLAUDE.md) or use the web UI.
- **Who benefits?** CLI users, automation scripts, and anyone managing the catalog without the web UI running.
- **What happens if we don't do this?** Users risk data mistakes from hand-written DELETE cascades and have no quick way to audit catalog contents.

## Requirements

### Must Have

- [ ] `aippt decks list` — tabular display of all cataloged decks with key metadata
- [ ] `aippt decks delete <deck>` — remove a deck and all associated data (slides, tags, sections, edit history) with confirmation prompt
- [ ] `aippt decks rename <deck> <new-name>` — update a deck's display name
- [ ] Deck lookup by ID or name (partial match) for all commands
- [ ] `--db` flag on all subcommands (default: `slides.db`)

### Nice to Have

- [ ] `aippt decks info <deck>` — detailed view of a single deck (metadata + slide titles + tag summary)
- [ ] `aippt decks delete --purge-images` — also remove the deck's image directory
- [ ] `--json` output flag for scripting
- [ ] `--force` flag to skip confirmation on delete

### Out of Scope

- Web UI deck management (delete/rename) — separate PRD
- Bulk operations (delete multiple decks at once)
- Deck merge or split operations

---

## Design

### Approach

Add a `decks` subcommand group to the CLI (following the existing `tags` and `models` pattern). Implement catalog functions in `catalog.py` for delete and rename, and wire them up through `cli.py`.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `aippt/catalog.py` | New functions | `delete_deck()`, `rename_deck()`, `get_deck_by_name()` |
| `aippt/cli.py` | New subcommands | `decks list`, `decks delete`, `decks rename`, `decks info` |

### Data Model Changes

No schema changes. All operations use existing tables. The `ON DELETE CASCADE` constraints on `slides`, `slide_tags`, `sections`, `slide_sections`, and `edit_history` handle cascading deletes automatically.

### Cascade verification

The schema defines these foreign key cascades:

```sql
slides.deck_id       → REFERENCES decks(id) ON DELETE CASCADE
slide_tags.slide_id  → REFERENCES slides(id) ON DELETE CASCADE
sections.deck_id     → REFERENCES decks(id) ON DELETE CASCADE
slide_sections       → REFERENCES slides(id) ON DELETE CASCADE
                     → REFERENCES sections(id) ON DELETE CASCADE
edit_history.slide_id→ REFERENCES slides(id) ON DELETE CASCADE
```

Deleting from `decks` cascades through all related tables automatically, provided `PRAGMA foreign_keys = ON` is set (verify this in `get_db()`).

---

## CLI Changes

### New Commands

```
aippt decks list [--db slides.db] [--json]
aippt decks info <deck> [--db slides.db] [--json]
aippt decks rename <deck> <new-name> [--db slides.db]
aippt decks delete <deck> [--db slides.db] [--force] [--purge-images]
```

### Command Details

#### `aippt decks list`

Display all cataloged decks in a table.

| Column | Source | Description |
|--------|--------|-------------|
| ID | `decks.id` | Database ID |
| Name | `decks.name` | Deck name (display_name applied) |
| Slides | `decks.slide_count` | Number of slides |
| Author | `decks.author` | Deck author from PPTX metadata |
| Cataloged | `decks.cataloged_at` | When first cataloged |
| Updated | `decks.updated_at` | Last re-catalog timestamp |
| Tags | computed | Count of distinct tags across all slides |
| File | `decks.file_path` | Path to source PPTX |

Example output:

```
ID  Name                                    Slides  Author        Cataloged   Tags  File
──  ──────────────────────────────────────  ──────  ────────────  ──────────  ────  ──────────────────────
 1  Networking Advantages                       12  Matt Elliott  2026-03-04    24  uploads/net-adv.pptx
 3  Deploying AMD Instinct                      18  Matt Elliott  2026-03-04    31  uploads/instinct.pptx
 5  Meme Directives Test                        11  (none)        2026-03-05     0  output/meme-test.pptx

3 decks, 41 slides total
```

#### `aippt decks info <deck>`

Show detailed metadata for a single deck, including slide titles and tag distribution.

```
Deck: Networking Advantages (ID: 1)
File: uploads/49c5d4025dfc4012ab2a56a93d0acc11_net-adv.pptx
Author: Matt Elliott
Subject: AMD Networking
Slides: 12
Cataloged: 2026-03-04 10:30:00
Updated: 2026-03-05 14:15:00

Slides:
  1. Title Slide
  2. Agenda
  3. Network Architecture Overview
  ...

Tags (24 total):
  networking (8), architecture (5), security (4), performance (3), ...
```

#### `aippt decks rename <deck> <new-name>`

Update the deck's `name` column. The `<deck>` argument accepts an ID (integer) or a name substring (case-insensitive partial match). If multiple decks match a name query, print the matches and ask the user to be more specific.

```bash
$ aippt decks rename 1 "AMD Networking Advantages Q4 2025"
Renamed deck 1: "Networking Advantages" → "AMD Networking Advantages Q4 2025"

$ aippt decks rename "instinct" "AMD Instinct Deployment Guide"
Renamed deck 3: "Deploying AMD Instinct" → "AMD Instinct Deployment Guide"
```

#### `aippt decks delete <deck>`

Delete a deck and all associated data (cascading). Prints a summary and asks for confirmation unless `--force` is used.

```bash
$ aippt decks delete 1
Delete deck 1 "Networking Advantages"?
  12 slides, 24 tags, 2 sections will be removed.
  Type 'yes' to confirm: yes
Deleted deck 1 and all associated data.

$ aippt decks delete "meme" --force
Deleted deck 5 "Meme Directives Test" and all associated data.

$ aippt decks delete "instinct" --purge-images
Delete deck 3 "Deploying AMD Instinct"?
  18 slides, 31 tags will be removed.
  Image directory will be deleted: images/instinct/
  Type 'yes' to confirm: yes
Deleted deck 3 and all associated data.
Removed image directory: images/instinct/
```

### Deck Lookup Logic

All commands that accept `<deck>` use a shared lookup function:

1. If `<deck>` is an integer, look up by `decks.id`
2. Otherwise, search `decks.name` with case-insensitive `LIKE '%<deck>%'`
3. If exactly one match, use it
4. If zero matches, print error and exit
5. If multiple matches, print the matches and ask user to be more specific (or use ID)

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_catalog.py` | `test_delete_deck`, `test_delete_deck_cascades` | Verify deck + slides + tags removed |
| `tests/test_catalog.py` | `test_rename_deck` | Verify name update |
| `tests/test_catalog.py` | `test_get_deck_by_name_partial` | Verify partial name matching |
| `tests/test_catalog.py` | `test_get_deck_by_name_ambiguous` | Verify multiple matches return all |
| `tests/test_cli.py` | `test_cmd_decks_list`, `test_cmd_decks_delete`, `test_cmd_decks_rename` | CLI integration |

### Manual Testing

1. `aippt decks list` — verify table output with correct metadata
2. `aippt decks info 1` — verify detailed deck view
3. `aippt decks rename 1 "New Name"` — verify rename, then list to confirm
4. `aippt decks delete <id>` — verify confirmation prompt, then list to confirm removal
5. `aippt decks delete <name> --force` — verify no prompt
6. `aippt decks delete <name> --purge-images` — verify image directory removed
7. Test ambiguous name match — verify user prompted to be specific

---

## Changelog Entry

```markdown
### Added
- `aippt decks list` — list all cataloged decks with metadata
- `aippt decks info <deck>` — show detailed deck information
- `aippt decks rename <deck> <new-name>` — rename a cataloged deck
- `aippt decks delete <deck>` — remove a deck and all associated data
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add `delete_deck()` to catalog.py (with cascade verification) | `aippt/catalog.py` | -- |
| 2 | Add `rename_deck()` to catalog.py | `aippt/catalog.py` | -- |
| 3 | Add `get_deck_by_name()` shared lookup function | `aippt/catalog.py` | -- |
| 4 | Add `decks` subcommand group with list/info/rename/delete | `aippt/cli.py` | 1, 2, 3 |
| 5 | Verify `PRAGMA foreign_keys = ON` in `get_db()` | `aippt/catalog.py` | -- |
| 6 | Add unit tests for catalog functions | `tests/test_catalog.py` | 1, 2, 3 |
| 7 | Add CLI integration tests | `tests/test_cli.py` | 4 |
| 8 | Update CLAUDE.md to replace manual SQL with CLI commands | `CLAUDE.md` | 4 |
| 9 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** SQLite foreign key cascades require `PRAGMA foreign_keys = ON` (off by default in SQLite). Verify `get_db()` enables this — if not, cascading deletes will silently leave orphaned rows — Mitigation: Task 5 verifies and fixes this; fall back to explicit DELETE statements if pragma can't be guaranteed
- **Question:** Should `decks list` show the `file_path` column? It can be long and ugly (UUID prefixes from web uploads). Recommendation: show it but truncate to last path component; `decks info` shows the full path
- **Question:** Should delete also remove the PPTX file itself? Recommendation: no — only remove database records and optionally images. The PPTX is the user's source file

---

## References

- Existing catalog functions: `aippt/catalog.py` (`list_decks()`, `get_deck_by_id()`)
- Schema: `aippt/schema.sql`
- Manual delete SQL: `CLAUDE.md` (Resetting Ingested Decks section)
- CLI subcommand pattern: `tags` subcommand group in `cli.py`
