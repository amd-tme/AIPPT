"""Export slide metadata to CSV."""
import csv
import logging
from typing import Optional

from aippt.catalog import get_db, get_slide_tags, get_slide_section

logger = logging.getLogger(__name__)

COLUMNS = [
    "deck_name", "subject", "description", "slide_number", "title",
    "layout_type", "section", "notes",
    "tags", "author", "deck_created_date", "slide_created_date",
    "content_hash", "image_path", "last_updated",
]


def export_csv(
    output_path: str,
    db_path: str = "slides.db",
    deck_path: Optional[str] = None,
    export_all: bool = False,
):
    """Export slide metadata to CSV.

    Args:
        output_path: CSV output file path
        db_path: SQLite database path
        deck_path: Specific deck to export (by file path)
        export_all: If True, export all decks
    """
    conn = get_db(db_path)

    if deck_path:
        import os
        abs_deck_path = os.path.abspath(deck_path)
        rel_deck_path = os.path.relpath(abs_deck_path)
        query = """
            SELECT s.id, s.position, s.title, s.notes, s.content_hash,
                   s.image_path, s.updated_at, s.author, s.slide_created_date,
                   s.layout_type,
                   d.name as deck_name, d.created_date as deck_created_date,
                   d.subject as deck_subject, d.description as deck_description
            FROM slides s JOIN decks d ON s.deck_id = d.id
            WHERE d.file_path = ? OR d.file_path = ?
            ORDER BY d.name, s.position
        """
        rows = conn.execute(query, (rel_deck_path, abs_deck_path)).fetchall()
    elif export_all:
        query = """
            SELECT s.id, s.position, s.title, s.notes, s.content_hash,
                   s.image_path, s.updated_at, s.author, s.slide_created_date,
                   s.layout_type,
                   d.name as deck_name, d.created_date as deck_created_date,
                   d.subject as deck_subject, d.description as deck_description
            FROM slides s JOIN decks d ON s.deck_id = d.id
            ORDER BY d.name, s.position
        """
        rows = conn.execute(query).fetchall()
    else:
        logger.error("Specify a deck path or use --all")
        conn.close()
        return 0

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            tags = get_slide_tags(row["id"], db_path)
            section = get_slide_section(row["id"], db_path) or ""
            writer.writerow({
                "deck_name": row["deck_name"],
                "subject": row["deck_subject"] or "",
                "description": row["deck_description"] or "",
                "slide_number": row["position"],
                "title": row["title"],
                "layout_type": row["layout_type"] or "",
                "section": section,
                "notes": row["notes"],
                "tags": "; ".join(tags),
                "author": row["author"] or "",
                "deck_created_date": row["deck_created_date"] or "",
                "slide_created_date": row["slide_created_date"] or "",
                "content_hash": row["content_hash"],
                "image_path": row["image_path"] or "",
                "last_updated": row["updated_at"],
            })

    conn.close()
    count = len(rows)
    logger.info(f"Exported {count} slides to {output_path}")
    return count
