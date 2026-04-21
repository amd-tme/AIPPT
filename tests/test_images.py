"""Tests for aippt.images module."""

import asyncio
import base64
import hashlib
import os
import tempfile

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aippt.images import (
    setup_image_directory,
    save_diagram,
    generate_diagram_svg,
    generate_mcp_image,
    _mcp_cache_key,
)


class TestSetupImageDirectory:
    def test_creates_directory(self, tmp_path):
        output_pptx = str(tmp_path / "presentation.pptx")

        with patch('aippt.images.os.makedirs') as mock_makedirs:
            result = setup_image_directory(output_pptx)

            mock_makedirs.assert_called_once()
            assert 'presentation' in result
            assert 'images' in result

    def test_includes_timestamp(self):
        with patch('aippt.images.os.makedirs'):
            result = setup_image_directory("test.pptx")

            # Should contain date-like pattern
            parts = os.path.basename(result).split('-')
            assert len(parts) >= 2  # name-timestamp format

    def test_handles_path_with_directories(self):
        with patch('aippt.images.os.makedirs'):
            result = setup_image_directory("/path/to/output.pptx")

            assert 'output' in result
            assert '/path/to' not in result  # Should only use basename


class TestSaveDiagram:
    def test_saves_svg_as_text(self, tmp_path):
        image_dir = str(tmp_path)
        svg_content = "<svg><rect/></svg>"

        result = save_diagram(svg_content, image_dir, 1, 'svg')

        assert result.endswith('.svg')
        assert os.path.exists(result)
        with open(result) as f:
            assert f.read() == svg_content

    def test_saves_png_as_binary(self, tmp_path):
        image_dir = str(tmp_path)
        png_content = b'\x89PNG\r\n\x1a\n'  # PNG magic bytes

        result = save_diagram(png_content, image_dir, 2, 'png')

        assert result.endswith('.png')
        assert os.path.exists(result)
        with open(result, 'rb') as f:
            assert f.read() == png_content

    def test_names_file_with_slide_number(self, tmp_path):
        image_dir = str(tmp_path)

        result = save_diagram("<svg/>", image_dir, 5, 'svg')

        assert 'slide05' in result

    def test_zero_pads_slide_number(self, tmp_path):
        image_dir = str(tmp_path)

        result = save_diagram("<svg/>", image_dir, 3, 'svg')

        assert 'slide03' in result


