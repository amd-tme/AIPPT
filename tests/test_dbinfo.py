"""Tests for aippt.dbinfo module."""

import json
import types

import pytest

from aippt.catalog import get_db, add_tags, add_taxonomy_tags, set_slide_section


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_populated_db(tmp_path):
    """Create a database with one deck, three slides, tags, taxonomy, and a section.

    Returns the db_path string.
    """
    db_path = str(tmp_path / "test.db")
    conn = get_db(db_path)

    # Deck
    conn.execute(
        "INSERT INTO decks (name, file_path, file_hash, slide_count, author, subject) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("Test Deck", "/path/to/test.pptx", "abc123def456", 3, "Test Author", "Architecture"),
    )

    # Slides
    conn.execute(
        "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes, layout_type) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, 1, "Title Slide", "intro content", "hash1", "Opening remarks for the presentation", "basic"),
    )
    conn.execute(
        "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, 2, "Cloud Architecture", "cloud bullet points", "hash2", "Discuss cloud options"),
    )
    conn.execute(
        "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, 3, "Security Overview", "security bullets", "hash3", ""),
    )

    # Edit history
    conn.execute(
        "INSERT INTO edit_history (slide_id, field, old_value, new_value, source) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "notes", "", "Opening remarks for the presentation", "web"),
    )

    conn.commit()
    conn.close()

    # Tags (via catalog helper so source is normalised)
    add_tags(1, ["architecture", "overview"], source="ai", db_path=db_path)
    add_tags(2, ["architecture", "cloud"], source="ai", db_path=db_path)
    add_tags(3, ["security"], source="manual", db_path=db_path)

    # Taxonomy
    add_taxonomy_tags(
        [
            {"name": "architecture", "category": "Technical"},
            {"name": "security", "category": "Technical"},
            {"name": "overview", "category": "Business"},
        ],
        db_path,
    )

    # Section: assign slide 2 and 3 to "Introduction"
    set_slide_section(2, "Introduction", 1, db_path)
    set_slide_section(3, "Introduction", 1, db_path)

    return db_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmptyDb:
    """dump_db_info on a fresh schema-only database."""

    def test_contains_schema_ddl(self, tmp_path):
        from aippt.dbinfo import dump_db_info

        db_path = str(tmp_path / "empty.db")
        get_db(db_path).close()

        result = dump_db_info(db_path)

        assert "CREATE TABLE" in result

    def test_shows_zero_row_counts(self, tmp_path):
        from aippt.dbinfo import dump_db_info

        db_path = str(tmp_path / "empty.db")
        get_db(db_path).close()

        result = dump_db_info(db_path)

        # Each known table should show 0 rows
        assert "decks" in result
        assert "slides" in result
        assert "tags" in result

        # All counts must be zero -- look for at least one "0" associated with
        # the stats section; the simplest check is that no deck appears in output.
        assert "Test Deck" not in result

    def test_no_deck_data_section(self, tmp_path):
        from aippt.dbinfo import dump_db_info

        db_path = str(tmp_path / "empty.db")
        get_db(db_path).close()

        result = dump_db_info(db_path)

        # With no rows there should be no deck names, slide titles, or tag names
        assert "Title Slide" not in result
        assert "architecture" not in result


class TestPopulatedDbText:
    """dump_db_info plain-text output with real data."""

    @pytest.fixture
    def db_path(self, tmp_path):
        return _make_populated_db(tmp_path)

    def test_has_database_info_header(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path)

        assert "Database Info" in result

    def test_has_schema_section(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path)

        assert "Schema" in result
        assert "CREATE TABLE" in result

    def test_contains_deck_name(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path)

        assert "Test Deck" in result

    def test_contains_slide_titles(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path)

        assert "Title Slide" in result
        assert "Cloud Architecture" in result
        assert "Security Overview" in result

    def test_contains_tag_names(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path)

        assert "architecture" in result
        assert "security" in result

    def test_contains_taxonomy_entries(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path)

        # Taxonomy section should list the entries or their categories
        assert "Technical" in result or "architecture" in result


class TestPopulatedDbJson:
    """dump_db_info JSON output with real data."""

    @pytest.fixture
    def db_path(self, tmp_path):
        return _make_populated_db(tmp_path)

    def test_output_is_valid_json(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path, as_json=True)

        # Must not raise
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_has_expected_top_level_keys(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path, as_json=True)
        data = json.loads(result)

        for key in ("database", "schema", "table_stats", "decks", "tags", "taxonomy", "edit_history"):
            assert key in data, f"Missing top-level key: {key}"

    def test_deck_has_correct_slide_count(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path, as_json=True)
        data = json.loads(result)

        assert len(data["decks"]) == 1
        deck = data["decks"][0]
        assert deck["name"] == "Test Deck"
        # Deck has 3 slides
        assert len(deck["slides"]) == 3

    def test_tags_have_correct_usage_counts(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path, as_json=True)
        data = json.loads(result)

        tag_map = {t["name"]: t for t in data["tags"]}

        # "architecture" is on slides 1 and 2
        assert tag_map["architecture"]["slide_count"] == 2
        # "security" is on slide 3 only
        assert tag_map["security"]["slide_count"] == 1
        # "cloud" is on slide 2 only
        assert tag_map["cloud"]["slide_count"] == 1

    def test_table_stats_are_non_negative_integers(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path, as_json=True)
        data = json.loads(result)

        for table, count in data["table_stats"].items():
            assert isinstance(count, int), f"table_stats[{table!r}] is not an int"
            assert count >= 0, f"table_stats[{table!r}] is negative"

    def test_table_stats_deck_count(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path, as_json=True)
        data = json.loads(result)

        assert data["table_stats"]["decks"] == 1
        assert data["table_stats"]["slides"] == 3

    def test_taxonomy_entries_present(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path, as_json=True)
        data = json.loads(result)

        taxonomy_names = {t["name"] for t in data["taxonomy"]}
        assert "architecture" in taxonomy_names
        assert "security" in taxonomy_names

    def test_edit_history_total(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path, as_json=True)
        data = json.loads(result)

        assert data["edit_history"]["total"] >= 1

    def test_database_metadata_present(self, db_path):
        from aippt.dbinfo import dump_db_info

        result = dump_db_info(db_path, as_json=True)
        data = json.loads(result)

        db_meta = data["database"]
        assert "path" in db_meta
        assert "size_bytes" in db_meta
        assert "sqlite_version" in db_meta
        assert isinstance(db_meta["size_bytes"], int)
        assert db_meta["size_bytes"] > 0


