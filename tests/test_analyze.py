"""Tests for aippt.analyze module."""

import os
import pytest
from unittest.mock import MagicMock, patch

from aippt.analyze import (
    analyze_slide,
    parse_tags_response,
    load_taxonomy,
    _is_placeholder_image,
    FEEDBACK_SYSTEM_PROMPT,
    NOTES_SYSTEM_PROMPT,
    TAGS_SYSTEM_PROMPT_FREEFORM,
    TAGS_SYSTEM_PROMPT_TAXONOMY,
    FEEDBACK_SYSTEM_PROMPT_TEXT,
    NOTES_SYSTEM_PROMPT_TEXT,
    TAGS_SYSTEM_PROMPT_FREEFORM_TEXT,
    TAGS_SYSTEM_PROMPT_TAXONOMY_TEXT,
)


class TestParseTagsResponse:
    def test_basic(self):
        result = parse_tags_response("security, architecture, cloud")
        assert result == ["security", "architecture", "cloud"]

    def test_handles_whitespace(self):
        result = parse_tags_response("  security ,  cloud  , aws ")
        assert result == ["security", "cloud", "aws"]

    def test_empty_string(self):
        result = parse_tags_response("")
        assert result == []

    def test_single_tag(self):
        result = parse_tags_response("security")
        assert result == ["security"]

    def test_normalizes_to_lowercase(self):
        result = parse_tags_response("Security, CLOUD, AWS")
        assert result == ["security", "cloud", "aws"]

    def test_filters_empty_items(self):
        result = parse_tags_response("security,, cloud,  ,aws")
        assert result == ["security", "cloud", "aws"]

    def test_handles_newlines(self):
        result = parse_tags_response("security\n, cloud")
        assert "security" in result
        assert "cloud" in result


class TestLoadTaxonomy:
    def test_load_csv_with_name_column(self, tmp_path):
        csv_file = tmp_path / "tags.csv"
        csv_file.write_text("name,category\nsecurity,topic\ncloud,topic\naws,provider\n")
        result = load_taxonomy(str(csv_file))
        assert result == ["security", "cloud", "aws"]

    def test_load_csv_first_column_fallback(self, tmp_path):
        csv_file = tmp_path / "tags.csv"
        csv_file.write_text("tag,description\nsecurity,Security related\ncloud,Cloud topics\n")
        result = load_taxonomy(str(csv_file))
        assert result == ["security", "cloud"]

    def test_normalizes_to_lowercase(self, tmp_path):
        csv_file = tmp_path / "tags.csv"
        csv_file.write_text("name\nSECURITY\nCloud\nAWS\n")
        result = load_taxonomy(str(csv_file))
        assert result == ["security", "cloud", "aws"]

    def test_skips_empty_rows(self, tmp_path):
        csv_file = tmp_path / "tags.csv"
        csv_file.write_text("name\nsecurity\n\ncloud\n  \n")
        result = load_taxonomy(str(csv_file))
        assert result == ["security", "cloud"]

    def test_empty_file(self, tmp_path):
        csv_file = tmp_path / "tags.csv"
        csv_file.write_text("name\n")
        result = load_taxonomy(str(csv_file))
        assert result == []


class TestIsPlaceholderImage:
    def test_tiny_file_is_placeholder(self, tmp_path):
        img = tmp_path / "tiny.png"
        img.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)  # < 5 KB
        assert _is_placeholder_image(str(img)) is True

    def test_missing_file_returns_false(self, tmp_path):
        assert _is_placeholder_image(str(tmp_path / "nonexistent.png")) is False

    def test_large_file_not_placeholder(self, tmp_path):
        img = tmp_path / "big.png"
        # Write more than 5 KB of non-white data so Pillow (if available) won't flag it
        img.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\xAB' * 6000)
        # File size alone passes; whether Pillow runs depends on environment
        # We only assert that a file larger than 5 KB is not flagged on size alone
        # (Pillow may or may not be able to parse our fake PNG)
        result = _is_placeholder_image(str(img))
        # The file is > 5 KB, so size check alone won't flag it as a placeholder.
        # The Pillow check may raise (fake PNG), so result should be False.
        assert result is False


