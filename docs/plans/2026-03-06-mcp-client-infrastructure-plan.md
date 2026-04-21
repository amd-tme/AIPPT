# MCP Client Infrastructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an MCP client layer to aippt using FastMCP, with config loading, server/tool discovery, and a `mcp list` CLI command.

**Architecture:** New `aippt/mcp.py` module with `MCPManager` class wrapping `fastmcp.Client`. Reads standard `mcp_servers.json` config. CLI bridges sync argparse to async MCP calls via `asyncio.run()`. Config file is optional -- missing config degrades gracefully.

**Tech Stack:** fastmcp>=2.14.0 (Python MCP client), asyncio (sync-to-async bridge), standard JSON config format

---

### Task 1: Add dependency, gitignore, and example config

**Files:**
- Modify: `requirements.txt`
- Modify: `.gitignore`
- Create: `mcp_servers.example.json`

**Step 1: Add fastmcp to requirements.txt**

Add after the `httpx` line in the "Core dependencies" section:

```
fastmcp>=2.14.0     # MCP client for external tool servers
```

**Step 2: Add mcp_servers.json to .gitignore**

Add after the `gateway.yaml` line in the "Environment and secrets" section:

```
mcp_servers.json
```

**Step 3: Create example config**

Create `mcp_servers.example.json`:

```json
{
  "mcpServers": {
    "example-http": {
      "url": "https://mcp.example.com/mcp",
      "auth": "oauth"
    },
    "example-stdio": {
      "command": "npx",
      "args": ["@example/mcp-server"],
      "env": {}
    }
  }
}
```

**Step 4: Install the dependency**

Run: `venv/bin/pip install fastmcp>=2.14.0`

**Step 5: Commit**

```bash
git add requirements.txt .gitignore mcp_servers.example.json
git commit -m "chore: add fastmcp dependency and MCP config scaffolding"
```

---

### Task 2: MCPManager config loading (TDD)

**Files:**
- Create: `tests/test_mcp.py`
- Create: `aippt/mcp.py`

**Step 1: Write failing tests for config loading**

Create `tests/test_mcp.py`:

