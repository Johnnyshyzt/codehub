"""MCP client wrapper (optional `mcp` package) with warm session reuse."""

from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Optional

from core.mcp.config import McpServerConfig


@dataclass
class McpToolInfo:
    server: str
    name: str
    description: str
    input_schema: dict[str, Any]


def mcp_sdk_available() -> bool:
    try:
        import mcp  # noqa: F401
        from mcp.client.stdio import stdio_client  # noqa: F401

        return True
    except Exception:
        return False


def _result_to_text(result: Any) -> str:
    parts: list[str] = []
    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(str(text))
            continue
        # Fallback serialize
        try:
            parts.append(json.dumps(block, default=str))
        except Exception:
            parts.append(str(block))
    structured = getattr(result, "structuredContent", None)
    if structured is not None and not parts:
        try:
            return json.dumps(structured, ensure_ascii=False)
        except Exception:
            return str(structured)
    if getattr(result, "isError", False) and not parts:
        return "ERROR: MCP tool returned an error"
    return "\n".join(parts) if parts else "(empty)"


def _tool_infos_from_listed(server: McpServerConfig, listed: Any) -> list[McpToolInfo]:
    tools: list[McpToolInfo] = []
    for tool in listed.tools:
        name = str(tool.name)
        if not server.allows(name):
            continue
        schema = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
        if hasattr(schema, "model_dump"):
            schema = schema.model_dump()
        elif not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}}
        tools.append(
            McpToolInfo(
                server=server.name,
                name=name,
                description=str(getattr(tool, "description", "") or name),
                input_schema=schema,
            )
        )
    return tools


class _WarmSession:
    """One long-lived stdio MCP connection."""

    def __init__(self, server: McpServerConfig) -> None:
        self.server = server
        self._stack: AsyncExitStack | None = None
        self.session: Any = None

    async def start(self) -> Any:
        if self.session is not None:
            return self.session
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=self.server.command,
            args=list(self.server.args),
            env=self.server.env or None,
        )
        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except Exception:
            await stack.aclose()
            raise
        self._stack = stack
        self.session = session
        return session

    async def close(self) -> None:
        stack = self._stack
        self._stack = None
        self.session = None
        if stack is not None:
            try:
                await stack.aclose()
            except Exception:  # noqa: BLE001
                pass


class McpSessionPool:
    """
    Keep MCP stdio sessions warm across tool discovery and calls.

    One process per configured server name; closed via ``aclose()``.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _WarmSession] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def _ensure(self, server: McpServerConfig) -> Any:
        if self._closed:
            raise RuntimeError("McpSessionPool is closed")
        if not mcp_sdk_available():
            raise RuntimeError(
                "MCP SDK not installed. Install with: pip install 'codehub[mcp]' "
                "or pip install mcp"
            )
        async with self._lock:
            warm = self._sessions.get(server.name)
            if warm is not None and warm.session is not None:
                return warm.session
            warm = _WarmSession(server)
            await warm.start()
            self._sessions[server.name] = warm
            return warm.session

    async def _drop(self, server_name: str) -> None:
        async with self._lock:
            warm = self._sessions.pop(server_name, None)
        if warm is not None:
            await warm.close()

    async def list_tools(self, server: McpServerConfig) -> list[McpToolInfo]:
        session = await self._ensure(server)
        listed = await session.list_tools()
        return _tool_infos_from_listed(server, listed)

    async def call_tool(
        self,
        server: McpServerConfig,
        tool_name: str,
        arguments: Optional[dict[str, Any]] = None,
        *,
        retry: bool = True,
    ) -> str:
        if not server.allows(tool_name):
            return (
                f"ERROR: tool {tool_name!r} is not allow-listed "
                f"for MCP server {server.name}"
            )
        if not mcp_sdk_available():
            return (
                "ERROR: MCP SDK not installed. "
                "Install with: pip install 'codehub[mcp]' or pip install mcp"
            )
        try:
            session = await self._ensure(server)
            result = await session.call_tool(tool_name, arguments=arguments or {})
            text = _result_to_text(result)
            if getattr(result, "isError", False):
                return f"ERROR: {text}"
            return text
        except Exception as exc:  # noqa: BLE001
            await self._drop(server.name)
            if retry:
                try:
                    session = await self._ensure(server)
                    result = await session.call_tool(tool_name, arguments=arguments or {})
                    text = _result_to_text(result)
                    if getattr(result, "isError", False):
                        return f"ERROR: {text}"
                    return text
                except Exception as exc2:  # noqa: BLE001
                    await self._drop(server.name)
                    return f"ERROR: MCP call failed ({server.name}/{tool_name}): {exc2}"
            return f"ERROR: MCP call failed ({server.name}/{tool_name}): {exc}"

    async def aclose(self) -> None:
        self._closed = True
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for warm in sessions:
            await warm.close()

    @property
    def open_server_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.session is not None)


async def list_server_tools(
    server: McpServerConfig,
    *,
    pool: Optional[McpSessionPool] = None,
) -> list[McpToolInfo]:
    """List allow-listed tools. Uses ``pool`` when provided; otherwise one-shot."""
    if pool is not None:
        return await pool.list_tools(server)
    if not mcp_sdk_available():
        raise RuntimeError(
            "MCP SDK not installed. Install with: pip install 'codehub[mcp]' "
            "or pip install mcp"
        )
    ephemeral = McpSessionPool()
    try:
        return await ephemeral.list_tools(server)
    finally:
        await ephemeral.aclose()


async def call_server_tool(
    server: McpServerConfig,
    tool_name: str,
    arguments: Optional[dict[str, Any]] = None,
    *,
    pool: Optional[McpSessionPool] = None,
) -> str:
    """Call an MCP tool. Uses ``pool`` when provided; otherwise one-shot."""
    if pool is not None:
        return await pool.call_tool(server, tool_name, arguments)
    ephemeral = McpSessionPool()
    try:
        return await ephemeral.call_tool(server, tool_name, arguments, retry=False)
    finally:
        await ephemeral.aclose()
