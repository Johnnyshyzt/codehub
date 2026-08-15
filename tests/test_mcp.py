"""MCP config / bridge unit tests (no MCP SDK required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.mcp.bridge import register_mcp_tools
from core.mcp.client import McpToolInfo
from core.mcp.config import (
    McpServerConfig,
    load_mcp_config,
    mcp_tool_name,
    parse_mcp_config,
)
from core.tools.filesystem import WorkspaceSandbox
from core.tools.registry import ToolRegistry


def test_mcp_tool_name() -> None:
    assert mcp_tool_name("demo", "echo") == "mcp__demo__echo"
    assert mcp_tool_name("my srv", "do-it!") == "mcp__my_srv__do-it_"


def test_parse_mcp_config_whitelist() -> None:
    cfg = parse_mcp_config(
        {
            "servers": {
                "echo": {
                    "command": "python",
                    "args": ["-m", "examples.mcp_echo_server"],
                    "allow_tools": ["echo"],
                    "enabled": True,
                },
                "off": {
                    "command": "npx",
                    "args": ["x"],
                    "enabled": False,
                },
            }
        }
    )
    assert len(cfg.enabled_servers) == 1
    server = cfg.enabled_servers[0]
    assert server.name == "echo"
    assert server.allows("echo")
    assert not server.allows("other")


def test_load_mcp_config_from_workspace(tmp_path: Path) -> None:
    conf_dir = tmp_path / ".codehub"
    conf_dir.mkdir()
    (conf_dir / "mcp.json").write_text(
        '{"servers":{"s":{"command":"echo","args":["hi"],"enabled":true}}}',
        encoding="utf-8",
    )
    cfg = load_mcp_config(tmp_path)
    assert len(cfg.enabled_servers) == 1
    assert cfg.enabled_servers[0].command == "echo"


@pytest.mark.asyncio
async def test_register_mcp_tools(tmp_path: Path) -> None:
    registry = ToolRegistry(WorkspaceSandbox(tmp_path))
    server = McpServerConfig(name="demo", command="python", args=[], allow_tools=["*"])
    tool = McpToolInfo(
        server="demo",
        name="echo",
        description="Echo text",
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    )
    names = register_mcp_tools(registry, [(server, tool)])
    assert names == ["mcp__demo__echo"]
    assert registry.has_tool("mcp__demo__echo")
    schemas = registry.openai_tools()
    assert any(s["function"]["name"] == "mcp__demo__echo" for s in schemas)


@pytest.mark.asyncio
async def test_mcp_session_pool_reuses_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.mcp.client import McpSessionPool

    server = McpServerConfig(name="demo", command="python", args=[], allow_tools=["*"])
    starts = {"n": 0}
    calls = {"n": 0}

    class FakeSession:
        async def list_tools(self):
            class T:
                name = "echo"
                description = "Echo"
                inputSchema = {"type": "object", "properties": {}}

            class Listed:
                tools = [T()]

            return Listed()

        async def call_tool(self, name, arguments=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("broken pipe")

            class Block:
                text = f"ok:{arguments}"

            class Result:
                content = [Block()]
                isError = False
                structuredContent = None

            return Result()

    class FakeWarm:
        def __init__(self, srv):
            self.server = srv
            self.session = None
            self._stack = object()

        async def start(self):
            starts["n"] += 1
            self.session = FakeSession()
            return self.session

        async def close(self):
            self.session = None

    monkeypatch.setattr("core.mcp.client.mcp_sdk_available", lambda: True)
    monkeypatch.setattr("core.mcp.client._WarmSession", FakeWarm)

    pool = McpSessionPool()
    tools = await pool.list_tools(server)
    assert len(tools) == 1
    assert starts["n"] == 1

    # Second list should reuse the warm session.
    tools2 = await pool.list_tools(server)
    assert len(tools2) == 1
    assert starts["n"] == 1

    out = await pool.call_tool(server, "echo", {"message": "hi"})
    assert out == "ok:{'message': 'hi'}"
    # First call failed → drop + retry start once more.
    assert starts["n"] == 2
    assert calls["n"] == 2

    await pool.aclose()
    assert pool.open_server_count == 0
