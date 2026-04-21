"""Tests for the export module."""
import csv
import pytest

from aippt.catalog import get_db, add_tags
from aippt.export import export_csv, COLUMNS


@pytest.fixture
def db_with_data(tmp_path):
    """Create a test database with sample data."""
    db_path = str(tmp_path / "test.db")
    conn = get_db(db_path)
    conn.execute(
        "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
        ("deck1", "/path/to/deck1.pptx", "abc123", 2),
    )
    conn.execute(
        "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (1, 1, "Intro", "intro content", "hash1", "speaker notes here"),
    )
    conn.execute(
        "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (1, 2, "Summary", "summary content", "hash2", ""),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def db_with_two_decks(tmp_path):
    """Create a test database with two decks."""
    db_path = str(tmp_path / "test.db")
    conn = get_db(db_path)
    conn.execute(
        "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
        ("deck1", "/path/to/deck1.pptx", "abc123", 1),
    )
    conn.execute(
        "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
        ("deck2", "/path/to/deck2.pptx", "def456", 1),
    )
    conn.execute(
        "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (1, 1, "Slide A", "content a", "hasha", "notes a"),
    )
    conn.execute(
        "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (2, 1, "Slide B", "content b", "hashb", "notes b"),
    )
    conn.commit()
    conn.close()
    return db_path


class TestExportCsv:
    def test_export_all(self, tmp_path, db_with_data):
        output = str(tmp_path / "out.csv")
        count = export_csv(output, db_path=db_with_data, export_all=True)

        assert count == 2
        with open(output, encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            assert len(reader) == 2
            assert reader[0]["title"] == "Intro"
            assert reader[0]["notes"] == "speaker notes here"
            assert reader[1]["title"] == "Summary"
            assert reader[1]["notes"] == ""

    def test_export_specific_deck(self, tmp_path, db_with_two_decks):
        # Use the absolute path that matches what export_csv will resolve
        import os
        deck2_abs = os.path.abspath("/path/to/deck2.pptx")
        # Update the DB to use the absolute path
        conn = get_db(db_with_two_decks)
        conn.execute("UPDATE decks SET file_path = ? WHERE name = 'deck2'", (deck2_abs,))
        conn.commit()
        conn.close()

        output = str(tmp_path / "out.csv")
        count = export_csv(output, db_path=db_with_two_decks, deck_path="/path/to/deck2.pptx")

        assert count == 1
        with open(output, encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            assert len(reader) == 1
            assert reader[0]["title"] == "Slide B"
            assert reader[0]["deck_name"] == "deck2"

    def test_export_no_args_returns_zero(self, tmp_path, db_with_data):
        output = str(tmp_path / "out.csv")
        count = export_csv(output, db_path=db_with_data)
        assert count == 0

    def test_export_includes_tags(self, tmp_path, db_with_data):
        add_tags(1, ["security", "overview"], source="manual", db_path=db_with_data)
        output = str(tmp_path / "out.csv")
        export_csv(output, db_path=db_with_data, export_all=True)

        with open(output, encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            assert "security" in reader[0]["tags"]
            assert "overview" in reader[0]["tags"]

    def test_csv_has_correct_columns(self, tmp_path, db_with_data):
        output = str(tmp_path / "out.csv")
        export_csv(output, db_path=db_with_data, export_all=True)

        with open(output, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert list(reader.fieldnames) == COLUMNS

    def test_export_empty_db(self, tmp_path):
        db_path = str(tmp_path / "empty.db")
        get_db(db_path).close()
        output = str(tmp_path / "out.csv")
        count = export_csv(output, db_path=db_path, export_all=True)

        assert count == 0
        with open(output, encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            assert len(reader) == 0


class TestExportNewColumns:
    """Verify CSV export includes subject, description, and layout_type columns."""

    def test_new_columns_present(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = get_db(db_path)
        conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, slide_count, subject, description) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("deck1", "/path/to/deck1.pptx", "abc123", 1, "My Subject", "My Description"),
        )
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes, layout_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, 1, "Intro", "content", "hash1", "notes", "two_column"),
        )
        conn.commit()
        conn.close()

        output = str(tmp_path / "out.csv")
        export_csv(output, db_path=db_path, export_all=True)

        with open(output, encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            assert len(reader) == 1
            assert reader[0]["subject"] == "My Subject"
            assert reader[0]["description"] == "My Description"
            assert reader[0]["layout_type"] == "two_column"

    def test_new_columns_default_to_empty(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = get_db(db_path)
        conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
            ("deck1", "/path/to/deck1.pptx", "abc123", 1),
        )
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (1, 1, "Intro", "content", "hash1", "notes"),
        )
        conn.commit()
        conn.close()

        output = str(tmp_path / "out.csv")
        export_csv(output, db_path=db_path, export_all=True)

        with open(output, encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            assert len(reader) == 1
            assert reader[0]["subject"] == ""
            assert reader[0]["description"] == ""
            assert reader[0]["layout_type"] == ""

    def test_new_columns_in_header(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = get_db(db_path)
        conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
            ("deck1", "/path/to/deck1.pptx", "abc123", 1),
        )
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (1, 1, "Intro", "content", "hash1", ""),
        )
        conn.commit()
        conn.close()

        output = str(tmp_path / "out.csv")
        export_csv(output, db_path=db_path, export_all=True)

        with open(output, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert "subject" in reader.fieldnames
            assert "description" in reader.fieldnames
            assert "layout_type" in reader.fieldnames
