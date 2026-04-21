"""Tests for the 'mcp' CLI subcommand group."""

import argparse
import json
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from aippt.cli import cmd_mcp


def _make_args(**kwargs):
    """Create a namespace with defaults for cmd_mcp."""
    defaults = {
        "command": "mcp",
        "mcp_action": None,
        "config": "mcp_servers.json",
        "json": False,
        "debug": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestMCPListNoConfig:
    def test_no_config_file(self, tmp_path, capsys):
        args = _make_args(mcp_action="list", config=str(tmp_path / "nope.json"))
        result = cmd_mcp(args)
        assert result == 0
        output = capsys.readouterr().out
        assert "No MCP servers configured" in output

    def test_default_action_is_list(self, tmp_path, capsys):
        args = _make_args(mcp_action=None, config=str(tmp_path / "nope.json"))
        result = cmd_mcp(args)
        assert result == 0
        assert "No MCP servers configured" in capsys.readouterr().out


class TestMCPListWithServers:
    @pytest.fixture
    def config_path(self, tmp_path):
        config = {
            "mcpServers": {
                "image-gen": {
                    "url": "https://mcp.example.com/mcp",
                    "auth": "oauth",
                },
                "local-tool": {
                    "command": "npx",
                    "args": ["@example/server"],
                },
            }
        }
        path = tmp_path / "mcp_servers.json"
        path.write_text(json.dumps(config))
        return str(path)

    def test_list_shows_servers_and_tools(self, config_path, capsys):
        tool1 = MagicMock()
        tool1.name = "generate_image"
        tool1.description = "Generate an image from text"

        tool2 = MagicMock()
        tool2.name = "screenshot"
        tool2.description = "Take a screenshot"

        clients = iter([AsyncMock(list_tools=AsyncMock(return_value=[tool1])),
                        AsyncMock(list_tools=AsyncMock(return_value=[tool2]))])

        with patch("aippt.mcp.Client", side_effect=lambda *a, **kw: next(clients)):
            args = _make_args(mcp_action="list", config=config_path)
            result = cmd_mcp(args)

        assert result == 0
        output = capsys.readouterr().out
        assert "image-gen" in output
        assert "https://mcp.example.com/mcp" in output
        assert "http" in output
        assert "oauth" in output
        assert "generate_image" in output
        assert "Generate an image from text" in output
        assert "local-tool" in output
        assert "screenshot" in output

    def test_list_connection_error(self, config_path, capsys):
        mock_client = AsyncMock()
        mock_client.__aenter__.side_effect = ConnectionError("refused")

        with patch("aippt.mcp.Client", return_value=mock_client):
            args = _make_args(mcp_action="list", config=config_path)
            result = cmd_mcp(args)

        assert result == 0  # continues past errors
        output = capsys.readouterr().out
        assert "Error" in output or "error" in output

    def test_list_json_output(self, config_path, capsys):
        tool = MagicMock()
        tool.name = "generate_image"
        tool.description = "Generate an image"

        mock_client = AsyncMock()
        mock_client.list_tools.return_value = [tool]

        with patch("aippt.mcp.Client", return_value=mock_client):
            args = _make_args(mcp_action="list", config=config_path, json=True)
            result = cmd_mcp(args)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert "image-gen" in data
        assert "local-tool" in data
