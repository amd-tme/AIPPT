"""Tests for the MCP client infrastructure."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMCPManagerConfigLoading:
    """Test MCPManager loads server config from JSON."""

    def test_load_valid_config(self, tmp_path):
        config = {
            "mcpServers": {
                "image-gen": {
                    "url": "https://mcp.example.com/mcp",
                    "auth": "oauth",
                },
                "playwright": {
                    "command": "npx",
                    "args": ["@playwright/mcp-server"],
                },
            }
        }
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps(config))

        from aippt.mcp import MCPManager

        mgr = MCPManager(str(config_path))
        assert len(mgr.servers) == 2
        assert "image-gen" in mgr.servers
        assert "playwright" in mgr.servers

    def test_load_missing_config(self, tmp_path):
        from aippt.mcp import MCPManager

        mgr = MCPManager(str(tmp_path / "nonexistent.json"))
        assert len(mgr.servers) == 0

    def test_load_malformed_config(self, tmp_path):
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text("not valid json {{{")

        from aippt.mcp import MCPManager

        with pytest.raises(json.JSONDecodeError):
            MCPManager(str(config_path))

    def test_load_empty_servers(self, tmp_path):
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps({"mcpServers": {}}))

        from aippt.mcp import MCPManager

        mgr = MCPManager(str(config_path))
        assert len(mgr.servers) == 0

    def test_server_config_http(self, tmp_path):
        config = {
            "mcpServers": {
                "my-server": {
                    "url": "https://mcp.example.com/mcp",
                    "auth": "oauth",
                }
            }
        }
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps(config))

        from aippt.mcp import MCPManager

        mgr = MCPManager(str(config_path))
        cfg = mgr.servers["my-server"]
        assert cfg.name == "my-server"
        assert cfg.url == "https://mcp.example.com/mcp"
        assert cfg.auth == "oauth"
        assert cfg.transport_type == "http"
        assert cfg.display_url == "https://mcp.example.com/mcp"

    def test_server_config_stdio(self, tmp_path):
        config = {
            "mcpServers": {
                "local-tool": {
                    "command": "npx",
                    "args": ["@example/server"],
                    "env": {"NODE_ENV": "production"},
                }
            }
        }
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps(config))

        from aippt.mcp import MCPManager

        mgr = MCPManager(str(config_path))
        cfg = mgr.servers["local-tool"]
        assert cfg.transport_type == "stdio"
        assert cfg.command == "npx"
        assert cfg.args == ["@example/server"]
        assert cfg.env == {"NODE_ENV": "production"}
        assert cfg.display_url == "npx @example/server"


class TestMCPManagerClientBuilding:
    """Test _build_client creates Client with correct params."""

    def test_build_client_http(self, tmp_path):
        config = {"mcpServers": {"srv": {"url": "https://example.com/mcp"}}}
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps(config))

        from aippt.mcp import MCPManager

        with patch("aippt.mcp.Client") as MockClient:
            mgr = MCPManager(str(config_path))
            mgr._build_client(mgr.servers["srv"])
            MockClient.assert_called_once_with("https://example.com/mcp")

    def test_build_client_http_with_oauth(self, tmp_path):
        config = {"mcpServers": {"srv": {"url": "https://example.com/mcp", "auth": "oauth"}}}
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps(config))

        from aippt.mcp import MCPManager

        with patch("aippt.mcp.Client") as MockClient:
            mgr = MCPManager(str(config_path))
            mgr._build_client(mgr.servers["srv"])
            MockClient.assert_called_once_with("https://example.com/mcp", auth="oauth")

    def test_build_client_stdio(self, tmp_path):
        config = {"mcpServers": {"srv": {"command": "npx", "args": ["@pw/server"]}}}
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps(config))

        from aippt.mcp import MCPManager

        with patch("aippt.mcp.Client") as MockClient:
            with patch("aippt.mcp.StdioTransport") as MockTransport:
                mgr = MCPManager(str(config_path))
                mgr._build_client(mgr.servers["srv"])
                MockTransport.assert_called_once_with(
                    command="npx", args=["@pw/server"], env=None
                )
                MockClient.assert_called_once_with(MockTransport.return_value)

    def test_build_client_stdio_no_args(self, tmp_path):
        config = {"mcpServers": {"srv": {"command": "my-server"}}}
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps(config))

        from aippt.mcp import MCPManager

        with patch("aippt.mcp.Client") as MockClient:
            with patch("aippt.mcp.StdioTransport") as MockTransport:
                mgr = MCPManager(str(config_path))
                mgr._build_client(mgr.servers["srv"])
                MockTransport.assert_called_once_with(
                    command="my-server", args=[], env=None
                )
                MockClient.assert_called_once_with(MockTransport.return_value)


class TestMCPManagerListTools:
    """Test list_tools connects to server and returns tools."""

    def test_list_tools_success(self, tmp_path):
        config = {"mcpServers": {"srv": {"url": "http://localhost:8000/mcp"}}}
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps(config))

        tool1 = MagicMock()
        tool1.name = "generate_image"
        tool1.description = "Generate an image from text"
        tool2 = MagicMock()
        tool2.name = "edit_image"
        tool2.description = "Edit an existing image"

        mock_client = AsyncMock()
        mock_client.list_tools.return_value = [tool1, tool2]

        from aippt.mcp import MCPManager

        with patch("aippt.mcp.Client", return_value=mock_client):
            mgr = MCPManager(str(config_path))
            tools = asyncio.run(mgr.list_tools("srv"))
            assert len(tools) == 2
            assert tools[0].name == "generate_image"
            assert tools[1].name == "edit_image"

    def test_list_tools_unknown_server(self, tmp_path):
        config = {"mcpServers": {}}
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps(config))

        from aippt.mcp import MCPManager

        mgr = MCPManager(str(config_path))
        with pytest.raises(KeyError, match="Unknown MCP server"):
            asyncio.run(mgr.list_tools("nonexistent"))

    def test_list_tools_connection_error(self, tmp_path):
        config = {"mcpServers": {"srv": {"url": "http://localhost:9999/mcp"}}}
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps(config))

        mock_client = AsyncMock()
        mock_client.__aenter__.side_effect = ConnectionError("refused")

        from aippt.mcp import MCPManager

        with patch("aippt.mcp.Client", return_value=mock_client):
            mgr = MCPManager(str(config_path))
            with pytest.raises(ConnectionError):
                asyncio.run(mgr.list_tools("srv"))


class TestMCPManagerCallTool:
    """Test call_tool invokes a tool on a server."""

    def test_call_tool_success(self, tmp_path):
        config = {"mcpServers": {"srv": {"url": "http://localhost:8000/mcp"}}}
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps(config))

        mock_result = MagicMock()
        mock_result.content = [MagicMock(text="image data")]

        mock_client = AsyncMock()
        mock_client.call_tool.return_value = mock_result

        from aippt.mcp import MCPManager

        with patch("aippt.mcp.Client", return_value=mock_client):
            mgr = MCPManager(str(config_path))
            result = asyncio.run(mgr.call_tool("srv", "generate_image", {"prompt": "a cat"}))
            mock_client.call_tool.assert_called_once_with("generate_image", {"prompt": "a cat"})
            assert result == mock_result

    def test_call_tool_unknown_server(self, tmp_path):
        config = {"mcpServers": {}}
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps(config))

        from aippt.mcp import MCPManager

        mgr = MCPManager(str(config_path))
        with pytest.raises(KeyError, match="Unknown MCP server"):
            asyncio.run(mgr.call_tool("nope", "tool", {}))
