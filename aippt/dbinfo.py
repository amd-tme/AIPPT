"""Database info dump: schema, statistics, deck inventory, tags, taxonomy, edit history."""
import json
import os
import sqlite3
from collections import defaultdict
from typing import Any, Dict, List, Optional

from aippt.catalog import get_db

# Tables to count in the statistics section (in display order)
_TRACKED_TABLES = [
    "decks",
    "slides",
    "tags",
    "slide_tags",
    "taxonomy",
    "sections",
    "slide_sections",
    "edit_history",
]


# ---------------------------------------------------------------------------
# Internal query helpers
# ---------------------------------------------------------------------------


def _get_schema_ddl(conn: sqlite3.Connection) -> List[str]:
    """Return all CREATE TABLE and CREATE INDEX DDL strings from sqlite_master."""
    rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type IN ('table', 'index') AND sql IS NOT NULL ORDER BY type DESC, name"
    ).fetchall()
    return [row["sql"] for row in rows]


def _get_table_stats(conn: sqlite3.Connection) -> Dict[str, int]:
    """Return row counts for each tracked table (0 if table does not exist)."""
    stats: Dict[str, int] = {}
    existing_tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for table in _TRACKED_TABLES:
        if table in existing_tables:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            stats[table] = row["cnt"]
        else:
            stats[table] = 0
    return stats


