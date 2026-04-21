"""MCP client infrastructure for connecting to external tool servers."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

logger = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    """Configuration for a single MCP server."""

    name: str
    url: str | None = None
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    auth: str | None = None

    @property
    def transport_type(self) -> str:
        """Return 'stdio' for subprocess servers, 'http' for URL-based."""
        return "stdio" if self.command else "http"

    @property
    def display_url(self) -> str:
        """Human-readable connection string for display."""
        if self.url:
            return self.url
        parts = [self.command] + self.args
        return " ".join(parts)


class MCPManager:
    """Manages connections to configured MCP servers.

    Reads server definitions from a standard mcp_servers.json config file
    (same format as Claude Desktop). Config file is optional -- missing
    file results in zero servers, not an error.
    """

    def __init__(self, config_path: str = "mcp_servers.json"):
        self._servers: dict[str, ServerConfig] = {}
        self._load_config(config_path)

    def _load_config(self, config_path: str) -> None:
        path = Path(config_path)
        if not path.exists():
            logger.debug("MCP config not found: %s", config_path)
            return

        with open(path) as f:
            data = json.load(f)

        for name, cfg in data.get("mcpServers", {}).items():
            self._servers[name] = ServerConfig(
                name=name,
                url=cfg.get("url"),
                command=cfg.get("command"),
                args=cfg.get("args", []),
                env=cfg.get("env", {}),
                auth=cfg.get("auth"),
            )

    @property
    def servers(self) -> dict[str, ServerConfig]:
        """Return a copy of the configured servers dict."""
        return dict(self._servers)

    def _build_client(self, cfg: ServerConfig) -> Client:
        """Create a FastMCP Client for the given server config."""
        kwargs = {}
        if cfg.auth:
            kwargs["auth"] = cfg.auth
        if cfg.url:
            return Client(cfg.url, **kwargs)
        transport = StdioTransport(
            command=cfg.command, args=cfg.args, env=cfg.env or None
        )
        return Client(transport, **kwargs)

    async def list_tools(self, server_name: str) -> list:
        """Connect to a server and list its available tools."""
        if server_name not in self._servers:
            raise KeyError(f"Unknown MCP server: {server_name}")
        client = self._build_client(self._servers[server_name])
        async with client:
            return await client.list_tools()

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict
    ) -> Any:
        """Call a tool on a named server."""
        if server_name not in self._servers:
            raise KeyError(f"Unknown MCP server: {server_name}")
        client = self._build_client(self._servers[server_name])
        async with client:
            return await client.call_tool(tool_name, arguments)
