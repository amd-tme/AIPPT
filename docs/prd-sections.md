# PRD: PowerPoint Section Support

## Problem Statement

PowerPoint sections are a native organizational feature that groups slides into named, ordered blocks visible in Slide Sorter and the slide panel. Unlike tags (many-to-many, unordered), sections are:

- **Exclusive**: each slide belongs to exactly one section (or none)
- **Ordered**: sections have a defined sequence within the deck
- **Structural**: they represent the logical outline of a presentation

AIPPT currently has no awareness of sections. Adding section support would enable:
- Cataloging existing section structure when importing decks
- Applying sections when creating decks from outlines (top-level headings → sections)
- AI-powered section suggestions for unstructured decks
- Section-aware search, remix, and export

## Feasibility

**Confirmed feasible.** python-pptx has no native section API (open issue [#257](https://github.com/scanny/python-pptx/issues/257) since 2016), but sections are fully accessible via direct XML manipulation of `ppt/presentation.xml`. The community has well-tested patterns for reading and writing sections via lxml.

### Technical Details

Sections live in `presentation.xml` as a PowerPoint 2010+ extension:

```xml
<p:extLst>
  <p:ext uri="{521415D9-36F7-43E2-AB2F-B90AF26B5E84}">
    <p14:sectionLst xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main">
      <p14:section name="Introduction" id="{UUID}">
        <p14:sldIdLst>
          <p14:sldId id="256"/>
          <p14:sldId id="257"/>
        </p14:sldIdLst>
      </p14:section>
    </p14:sectionLst>
  </p:ext>
</p:extLst>
```

Key facts:
- Extension URI is a fixed GUID: `{521415D9-36F7-43E2-AB2F-B90AF26B5E84}`
- Namespace: `p14` = `http://schemas.microsoft.com/office/powerpoint/2010/main`
- Slide membership uses `slide.slide_id` (integer), available from python-pptx
- Sections must be written as the final step before `prs.save()` since slide additions/removals would invalidate the section XML

## Data Model

### New Database Tables

```sql
-- Named sections within a deck
CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position INTEGER NOT NULL,  -- ordering within the deck
    UNIQUE(deck_id, name),
    UNIQUE(deck_id, position)
);

-- Each slide belongs to at most one section
CREATE TABLE IF NOT EXISTS slide_sections (
    slide_id INTEGER NOT NULL REFERENCES slides(id) ON DELETE CASCADE,
    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    PRIMARY KEY (slide_id),  -- enforces one section per slide
    FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sections_deck ON sections(deck_id);
CREATE INDEX IF NOT EXISTS idx_slide_sections_section ON slide_sections(section_id);
```

Key design decisions:
- **`slide_sections` PK is `slide_id` alone** — enforces the one-section-per-slide constraint at the database level
- **`sections.position`** — maintains ordering, with a uniqueness constraint per deck
- **Cascading deletes** — removing a deck or slide cleans up section associations
- Sections are **deck-scoped** (unlike tags, which are global) — the same section name can appear in different decks

### Relationship to Tags

| Aspect | Tags | Sections |
|--------|------|----------|
| Cardinality | Many-to-many | One-to-one (slide → section) |
| Scope | Global across all decks | Scoped to a single deck |
| Ordering | Unordered set | Ordered sequence |
| Source | ai, taxonomy, manual | pptx, outline, ai, manual |
| Purpose | Categorization/discovery | Structural organization |

## Features

### Phase 1: Core Infrastructure

#### 1.1 Section XML Reader (`sections.py`)
- `read_sections(presentation) → list[Section]` — Parse `p14:sectionLst` from a Presentation object
- `Section` dataclass: `name`, `slide_ids` (list of integer slide IDs)
- Handle missing sections gracefully (many PPTX files have none)

#### 1.2 Section XML Writer (`sections.py`)
- `write_sections(presentation, sections: list[Section])` — Write `p14:sectionLst` XML
- Generate UUIDs for section `id` attributes
- Remove existing sections before writing (replace semantics)
- Must be called after all slides are added, before `prs.save()`

#### 1.3 Database Operations (`catalog.py`)
- `set_slide_section(slide_id, section_name, deck_id)` — Assign slide to section (upsert)
- `get_slide_section(slide_id) → str | None` — Get section name for a slide
- `get_deck_sections(deck_id) → list[dict]` — Get ordered sections with slide counts
- `remove_slide_section(slide_id)` — Remove slide from its section
- `rename_section(deck_id, old_name, new_name)` — Rename a section within a deck

#### 1.4 Schema Migration
- Add `sections` and `slide_sections` tables
- Migration runs on `init_db()` — detect missing tables and create them (non-destructive)

### Phase 2: Integration with Existing Features

#### 2.1 Catalog Integration
- `catalog_deck()` reads sections from the PPTX and stores them in the database
- Re-cataloging updates sections (detects changes via file hash, same as slides)

#### 2.2 Create Integration
- Top-level headings (`# Section Name`) in markdown outlines become PowerPoint sections
- `write_sections()` called as final step before save
- No change to slide creation logic — sections are applied after all slides exist

#### 2.3 Reverse Integration
- `ppt2outline.py` emits section comments or structural markers when converting PPTX → markdown
- Option: use `# Section Name` as a heading above the slides in that section

#### 2.4 Search Integration
- `search_slides()` gains `--section` filter parameter
- Can combine with existing `--tags` and `--title-contains` filters

#### 2.5 Export Integration
- CSV export includes `section` column per slide
- Remix manifest includes section assignments

### Phase 3: AI and Web UI

#### 3.1 AI Section Suggestions (`analyze.py`)
- New analysis mode: `--mode sections`
- LLM reviews slide sequence and suggests section boundaries + names
- Applies sections to database (and optionally writes to PPTX)
- Works with or without existing section structure

#### 3.2 Web UI
- **Slide cards** show section name badge (distinct from tags)
- **Section filter** in search sidebar
- **Section management panel** per deck:
  - View sections with slide counts
  - Drag-and-drop reordering (updates position)
  - Rename sections inline
  - Assign/reassign slides to sections
- **Deck detail view** groups slides by section with visual separators

#### 3.3 CLI Commands
```bash
# View sections for a deck
aippt sections <deck.pptx>

# Assign a slide to a section
aippt section-set <slide_id> "Introduction"

# Remove slide from section
aippt section-clear <slide_id>

# AI-suggest sections
aippt analyze <deck.pptx> --mode sections
```

## Implementation Notes

### Section XML Module (`aippt/sections.py`)

New module containing all section XML operations:

```python
# Core types
@dataclass
class Section:
    name: str
    slide_ids: list[int]  # slide.slide_id values

# Read/write functions
def read_sections(prs: Presentation) -> list[Section]: ...
def write_sections(prs: Presentation, sections: list[Section]) -> None: ...
```

This isolates the XML manipulation from the rest of the codebase. All other modules interact with sections via the database or these two functions.

### Integration Points

| Module | Change | Scope |
|--------|--------|-------|
| `sections.py` | New file — XML read/write | Phase 1 |
| `catalog.py` | Section DB operations + catalog reads sections | Phase 1-2 |
| `schema.sql` | Add `sections`, `slide_sections` tables | Phase 1 |
| `cli.py` | Section subcommands, `--section` search filter | Phase 2-3 |
| `parser.py` | Extract `# Heading` as section markers | Phase 2 |
| `layouts.py` | No change (sections don't affect layout selection) | — |
| `ppt2outline.py` | Emit section structure in markdown output | Phase 2 |
| `analyze.py` | `--mode sections` for AI suggestions | Phase 3 |
| `export.py` | Include `section` column in CSV | Phase 2 |
| `remix.py` | Carry section info into remixed decks | Phase 2 |
| `web/routes.py` | Section API endpoints | Phase 3 |
| `web/static/index.html` | Section UI components | Phase 3 |

### Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Section XML becomes stale if slides are added/removed after writing | Corrupted section display in PowerPoint | Always write sections as the final step; validate slide IDs exist before writing |
| PowerPoint versions before 2010 don't support sections | Sections silently ignored | Document minimum version requirement; the `p14` extension is safely ignored by older versions |
| `slide.slide_id` changes if slides are copied between presentations | Section membership broken | Re-read slide IDs from the destination presentation when applying sections during remix |
| Schema migration on existing databases | Potential data issues | Use `CREATE TABLE IF NOT EXISTS`; non-destructive migration |

## Out of Scope

- **Nested sections** — PowerPoint doesn't support section nesting
- **Section-level metadata** — No custom properties on sections (beyond name and ordering)
- **Section templates** — Predefined section structures (could be a future feature)
- **Cross-deck sections** — Sections are inherently deck-scoped; use tags for cross-deck categorization
