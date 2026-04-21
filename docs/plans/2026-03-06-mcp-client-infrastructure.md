# MCP Client Infrastructure Layer

**Date:** 2026-03-06
**Status:** Approved
**Branch:** `feature/mcp-client-infrastructure`

## Summary

Add a basic MCP (Model Context Protocol) client layer to aippt using FastMCP's Python client. This provides the infrastructure for connecting to external MCP servers -- initially targeting an internal text-to-image server (Streamable HTTP + OAuth) and Playwright for web screenshots (stdio). This PRD covers only the client infrastructure; agentic enhance integration and specific server integrations are separate follow-up efforts.

## Motivation

- Internal MCP server provides text-to-image generation (NanoBanana and other models) via Streamable HTTP with OAuth
- Playwright MCP server enables automated web screenshots (covers ~95% of slide images)
- MCP is the emerging standard for LLM tool integration -- building the client layer now enables future agentic workflows where the enhance pipeline can call MCP tools directly

## Design Decisions

- **FastMCP client** (Approach A) over raw MCP SDK or subprocess delegation -- mature OAuth handling, token caching, transport auto-detection, and native `mcp_servers.json` config parsing
- **Standard `mcp_servers.json` config** -- uses the MCP ecosystem format (same as Claude Desktop, etc.) for portability; FastMCP reads it natively via `MCPConfig.from_file()`
- **Infrastructure only** -- no enhance pipeline integration yet; just the client module, config, and `mcp list` CLI command
- **`aippt mcp list` CLI** -- read-only command for verifying connectivity and discovering available tools; no `call` command initially

## Architecture

### New Module: `aippt/mcp.py`

```python
class MCPManager:
    """Manages connections to configured MCP servers."""

    def __init__(self, config_path: str = "mcp_servers.json"):
        """Load server definitions from standard MCP config file."""

    async def get_client(self, server_name: str) -> Client:
        """Get or create a connected FastMCP client for a named server."""

    async def list_servers(self) -> list[ServerInfo]:
        """List configured servers with connection status."""

    async def list_tools(self, server_name: str) -> list[Tool]:
        """Connect to a server and list its available tools."""

    async def call_tool(self, server_name: str, tool_name: str, args: dict) -> Any:
        """Call a tool on a named server. (Available for future use.)"""

    async def close(self):
        """Close all open client connections."""
```

Key behaviors:
- Config file is optional -- MCP features gracefully degrade when missing (like `gateway.yaml`)
- OAuth servers use `auth="oauth"` (FastMCP auto-opens browser, caches tokens)
- Connection caching -- clients reused within a session
- Async context manager support (`async with MCPManager(...) as mgr:`)

### Configuration: `mcp_servers.json`

Standard MCP config format:

```json
{
  "mcpServers": {
    "image-gen": {
      "url": "https://internal-mcp.example.com/mcp",
      "transport": "streamable-http",
      "auth": "oauth"
    },
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp-server"],
      "transport": "stdio"
    }
  }
}
```

- Gitignored by default (may contain internal URLs)
- `mcp_servers.example.json` checked in with placeholder entries

### CLI: `aippt mcp list`

New `mcp` subcommand group in `cli.py`:

```
$ aippt mcp list
MCP Servers:
  image-gen (https://internal-mcp.example.com/mcp) [streamable-http, oauth]
    Tools:
      - generate_image: Generate an image from a text prompt
      - edit_image: Edit an existing image with instructions

  playwright (npx @playwright/mcp-server) [stdio]
    Tools:
      - screenshot: Take a screenshot of a URL
      - navigate: Navigate to a URL
```

- Connects to each configured server, runs `list_tools()`, displays results
- Auth errors shown gracefully (e.g., "image-gen: authentication required")
- `--json` flag for machine-readable output

### Dependencies

- Add `fastmcp>=2.14.0` to `requirements.txt` (stable v2.x, not v3 beta)
- FastMCP transitively pulls in the `mcp` SDK
- Python >=3.10 already required by project

### Testing

- Unit tests mock `fastmcp.Client` -- no real server connections needed
- Test config loading (valid, missing, malformed)
- Test server listing and tool discovery
- Test CLI output formatting (text and JSON modes)
- Test graceful degradation when config missing
- Future: `e2e`-marked tests for real MCP server connections

## File Changes

| File | Change |
|------|--------|
| `aippt/mcp.py` | **New** -- MCPManager class |
| `aippt/cli.py` | Add `mcp` subcommand group with `list` command |
| `requirements.txt` | Add `fastmcp>=2.14.0` |
| `mcp_servers.example.json` | **New** -- example config with placeholder entries |
| `.gitignore` | Add `mcp_servers.json` |
| `tests/test_mcp.py` | **New** -- unit tests for MCPManager |
| `tests/test_cli_mcp.py` | **New** -- CLI integration tests for mcp subcommand |

## Future Work (Separate PRDs)

1. **Agentic enhance integration** -- LLM in enhance pipeline gets MCP tools as available functions, decides when to call them
2. **Text-to-image MCP server** -- specific config and integration for internal image generation service
3. **Playwright MCP server** -- web screenshot capture for slide images
4. **`aippt mcp call`** -- interactive tool invocation command
5. **`aippt mcp auth`** -- pre-authenticate OAuth servers before pipeline use
