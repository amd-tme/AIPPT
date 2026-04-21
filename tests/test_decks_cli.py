"""Tests for the 'decks' CLI subcommand group."""

import argparse
import json
import os
from unittest.mock import patch

import pytest

from aippt.catalog import get_db, display_name
from aippt.cli import cmd_decks


def _make_args(**kwargs):
    """Create a namespace with defaults for cmd_decks."""
    defaults = {
        "command": "decks",
        "decks_action": None,
        "db": None,
        "json": False,
        "debug": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@pytest.fixture
def db_with_decks(tmp_path):
    """Database with two decks, slides, tags, and sections."""
    db_path = str(tmp_path / "test.db")
    conn = get_db(db_path)
    conn.execute(
        "INSERT INTO decks (name, file_path, file_hash, slide_count, author) VALUES (?, ?, ?, ?, ?)",
        ("Networking Advantages", "uploads/net.pptx", "abc", 10, "Matt Elliott"),
    )
    conn.execute(
        "INSERT INTO decks (name, file_path, file_hash, slide_count, author) VALUES (?, ?, ?, ?, ?)",
        ("Deploying AMD Instinct", "uploads/instinct.pptx", "def", 18, "Matt Elliott"),
    )
    # Add slides to deck 1
    for i in range(1, 11):
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash, image_path) VALUES (?, ?, ?, ?, ?, ?)",
            (1, i, f"Slide {i}", f"content{i}", f"hash{i}", f"images/net/Slide{i}.PNG" if i <= 3 else None),
        )
    # Add slides to deck 2
    for i in range(1, 19):
        conn.execute(
            "INSERT INTO slides (deck_id, position, title, content_text, content_hash) VALUES (?, ?, ?, ?, ?)",
            (2, i, f"Instinct Slide {i}", f"content{i}", f"ihash{i}"),
        )
    # Tags
    conn.execute("INSERT INTO tags (name, source) VALUES (?, ?)", ("security", "ai"))
    conn.execute("INSERT INTO tags (name, source) VALUES (?, ?)", ("networking", "ai"))
    conn.execute("INSERT INTO slide_tags (slide_id, tag_id) VALUES (?, ?)", (1, 1))
    conn.execute("INSERT INTO slide_tags (slide_id, tag_id) VALUES (?, ?)", (1, 2))
    conn.execute("INSERT INTO slide_tags (slide_id, tag_id) VALUES (?, ?)", (2, 1))
    # Sections
    conn.execute("INSERT INTO sections (deck_id, name, position) VALUES (?, ?, ?)", (1, "intro", 1))
    conn.execute("INSERT INTO slide_sections (slide_id, section_id) VALUES (?, ?)", (1, 1))
    conn.commit()
    conn.close()
    return db_path


class TestDecksListCmd:
    def test_list_shows_decks(self, db_with_decks, capsys):
        args = _make_args(decks_action="list", db=db_with_decks)
        result = cmd_decks(args)
        assert result == 0
        output = capsys.readouterr().out
        assert "Networking Advantages" in output
        assert "Deploying AMD Instinct" in output
        assert "2 decks, 28 slides total" in output

    def test_list_json(self, db_with_decks, capsys):
        args = _make_args(decks_action="list", db=db_with_decks, json=True)
        result = cmd_decks(args)
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 2

    def test_list_empty_db(self, tmp_path, capsys):
        db_path = str(tmp_path / "empty.db")
        conn = get_db(db_path)
        conn.close()
        args = _make_args(decks_action="list", db=db_path)
        result = cmd_decks(args)
        assert result == 0
        assert "No decks" in capsys.readouterr().out

    def test_default_action_same_as_list(self, db_with_decks, capsys):
        args = _make_args(decks_action=None, db=db_with_decks)
        result = cmd_decks(args)
        assert result == 0
        assert "Networking Advantages" in capsys.readouterr().out