```python
"""Tests for the MCP client infrastructure."""

import json
from unittest.mock import MagicMock

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
```

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_mcp.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'aippt.mcp'`

**Step 3: Implement MCPManager config loading**

Create `aippt/mcp.py`:

```python
"""MCP client infrastructure for connecting to external tool servers."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastmcp import Client

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
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_mcp.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add aippt/mcp.py tests/test_mcp.py
git commit -m "feat: add MCPManager with config loading from mcp_servers.json"
```

---

### Task 3: MCPManager tool listing and client building (TDD)

**Files:**
- Modify: `tests/test_mcp.py`
- Modify: `aippt/mcp.py`

**Step 1: Write failing tests for client building and tool listing**

Append to `tests/test_mcp.py`:

```python
import asyncio
from unittest.mock import patch, AsyncMock


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
            mgr = MCPManager(str(config_path))
            mgr._build_client(mgr.servers["srv"])
            MockClient.assert_called_once_with("npx @pw/server")

    def test_build_client_stdio_no_args(self, tmp_path):
        config = {"mcpServers": {"srv": {"command": "my-server"}}}
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(json.dumps(config))

        from aippt.mcp import MCPManager

        with patch("aippt.mcp.Client") as MockClient:
            mgr = MCPManager(str(config_path))
            mgr._build_client(mgr.servers["srv"])
            MockClient.assert_called_once_with("my-server")


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
```

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_mcp.py::TestMCPManagerClientBuilding -v`
Expected: FAIL with `AttributeError: 'MCPManager' object has no attribute '_build_client'`

**Step 3: Implement _build_client, list_tools, and call_tool**

Add to `aippt/mcp.py` (inside the `MCPManager` class, after the `servers` property):

```python
    def _build_client(self, cfg: ServerConfig) -> Client:
        """Create a FastMCP Client for the given server config."""
        kwargs = {}
        if cfg.auth:
            kwargs["auth"] = cfg.auth
        if cfg.url:
            return Client(cfg.url, **kwargs)
        cmd = cfg.command
        if cfg.args:
            cmd = f"{cmd} {' '.join(cfg.args)}"
        return Client(cmd, **kwargs)

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
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_mcp.py -v`
Expected: All 18 tests PASS

**Step 5: Commit**

```bash
git add aippt/mcp.py tests/test_mcp.py
git commit -m "feat: add MCPManager tool listing and client building"
```

---

### Task 4: CLI `mcp list` command (TDD)

**Files:**
- Create: `tests/test_cli_mcp.py`
- Modify: `aippt/cli.py`

**Step 1: Write failing CLI tests**

Create `tests/test_cli_mcp.py`:

```python
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

        mock_client_1 = AsyncMock()
        mock_client_1.list_tools.return_value = [tool1]
        mock_client_2 = AsyncMock()
        mock_client_2.list_tools.return_value = [tool2]

        clients = iter([mock_client_1, mock_client_2])

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
```

**Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_cli_mcp.py -v`
Expected: FAIL with `ImportError: cannot import name 'cmd_mcp' from 'aippt.cli'`

**Step 3: Implement cmd_mcp and add parser entries**

Add to `aippt/cli.py` -- the `cmd_mcp` function (add before `build_parser`):

```python
def cmd_mcp(args):
    """Manage MCP server connections."""
    import asyncio

    action = getattr(args, "mcp_action", None)

    # Default action is list
    if action == "list" or action is None:
        return asyncio.run(_cmd_mcp_list(args))

    print(f"Unknown mcp action: {action}")
    return 1


async def _cmd_mcp_list(args):
    """List configured MCP servers and their available tools."""
    import json as json_mod

    from aippt.mcp import MCPManager

    config_path = getattr(args, "config", "mcp_servers.json")
    mgr = MCPManager(config_path)

    if not mgr.servers:
        print("No MCP servers configured.")
        if config_path == "mcp_servers.json":
            print("Create mcp_servers.json or copy from mcp_servers.example.json")
        return 0

    use_json = getattr(args, "json", False)
    results = {}

    for name, cfg in mgr.servers.items():
        entry = {
            "url": cfg.display_url,
            "transport": cfg.transport_type,
        }
        if cfg.auth:
            entry["auth"] = cfg.auth

        try:
            tools = await mgr.list_tools(name)
            entry["tools"] = [
                {"name": t.name, "description": t.description} for t in tools
            ]
        except Exception as e:
            entry["error"] = str(e)

        results[name] = entry

    if use_json:
        print(json_mod.dumps(results, indent=2))
        return 0

    # Human-readable output
    print("MCP Servers:\n")
    for name, info in results.items():
        transport = info["transport"]
        auth_str = f", {info['auth']}" if info.get("auth") else ""
        print(f"  {name} ({info['url']}) [{transport}{auth_str}]")

        if "error" in info:
            print(f"    Error: {info['error']}")
        elif "tools" in info:
            if info["tools"]:
                print("    Tools:")
                for tool in info["tools"]:
                    print(f"      - {tool['name']}: {tool['description']}")
            else:
                print("    No tools available")
        print()

    return 0
```

Add parser entries in `build_parser()` -- add after the `migrate-paths` parser (before `return parser`):

```python
    # mcp (MCP server management)
    p_mcp = sub.add_parser("mcp", help="Manage MCP server connections")
    p_mcp.add_argument("--config", default="mcp_servers.json", help="MCP servers config file")
    mcp_sub = p_mcp.add_subparsers(dest="mcp_action")

    p_mcp_list = mcp_sub.add_parser("list", help="List configured MCP servers and their tools")
    p_mcp_list.add_argument("--config", default="mcp_servers.json", help="MCP servers config file")
    p_mcp_list.add_argument("--json", action="store_true", help="Output as JSON")
```

Add `"mcp": cmd_mcp` to the `commands` dict in `main()`:

```python
    commands = {
        ...
        "migrate-paths": cmd_migrate_paths,
        "mcp": cmd_mcp,
    }
```

**Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_cli_mcp.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add aippt/cli.py tests/test_cli_mcp.py
git commit -m "feat: add 'mcp list' CLI command for server/tool discovery"
```

---

### Task 5: Full test suite verification and CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Run full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS (existing + new MCP tests), no regressions

**Step 2: Test the CLI manually**

Run without config (graceful degradation):
```bash
venv/bin/python aippt.py mcp list
```
Expected: "No MCP servers configured."

Run with example config (will fail to connect but tests the flow):
```bash
cp mcp_servers.example.json mcp_servers.json
venv/bin/python aippt.py mcp list
```
Expected: Shows servers with connection errors (expected since example URLs aren't real).

Clean up:
```bash
rm mcp_servers.json
```

**Step 3: Update CLAUDE.md**

Add MCP CLI commands to the "CLI Commands" section:

```markdown
# MCP server management
$VENV_PYTHON aippt.py mcp list
$VENV_PYTHON aippt.py mcp list --json
$VENV_PYTHON aippt.py mcp list --config path/to/mcp_servers.json
```

Add to the Architecture file list:

```
  mcp.py          # MCP client infrastructure (FastMCP wrapper)
```

**Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add MCP commands to CLAUDE.md"
```

---

## Summary

| Task | Tests | Files |
|------|-------|-------|
| 1. Dependency + config scaffolding | -- | requirements.txt, .gitignore, mcp_servers.example.json |
| 2. MCPManager config loading | 7 | aippt/mcp.py, tests/test_mcp.py |
| 3. MCPManager tool listing | 11 | aippt/mcp.py, tests/test_mcp.py |
| 4. CLI `mcp list` command | 5 | aippt/cli.py, tests/test_cli_mcp.py |
| 5. Verification + docs | -- | CLAUDE.md |

Total: ~23 new tests, 2 new files, 3 modified files