class TestGenerateDiagramSvg:
    @patch('aippt.images.LLMClient')
    def test_calls_generate_text(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "<svg><rect/></svg>"

        result = generate_diagram_svg("A simple box", mock_client)

        mock_client.generate_text.assert_called_once()
        assert '<svg>' in result

    @patch('aippt.images.LLMClient')
    def test_extracts_svg_from_explanation(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = (
            "Here is the diagram:\n\n"
            "<svg viewBox=\"0 0 800 600\"><rect/></svg>\n\n"
            "This shows a rectangle."
        )

        result = generate_diagram_svg("A rectangle", mock_client)

        assert result.startswith('<svg')
        assert result.endswith('</svg>')
        assert 'Here is the diagram' not in result

    @patch('aippt.images.LLMClient')
    def test_returns_raw_if_no_svg_tags(self, mock_client_cls):
        mock_client = MagicMock()
        raw_response = "Some non-SVG response"
        mock_client.generate_text.return_value = raw_response

        result = generate_diagram_svg("Something", mock_client)

        assert result == raw_response

    @patch('aippt.images.LLMClient')
    def test_uses_low_temperature(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "<svg/>"

        generate_diagram_svg("description", mock_client)

        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert call_kwargs['temperature'] <= 0.3

    @patch('aippt.images.LLMClient')
    def test_includes_description_in_prompt(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "<svg/>"

        generate_diagram_svg("A flowchart showing user login", mock_client)

        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert "A flowchart showing user login" in call_kwargs['prompt']


class TestMCPCacheKey:
    def test_cache_key_deterministic(self):
        key1 = _mcp_cache_key("a cat", "model-1", "16:9")
        key2 = _mcp_cache_key("a cat", "model-1", "16:9")
        assert key1 == key2

    def test_cache_key_differs_by_prompt(self):
        key1 = _mcp_cache_key("a cat", "model-1", "16:9")
        key2 = _mcp_cache_key("a dog", "model-1", "16:9")
        assert key1 != key2

    def test_cache_key_differs_by_model(self):
        key1 = _mcp_cache_key("a cat", "model-1", "16:9")
        key2 = _mcp_cache_key("a cat", "model-2", "16:9")
        assert key1 != key2

    def test_cache_key_differs_by_aspect(self):
        key1 = _mcp_cache_key("a cat", "model-1", "16:9")
        key2 = _mcp_cache_key("a cat", "model-1", "4:3")
        assert key1 != key2

    def test_cache_key_is_12_hex_chars(self):
        key = _mcp_cache_key("prompt", "model", "16:9")
        assert len(key) == 12
        assert all(c in '0123456789abcdef' for c in key)


class TestGenerateMCPImage:
    def test_calls_mcp_tool(self, tmp_path):
        mock_manager = MagicMock()
        mock_result = MagicMock()
        fake_png = b'\x89PNG\r\n\x1a\nfake image data'
        mock_result.content = [MagicMock(text=base64.b64encode(fake_png).decode())]
        mock_manager.call_tool = AsyncMock(return_value=mock_result)

        result = asyncio.run(generate_mcp_image(
            prompt="a network diagram",
            output_dir=str(tmp_path),
            slide_num=1,
            mcp_manager=mock_manager,
        ))

        mock_manager.call_tool.assert_called_once()
        call_args = mock_manager.call_tool.call_args
        assert call_args[0][0] == "txt2img"
        assert call_args[0][1] == "generate_slide_image"
        assert "a network diagram" in str(call_args[0][2])

    def test_returns_image_path_on_success(self, tmp_path):
        mock_manager = MagicMock()
        mock_result = MagicMock()
        fake_png = b'\x89PNG\r\n\x1a\nfake'
        mock_result.content = [MagicMock(text=base64.b64encode(fake_png).decode())]
        mock_manager.call_tool = AsyncMock(return_value=mock_result)

        result = asyncio.run(generate_mcp_image(
            prompt="diagram",
            output_dir=str(tmp_path),
            slide_num=3,
            mcp_manager=mock_manager,
        ))

        assert result is not None
        assert result.endswith('.png')
        assert 'slide_03_gen' in result
        assert os.path.exists(result)

    def test_returns_none_on_mcp_error(self, tmp_path):
        mock_manager = MagicMock()
        mock_manager.call_tool = AsyncMock(side_effect=Exception("MCP server down"))

        result = asyncio.run(generate_mcp_image(
            prompt="diagram",
            output_dir=str(tmp_path),
            slide_num=1,
            mcp_manager=mock_manager,
        ))

        assert result is None

    def test_uses_cache_on_identical_prompt(self, tmp_path):
        mock_manager = MagicMock()
        mock_result = MagicMock()
        fake_png = b'\x89PNG\r\n\x1a\nfake'
        mock_result.content = [MagicMock(text=base64.b64encode(fake_png).decode())]
        mock_manager.call_tool = AsyncMock(return_value=mock_result)

        cache_dir = str(tmp_path / "cache")

        result1 = asyncio.run(generate_mcp_image(
            prompt="same prompt",
            output_dir=str(tmp_path),
            slide_num=1,
            mcp_manager=mock_manager,
            cache_dir=cache_dir,
        ))

        result2 = asyncio.run(generate_mcp_image(
            prompt="same prompt",
            output_dir=str(tmp_path),
            slide_num=2,
            mcp_manager=mock_manager,
            cache_dir=cache_dir,
        ))

        assert mock_manager.call_tool.call_count == 1
        assert result1 is not None
        assert result2 is not None
        assert os.path.exists(result2)

    def test_passes_classification(self, tmp_path):
        mock_manager = MagicMock()
        mock_result = MagicMock()
        fake_png = b'\x89PNG\r\n\x1a\nfake'
        mock_result.content = [MagicMock(text=base64.b64encode(fake_png).decode())]
        mock_manager.call_tool = AsyncMock(return_value=mock_result)

        asyncio.run(generate_mcp_image(
            prompt="test",
            output_dir=str(tmp_path),
            slide_num=1,
            mcp_manager=mock_manager,
            classification="confidential",
        ))

        tool_args = mock_manager.call_tool.call_args[0][2]
        assert tool_args["classification"] == "confidential"

    def test_custom_server_name(self, tmp_path):
        mock_manager = MagicMock()
        mock_result = MagicMock()
        fake_png = b'\x89PNG\r\n\x1a\nfake'
        mock_result.content = [MagicMock(text=base64.b64encode(fake_png).decode())]
        mock_manager.call_tool = AsyncMock(return_value=mock_result)

        asyncio.run(generate_mcp_image(
            prompt="test",
            output_dir=str(tmp_path),
            slide_num=1,
            mcp_manager=mock_manager,
            server_name="my-custom-server",
        ))

        assert mock_manager.call_tool.call_args[0][0] == "my-custom-server"