class TestDecksInfoCmd:
    def test_info_by_id(self, db_with_decks, capsys):
        args = _make_args(decks_action="info", deck="1", db=db_with_decks)
        result = cmd_decks(args)
        assert result == 0
        output = capsys.readouterr().out
        assert "Networking Advantages" in output
        assert "Slide 1" in output

    def test_info_by_name(self, db_with_decks, capsys):
        args = _make_args(decks_action="info", deck="instinct", db=db_with_decks)
        result = cmd_decks(args)
        assert result == 0
        assert "Deploying AMD Instinct" in capsys.readouterr().out

    def test_info_not_found(self, db_with_decks, capsys):
        args = _make_args(decks_action="info", deck="nonexistent", db=db_with_decks)
        result = cmd_decks(args)
        assert result == 1
        assert "No deck found" in capsys.readouterr().out

    def test_info_json(self, db_with_decks, capsys):
        args = _make_args(decks_action="info", deck="1", db=db_with_decks, json=True)
        result = cmd_decks(args)
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["name"] == "Networking Advantages"
        assert "slides" in data

    def test_info_shows_tags(self, db_with_decks, capsys):
        args = _make_args(decks_action="info", deck="1", db=db_with_decks)
        result = cmd_decks(args)
        assert result == 0
        output = capsys.readouterr().out
        assert "Tags" in output
        assert "security" in output


class TestDecksRenameCmd:
    def test_rename_by_id(self, db_with_decks, capsys):
        args = _make_args(decks_action="rename", deck="1", new_name="New Name", db=db_with_decks)
        result = cmd_decks(args)
        assert result == 0
        output = capsys.readouterr().out
        assert "Renamed" in output
        assert "New Name" in output

    def test_rename_not_found(self, db_with_decks, capsys):
        args = _make_args(decks_action="rename", deck="999", new_name="X", db=db_with_decks)
        result = cmd_decks(args)
        assert result == 1


class TestDecksDeleteCmd:
    def test_delete_with_force(self, db_with_decks, capsys):
        args = _make_args(decks_action="delete", deck="2", db=db_with_decks, force=True, purge_images=False)
        result = cmd_decks(args)
        assert result == 0
        output = capsys.readouterr().out
        assert "Deleted" in output
        assert "Deploying AMD Instinct" in output
        # Verify it's gone
        conn = get_db(db_with_decks)
        assert conn.execute("SELECT COUNT(*) FROM decks").fetchone()[0] == 1
        conn.close()

    def test_delete_with_confirmation(self, db_with_decks, capsys):
        args = _make_args(decks_action="delete", deck="1", db=db_with_decks, force=False, purge_images=False)
        with patch("builtins.input", return_value="yes"):
            result = cmd_decks(args)
        assert result == 0
        assert "Deleted" in capsys.readouterr().out

    def test_delete_aborted(self, db_with_decks, capsys):
        args = _make_args(decks_action="delete", deck="1", db=db_with_decks, force=False, purge_images=False)
        with patch("builtins.input", return_value="no"):
            result = cmd_decks(args)
        assert result == 1
        assert "Aborted" in capsys.readouterr().out

    def test_delete_not_found(self, db_with_decks, capsys):
        args = _make_args(decks_action="delete", deck="999", db=db_with_decks, force=True, purge_images=False)
        result = cmd_decks(args)
        assert result == 1

    def test_delete_purge_images(self, db_with_decks, tmp_path, capsys):
        # Create the image directory
        img_dir = tmp_path / "images" / "net"
        img_dir.mkdir(parents=True)
        (img_dir / "Slide1.PNG").write_text("fake")
        # Update image_path to point to the temp dir
        conn = get_db(db_with_decks)
        conn.execute("UPDATE slides SET image_path = ? WHERE deck_id = 1 AND position = 1",
                      (str(img_dir / "Slide1.PNG"),))
        conn.commit()
        conn.close()
        args = _make_args(decks_action="delete", deck="1", db=db_with_decks, force=True, purge_images=True)
        result = cmd_decks(args)
        assert result == 0
        assert not img_dir.exists()

    def test_delete_shows_summary(self, db_with_decks, capsys):
        """Confirmation prompt should show slide/tag/section counts."""
        args = _make_args(decks_action="delete", deck="1", db=db_with_decks, force=False, purge_images=False)
        with patch("builtins.input", return_value="no"):
            cmd_decks(args)
        output = capsys.readouterr().out
        assert "10 slides" in output
        assert "2 tags" in output
        assert "1 sections" in output


class TestDecksAmbiguousMatch:
    def test_ambiguous_name_shows_options(self, db_with_decks, capsys):
        conn = get_db(db_with_decks)
        conn.execute(
            "INSERT INTO decks (name, file_path, file_hash, slide_count) VALUES (?, ?, ?, ?)",
            ("Advanced Networking", "/adv.pptx", "xyz", 5),
        )
        conn.commit()
        conn.close()
        # "network" matches "Networking Advantages" and "Advanced Networking"
        args = _make_args(decks_action="info", deck="network", db=db_with_decks)
        result = cmd_decks(args)
        assert result == 1
        output = capsys.readouterr().out
        assert "Multiple decks" in output