class TestAnalyzeSlide:
    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.generate_text_with_image.return_value = "Analysis result"
        client.generate_text.return_value = "Analysis result"
        return client

    @pytest.fixture
    def sample_image(self, tmp_path):
        """A PNG file large enough (> 5 KB) to pass the placeholder size check."""
        img_path = tmp_path / "slide.png"
        # PNG magic bytes + enough padding to exceed the 5 KB threshold
        img_path.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\xAB' * 6000)
        return str(img_path)

    @pytest.fixture
    def placeholder_image(self, tmp_path):
        """A tiny PNG file that will be treated as a placeholder."""
        img_path = tmp_path / "placeholder.png"
        img_path.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
        return str(img_path)

    def test_feedback_mode(self, mock_client, sample_image):
        result = analyze_slide(
            client=mock_client,
            image_path=sample_image,
            mode="feedback",
            title="Test Slide",
        )

        mock_client.generate_text_with_image.assert_called_once()
        call_kwargs = mock_client.generate_text_with_image.call_args.kwargs
        assert call_kwargs["system_prompt"] == FEEDBACK_SYSTEM_PROMPT
        assert "Test Slide" in call_kwargs["prompt"]
        assert "feedback" in call_kwargs["prompt"].lower()

    def test_notes_mode(self, mock_client, sample_image):
        result = analyze_slide(
            client=mock_client,
            image_path=sample_image,
            mode="notes",
            title="Test Slide",
        )

        call_kwargs = mock_client.generate_text_with_image.call_args.kwargs
        assert call_kwargs["system_prompt"] == NOTES_SYSTEM_PROMPT
        assert "speaker notes" in call_kwargs["prompt"].lower()

    def test_tags_mode_freeform(self, mock_client, sample_image):
        result = analyze_slide(
            client=mock_client,
            image_path=sample_image,
            mode="tags",
            title="Test Slide",
        )

        call_kwargs = mock_client.generate_text_with_image.call_args.kwargs
        assert call_kwargs["system_prompt"] == TAGS_SYSTEM_PROMPT_FREEFORM
        assert "tags" in call_kwargs["prompt"].lower()

    def test_tags_mode_with_taxonomy(self, mock_client, sample_image):
        taxonomy = ["security", "cloud", "architecture"]
        result = analyze_slide(
            client=mock_client,
            image_path=sample_image,
            mode="tags",
            title="Test Slide",
            taxonomy=taxonomy,
        )

        call_kwargs = mock_client.generate_text_with_image.call_args.kwargs
        assert call_kwargs["system_prompt"] == TAGS_SYSTEM_PROMPT_TAXONOMY
        assert "security" in call_kwargs["prompt"]
        assert "cloud" in call_kwargs["prompt"]

    def test_unknown_mode_raises(self, mock_client, sample_image):
        with pytest.raises(ValueError, match="Unknown analysis mode"):
            analyze_slide(
                client=mock_client,
                image_path=sample_image,
                mode="invalid",
                title="Test",
            )

    def test_uses_low_temperature(self, mock_client, sample_image):
        analyze_slide(
            client=mock_client,
            image_path=sample_image,
            mode="tags",
            title="Test",
        )

        call_kwargs = mock_client.generate_text_with_image.call_args.kwargs
        assert call_kwargs["temperature"] <= 0.5

    def test_returns_client_response(self, mock_client, sample_image):
        mock_client.generate_text_with_image.return_value = "security, cloud, aws"
        result = analyze_slide(
            client=mock_client,
            image_path=sample_image,
            mode="tags",
            title="Test",
        )
        assert result == "security, cloud, aws"

    # ------------------------------------------------------------------
    # Text-only fallback tests
    # ------------------------------------------------------------------

    def test_text_only_when_image_is_none(self, mock_client):
        """No image_path -> generate_text is used, not generate_text_with_image."""
        mock_client.generate_text.return_value = "text-only result"
        result = analyze_slide(
            client=mock_client,
            image_path=None,
            mode="feedback",
            title="My Slide",
            content_text="Bullet one\nBullet two",
        )
        mock_client.generate_text_with_image.assert_not_called()
        mock_client.generate_text.assert_called_once()
        assert "text-only" in result.lower()

    def test_text_only_when_image_path_missing(self, mock_client, tmp_path):
        """Non-existent image path -> falls back to text-only."""
        mock_client.generate_text.return_value = "text-only result"
        result = analyze_slide(
            client=mock_client,
            image_path=str(tmp_path / "no_such_file.png"),
            mode="feedback",
            title="My Slide",
            content_text="Bullet one\nBullet two",
        )
        mock_client.generate_text_with_image.assert_not_called()
        mock_client.generate_text.assert_called_once()
        assert "text-only" in result.lower()

    def test_text_only_when_placeholder_image(self, mock_client, placeholder_image):
        """Tiny placeholder image -> falls back to text-only."""
        mock_client.generate_text.return_value = "text-only result"
        result = analyze_slide(
            client=mock_client,
            image_path=placeholder_image,
            mode="notes",
            title="My Slide",
            content_text="Some content",
        )
        mock_client.generate_text_with_image.assert_not_called()
        mock_client.generate_text.assert_called_once()
        assert "text-only" in result.lower()

    def test_text_only_feedback_uses_text_system_prompt(self, mock_client):
        mock_client.generate_text.return_value = "result"
        analyze_slide(
            client=mock_client,
            image_path=None,
            mode="feedback",
            title="My Slide",
            content_text="Content here",
        )
        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert call_kwargs["system_prompt"] == FEEDBACK_SYSTEM_PROMPT_TEXT
        assert "Content here" in call_kwargs["prompt"]

    def test_text_only_notes_uses_text_system_prompt(self, mock_client):
        mock_client.generate_text.return_value = "result"
        analyze_slide(
            client=mock_client,
            image_path=None,
            mode="notes",
            title="My Slide",
            content_text="Content here",
        )
        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert call_kwargs["system_prompt"] == NOTES_SYSTEM_PROMPT_TEXT

    def test_text_only_tags_freeform(self, mock_client):
        mock_client.generate_text.return_value = "result"
        analyze_slide(
            client=mock_client,
            image_path=None,
            mode="tags",
            title="My Slide",
            content_text="Content here",
        )
        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert call_kwargs["system_prompt"] == TAGS_SYSTEM_PROMPT_FREEFORM_TEXT

    def test_text_only_tags_taxonomy(self, mock_client):
        mock_client.generate_text.return_value = "result"
        analyze_slide(
            client=mock_client,
            image_path=None,
            mode="tags",
            title="My Slide",
            content_text="Content here",
            taxonomy=["security", "cloud"],
        )
        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert call_kwargs["system_prompt"] == TAGS_SYSTEM_PROMPT_TAXONOMY_TEXT
        assert "security" in call_kwargs["prompt"]

    def test_text_only_content_included_in_prompt(self, mock_client):
        """Slide body text is included in the text-only prompt."""
        mock_client.generate_text.return_value = "result"
        analyze_slide(
            client=mock_client,
            image_path=None,
            mode="feedback",
            title="My Slide",
            content_text="Key point one\nKey point two",
        )
        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert "Key point one" in call_kwargs["prompt"]
        assert "Key point two" in call_kwargs["prompt"]

    def test_text_only_note_appended_to_result(self, mock_client):
        """The text-only note is appended to every text-only result."""
        mock_client.generate_text.return_value = "Here is the analysis."
        result = analyze_slide(
            client=mock_client,
            image_path=None,
            mode="improvements",
            title="My Slide",
        )
        assert "Here is the analysis." in result
        assert "[Note:" in result
        assert "text only" in result.lower()

    def test_text_only_uses_low_temperature(self, mock_client):
        mock_client.generate_text.return_value = "result"
        analyze_slide(
            client=mock_client,
            image_path=None,
            mode="tags",
            title="Test",
        )
        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert call_kwargs["temperature"] <= 0.5


class TestSystemPrompts:
    def test_feedback_prompt_mentions_feedback(self):
        assert "feedback" in FEEDBACK_SYSTEM_PROMPT.lower()

    def test_notes_prompt_mentions_speaker(self):
        assert "speaker" in NOTES_SYSTEM_PROMPT.lower()

    def test_tags_freeform_prompt_mentions_tags(self):
        assert "tags" in TAGS_SYSTEM_PROMPT_FREEFORM.lower()

    def test_tags_taxonomy_prompt_mentions_allowed(self):
        assert "allowed" in TAGS_SYSTEM_PROMPT_TAXONOMY.lower()