def _get_decks(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Return all decks with full metadata."""
    rows = conn.execute(
        """SELECT id, name, file_path, file_hash, author, created_date, modified_date,
                  subject, description, slide_count, cataloged_at, updated_at
           FROM decks
           ORDER BY id"""
    ).fetchall()
    return [dict(r) for r in rows]


def _get_deck_sections(conn: sqlite3.Connection, deck_id: int) -> List[Dict[str, Any]]:
    """Return sections for a deck with slide counts."""
    rows = conn.execute(
        """SELECT sec.id, sec.name, sec.position,
                  COUNT(ss.slide_id) as slide_count
           FROM sections sec
           LEFT JOIN slide_sections ss ON sec.id = ss.section_id
           WHERE sec.deck_id = ?
           GROUP BY sec.id
           ORDER BY sec.position""",
        (deck_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _get_deck_slides(conn: sqlite3.Connection, deck_id: int) -> List[Dict[str, Any]]:
    """Return slides for a deck with tags and section name."""
    slide_rows = conn.execute(
        """SELECT s.id, s.position, s.title, s.content_hash, s.layout_type, s.notes
           FROM slides s
           WHERE s.deck_id = ?
           ORDER BY s.position""",
        (deck_id,),
    ).fetchall()

    slides = []
    for row in slide_rows:
        slide_id = row["id"]

        # Tags
        tag_rows = conn.execute(
            """SELECT t.name FROM tags t
               JOIN slide_tags st ON t.id = st.tag_id
               WHERE st.slide_id = ?
               ORDER BY t.name""",
            (slide_id,),
        ).fetchall()
        tags = [r["name"] for r in tag_rows]

        # Section
        sec_row = conn.execute(
            """SELECT sec.name FROM sections sec
               JOIN slide_sections ss ON sec.id = ss.section_id
               WHERE ss.slide_id = ?""",
            (slide_id,),
        ).fetchone()
        section = sec_row["name"] if sec_row else None

        slides.append(
            {
                "id": slide_id,
                "position": row["position"],
                "title": row["title"],
                "content_hash": row["content_hash"],
                "layout_type": row["layout_type"],
                "tags": tags,
                "section": section,
                "notes": row["notes"] or "",
            }
        )
    return slides


def _get_all_tags(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Return all tags with source and usage count."""
    rows = conn.execute(
        """SELECT t.name, t.source, COUNT(st.slide_id) as slide_count
           FROM tags t
           LEFT JOIN slide_tags st ON t.id = st.tag_id
           GROUP BY t.id
           ORDER BY slide_count DESC, t.name"""
    ).fetchall()
    return [dict(r) for r in rows]


def _get_taxonomy(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Return all taxonomy entries ordered by category then name."""
    rows = conn.execute(
        "SELECT name, category FROM taxonomy ORDER BY category, name"
    ).fetchall()
    return [dict(r) for r in rows]


def _get_edit_history(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Return total edit count and last 10 entries."""
    total_row = conn.execute("SELECT COUNT(*) as cnt FROM edit_history").fetchone()
    total = total_row["cnt"]

    recent_rows = conn.execute(
        """SELECT slide_id, field, source, created_at
           FROM edit_history
           ORDER BY id DESC
           LIMIT 10"""
    ).fetchall()
    recent = [dict(r) for r in recent_rows]
    return {"total": total, "recent": recent}


# ---------------------------------------------------------------------------
# Formatting helpers (plain text)
# ---------------------------------------------------------------------------


def _fmt_size(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _truncate(text: str, max_len: int = 80) -> str:
    """Truncate a string to max_len characters, appending '...' if truncated."""
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _format_plain(
    db_path: str,
    size_bytes: int,
    sqlite_version: str,
    schema_ddl: List[str],
    table_stats: Dict[str, int],
    decks: List[Dict[str, Any]],
    deck_sections_map: Dict[int, List[Dict[str, Any]]],
    deck_slides_map: Dict[int, List[Dict[str, Any]]],
    all_tags: List[Dict[str, Any]],
    taxonomy: List[Dict[str, Any]],
    edit_history: Dict[str, Any],
) -> str:
    lines: List[str] = []

    # --- Database Info ---
    lines.append("=== Database Info ===")
    lines.append(f"Path: {db_path}")
    lines.append(f"Size: {_fmt_size(size_bytes)}")
    lines.append(f"SQLite version: {sqlite_version}")
    lines.append("")

    # --- Schema ---
    lines.append("=== Schema ===")
    for ddl in schema_ddl:
        lines.append(ddl + ";")
        lines.append("")

    # --- Table Statistics ---
    lines.append("=== Table Statistics ===")
    for table, count in table_stats.items():
        lines.append(f"  {table:<20} {count}")
    lines.append("")

    # --- Decks ---
    lines.append("=== Decks ===")
    if not decks:
        lines.append("  (no decks cataloged)")
    for deck in decks:
        lines.append(f"[{deck['id']}] {deck['name']}")
        lines.append(f"    Path: {deck['file_path']}")
        lines.append(f"    Hash: {(deck['file_hash'] or '')[:12]}...")
        lines.append(f"    Author: {deck['author'] or ''}")
        lines.append(f"    Created: {deck['created_date'] or ''}")
        lines.append(f"    Modified: {deck['modified_date'] or ''}")
        lines.append(f"    Subject: {deck['subject'] or ''}")
        lines.append(f"    Slides: {deck['slide_count']}")
        lines.append(f"    Cataloged: {deck['cataloged_at'] or ''}")

        sections = deck_sections_map.get(deck["id"], [])
        if sections:
            sec_parts = [f"{s['name']} ({s['slide_count']})" for s in sections]
            lines.append(f"    Sections: {', '.join(sec_parts)}")

        slides = deck_slides_map.get(deck["id"], [])
        if slides:
            lines.append("")
            lines.append("    Slides:")
            for slide in slides:
                hash_short = (slide["content_hash"] or "")[:8] + ".."
                parts = [f"      {slide['position']}. {slide['title']} [{hash_short}]"]
                if slide["section"]:
                    parts.append(f"section: {slide['section']}")
                if slide["tags"]:
                    parts.append(f"tags: {', '.join(slide['tags'])}")
                if slide["layout_type"]:
                    parts.append(f"layout: {slide['layout_type']}")
                lines.append("  ".join(parts))
                if slide["notes"]:
                    truncated = _truncate(slide["notes"], 80)
                    lines.append(f"        notes: {truncated}")
        lines.append("")

    # --- Tags ---
    total_tags = len(all_tags)
    lines.append(f"=== Tags ({total_tags} total) ===")
    if not all_tags:
        lines.append("  (no tags)")
    for tag in all_tags:
        lines.append(
            f"  {tag['name']:<30} {tag['source']:<12} {tag['slide_count']} slides"
        )
    lines.append("")

    # --- Taxonomy ---
    total_taxonomy = len(taxonomy)
    lines.append(f"=== Taxonomy ({total_taxonomy} entries) ===")
    if not taxonomy:
        lines.append("  (no taxonomy entries)")
    else:
        by_category: Dict[str, List[str]] = defaultdict(list)
        for entry in taxonomy:
            category = entry["category"] or "Uncategorized"
            by_category[category].append(entry["name"])
        for category in sorted(by_category.keys()):
            lines.append(f"  [{category}]")
            lines.append(f"    {', '.join(by_category[category])}")
    lines.append("")

    # --- Edit History ---
    total_edits = edit_history["total"]
    recent = edit_history["recent"]
    lines.append(
        f"=== Edit History ({total_edits} total edits, showing last {min(len(recent), 10)}) ==="
    )
    if not recent:
        lines.append("  (no edit history)")
    for entry in recent:
        # Format datetime: show only date + time (drop microseconds/timezone if present)
        created_at = (entry["created_at"] or "").replace("T", " ")[:16]
        lines.append(
            f"  {created_at}  slide #{entry['slide_id']:<6} {entry['field']:<12} ({entry['source']})"
        )

    return "\n".join(lines)


def _format_json(
    db_path: str,
    size_bytes: int,
    sqlite_version: str,
    schema_ddl: List[str],
    table_stats: Dict[str, int],
    decks: List[Dict[str, Any]],
    deck_sections_map: Dict[int, List[Dict[str, Any]]],
    deck_slides_map: Dict[int, List[Dict[str, Any]]],
    all_tags: List[Dict[str, Any]],
    taxonomy: List[Dict[str, Any]],
    edit_history: Dict[str, Any],
) -> str:
    decks_out = []
    for deck in decks:
        deck_dict = dict(deck)
        deck_dict["sections"] = deck_sections_map.get(deck["id"], [])

        slides_raw = deck_slides_map.get(deck["id"], [])
        slides_out = []
        for slide in slides_raw:
            slides_out.append(
                {
                    "position": slide["position"],
                    "title": slide["title"],
                    "content_hash": slide["content_hash"],
                    "layout_type": slide["layout_type"],
                    "tags": slide["tags"],
                    "section": slide["section"],
                    "notes": _truncate(slide["notes"], 80) if slide["notes"] else "",
                }
            )
        deck_dict["slides"] = slides_out
        decks_out.append(deck_dict)

    payload = {
        "database": {
            "path": db_path,
            "size_bytes": size_bytes,
            "sqlite_version": sqlite_version,
        },
        "schema": schema_ddl,
        "table_stats": table_stats,
        "decks": decks_out,
        "tags": [
            {
                "name": t["name"],
                "source": t["source"],
                "slide_count": t["slide_count"],
            }
            for t in all_tags
        ],
        "taxonomy": taxonomy,
        "edit_history": {
            "total": edit_history["total"],
            "recent": edit_history["recent"],
        },
    }
    return json.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def dump_db_info(db_path: str = "slides.db", as_json: bool = False) -> str:
    """Dump a comprehensive snapshot of the SQLite catalog database.

    Includes schema DDL, table statistics, deck inventory with per-slide detail,
    tags with usage counts, taxonomy grouped by category, and edit history.

    Args:
        db_path: Path to the SQLite database file.
        as_json: If True, return JSON string; otherwise return plain text.

    Returns:
        Formatted string (plain text or JSON).
    """
    conn = get_db(db_path)
    try:
        # Gather SQLite version
        ver_row = conn.execute("SELECT sqlite_version() as v").fetchone()
        sqlite_version: str = ver_row["v"]

        # File size (0 if file does not exist yet -- in-memory or new DB)
        try:
            size_bytes = os.path.getsize(db_path)
        except OSError:
            size_bytes = 0

        schema_ddl = _get_schema_ddl(conn)
        table_stats = _get_table_stats(conn)
        decks = _get_decks(conn)

        deck_sections_map: Dict[int, List[Dict[str, Any]]] = {}
        deck_slides_map: Dict[int, List[Dict[str, Any]]] = {}
        for deck in decks:
            deck_id = deck["id"]
            deck_sections_map[deck_id] = _get_deck_sections(conn, deck_id)
            deck_slides_map[deck_id] = _get_deck_slides(conn, deck_id)

        all_tags = _get_all_tags(conn)
        taxonomy = _get_taxonomy(conn)
        edit_history = _get_edit_history(conn)
    finally:
        conn.close()

    if as_json:
        return _format_json(
            db_path,
            size_bytes,
            sqlite_version,
            schema_ddl,
            table_stats,
            decks,
            deck_sections_map,
            deck_slides_map,
            all_tags,
            taxonomy,
            edit_history,
        )
    else:
        return _format_plain(
            db_path,
            size_bytes,
            sqlite_version,
            schema_ddl,
            table_stats,
            decks,
            deck_sections_map,
            deck_slides_map,
            all_tags,
            taxonomy,
            edit_history,
        )
