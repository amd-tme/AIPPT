# PRD: [Feature Name]

**Date:** YYYY-MM-DD
**Author:** [Name]
**Status:** Draft | In Review | Approved | In Progress | Complete

---

## Summary

One-paragraph description of the feature or change. What is it, and why does it matter?

## Motivation

- What problem does this solve?
- Who benefits (end user, developer, both)?
- What happens if we don't do this?

## Requirements

### Must Have

- [ ] Requirement 1
- [ ] Requirement 2

### Nice to Have

- [ ] Optional requirement 1

### Out of Scope

- Explicitly list things this PRD does NOT cover.

---

## Design

### Approach

Describe the implementation approach at a high level. Reference existing modules and patterns where applicable.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/module.py` | New / Modified | What changes and why |

### Data Model Changes

Describe any changes to `schema.sql`, new tables, new columns, or migration steps.

If none: "No data model changes."

If changes are needed, include:

#### New columns on existing tables

```sql
-- table_name: description of what the column stores
ALTER TABLE table_name ADD COLUMN column_name TEXT NOT NULL DEFAULT '';
```

#### New tables

```sql
CREATE TABLE IF NOT EXISTS new_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- columns...
);
```

#### Column semantics

| Column | Source | Default | Updated When |
|--------|--------|---------|-------------|
| `table.column` | Where the value comes from | Default value | When it gets written |

#### Migration process

All migrations run inside `get_db()` in `catalog.py` using idempotent `ALTER TABLE` / `CREATE TABLE IF NOT EXISTS`. See `docs/plans/2026-03-02-data-model-v2.md` for the established pattern:

- New columns: add to the existing migration loop in `get_db()` (PRAGMA table_info check + ALTER TABLE)
- New tables: add `CREATE TABLE IF NOT EXISTS` to `schema.sql` (executed on every `get_db()` call)
- Always update `schema.sql` to reflect the full canonical schema for new databases
- Always add unit tests verifying idempotent migration (run `get_db()` twice, no errors)

#### python-pptx core_properties reference

Available attributes: `author`, `subject`, `category`, `comments`, `keywords`, `content_status`, `created`, `modified`, `last_modified_by`, `last_printed`, `revision`, `title`, `version`, `identifier`, `language`.

Note: python-pptx does **not** expose a `description` attribute. The closest equivalent is `comments`. Use `getattr(cp, "attr", None)` for defensive access.

---

## CLI Changes

### New Commands

```
outline2ppt <command> [args] [options]
```

Describe arguments, options, defaults, and example invocations.

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `outline2ppt <cmd>` | New option `--flag` | Description |

### Example Usage

```bash
# Example 1: Basic usage
python outline2ppt.py <command> arg1 arg2

# Example 2: With options
python outline2ppt.py <command> arg1 --option value
```

If no CLI changes: "No CLI changes."

---

## UI Changes

### New Pages / Views

Describe new web UI pages, sections, or components.

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Dashboard | Added widget | Description |

### New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/resource` | Returns resource list |
| POST | `/api/resource` | Creates a resource |

### Wireframe / Mockup

Include ASCII mockup, screenshot, or link to design if applicable.

If no UI changes: "No UI changes."

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_module.py` | `TestClassName` | Functions/methods covered |

### Integration Tests

Describe any additions to `tests/test_integration.py` or new integration test files.

### Manual Testing

List specific manual validation steps. Reference `UITESTING.md` sections if adding to the UI testing guide.

1. Step 1 -- expected result
2. Step 2 -- expected result

---

## Changelog Entry

Draft the `CHANGELOG.md` entry for this feature. Follow [Keep a Changelog](https://keepachangelog.com/) format.

```markdown
### Added
- Description of new feature

### Changed
- Description of change to existing functionality

### Fixed
- Description of bug fix
```

---

## Implementation Tasks

Break down into ordered, independently committable tasks.

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Description | `file1.py`, `file2.py` | -- |
| 2 | Description | `file3.py` | 1 |
| 3 | Wire up CLI | `cli.py` | 1, 2 |
| 4 | Add tests | `tests/test_*.py` | 1, 2 |
| 5 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Description -- mitigation strategy
- **Question:** Unresolved decision -- options A vs B

---

## References

- Related PRDs: `docs/plans/YYYY-MM-DD-name.md`
- External docs: links
- Issues: references