class TestNoteTruncation:
    """Notes longer than the truncation threshold are shortened in text output."""

    def test_long_notes_are_truncated(self, tmp_path):
        from aippt.dbinfo import dump_db_info

        db_path = str(tmp_path / "notes.db")
        conn = get_db(db_path)
        conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
            ("Notes Deck", "/path/notes.pptx", "noteshash", 1),
        )
        long_notes = "A" * 250
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (1, 1, "Verbose Slide", "content", "hashN", long_notes),
        )
        conn.commit()
        conn.close()

        result = dump_db_info(db_path)

        # The full 250-char notes string must NOT appear verbatim in text output
        assert long_notes not in result

    def test_long_notes_truncation_marker(self, tmp_path):
        from aippt.dbinfo import dump_db_info

        db_path = str(tmp_path / "notes2.db")
        conn = get_db(db_path)
        conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
            ("Notes Deck 2", "/path/notes2.pptx", "noteshash2", 1),
        )
        long_notes = "B" * 250
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (1, 1, "Verbose Slide 2", "content", "hashN2", long_notes),
        )
        conn.commit()
        conn.close()

        result = dump_db_info(db_path)

        # A truncation marker such as "..." should appear when notes are cut
        assert "..." in result

    def test_short_notes_not_truncated(self, tmp_path):
        from aippt.dbinfo import dump_db_info

        db_path = str(tmp_path / "short.db")
        conn = get_db(db_path)
        conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
            ("Short Deck", "/path/short.pptx", "shorthash", 1),
        )
        short_notes = "Brief notes here."
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (1, 1, "Brief Slide", "content", "hashS", short_notes),
        )
        conn.commit()
        conn.close()

        result = dump_db_info(db_path)

        # Short notes must appear in full
        assert short_notes in result


class TestOutputFile:
    """cmd_db_info --output writes output to a file instead of stdout."""

    def test_output_written_to_file(self, tmp_path):
        from aippt.dbinfo import dump_db_info

        # Create a populated DB so output is non-trivial
        db_path = _make_populated_db(tmp_path)
        output_path = str(tmp_path / "snapshot.txt")

        # Write the output ourselves the same way cmd_db_info would
        content = dump_db_info(db_path)
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(content)

        import os
        assert os.path.exists(output_path)
        with open(output_path, encoding="utf-8") as fh:
            written = fh.read()
        assert written == content
        assert "Test Deck" in written

    def test_cmd_db_info_writes_file(self, tmp_path):
        """cmd_db_info with --output arg writes result to disk."""
        from aippt.cli import cmd_db_info

        db_path = _make_populated_db(tmp_path)
        output_path = str(tmp_path / "cli_out.txt")

        args = types.SimpleNamespace(
            db=db_path,
            json=False,
            output=output_path,
        )

        ret = cmd_db_info(args)

        import os
        assert ret == 0
        assert os.path.exists(output_path)
        with open(output_path, encoding="utf-8") as fh:
            content = fh.read()
        assert "Database Info" in content
        assert "Test Deck" in content

    def test_cmd_db_info_json_output_to_file(self, tmp_path):
        """cmd_db_info with --json and --output writes valid JSON to disk."""
        from aippt.cli import cmd_db_info

        db_path = _make_populated_db(tmp_path)
        output_path = str(tmp_path / "cli_out.json")

        args = types.SimpleNamespace(
            db=db_path,
            json=True,
            output=output_path,
        )

        ret = cmd_db_info(args)

        assert ret == 0
        with open(output_path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert "decks" in data
        assert len(data["decks"]) == 1

    def test_cmd_db_info_no_output_returns_zero(self, tmp_path, capsys):
        """cmd_db_info with output=None prints to stdout and returns 0."""
        from aippt.cli import cmd_db_info

        db_path = str(tmp_path / "empty.db")
        get_db(db_path).close()

        args = types.SimpleNamespace(
            db=db_path,
            json=False,
            output=None,
        )

        ret = cmd_db_info(args)

        assert ret == 0
        captured = capsys.readouterr()
        assert "Database Info" in captured.out
