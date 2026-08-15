"""Bridge MCP tools into CodeHub ToolRegistry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.mcp.client import (
    McpSessionPool,
    McpToolInfo,
    call_server_tool,
    list_server_tools,
    mcp_sdk_available,
)
from core.mcp.config import McpConfig, McpServerConfig, mcp_tool_name
from core.tools.registry import ToolRegistry, ToolSpec


@dataclass
class McpAttachResult:
    """Registered MCP tool names plus optional warm session pool."""

    tool_names: list[str] = field(default_factory=list)
    pool: Optional[McpSessionPool] = None

    async def aclose(self) -> None:
        if self.pool is not None:
            await self.pool.aclose()
            self.pool = None


async def discover_mcp_tools(
    config: McpConfig,
    *,
    pool: Optional[McpSessionPool] = None,
) -> list[tuple[McpServerConfig, McpToolInfo]]:
    discovered: list[tuple[McpServerConfig, McpToolInfo]] = []
    for server in config.enabled_servers:
        tools = await list_server_tools(server, pool=pool)
        for tool in tools:
            discovered.append((server, tool))
    return discovered


def register_mcp_tools(
    registry: ToolRegistry,
    discovered: list[tuple[McpServerConfig, McpToolInfo]],
    *,
    pool: Optional[McpSessionPool] = None,
) -> list[str]:
    """
    Register discovered MCP tools onto the registry.

    When ``pool`` is provided, handlers reuse warm stdio sessions.
    Returns registered OpenAI tool names.
    """
    registered: list[str] = []
    for server, tool in discovered:
        openai_name = mcp_tool_name(server.name, tool.name)
        if registry.has_tool(openai_name):
            continue

        # Bind server/tool/pool into closure for the handler.
        server_cfg = server
        remote_name = tool.name
        session_pool = pool

        async def _handler(
            __server: McpServerConfig = server_cfg,
            __tool: str = remote_name,
            __pool: Optional[McpSessionPool] = session_pool,
            **kwargs: Any,
        ) -> str:
            return await call_server_tool(
                __server, __tool, arguments=kwargs, pool=__pool
            )

        schema = tool.input_schema if isinstance(tool.input_schema, dict) else {
            "type": "object",
            "properties": {},
        }
        # Ensure JSON-schema object shape for OpenAI tools.
        if schema.get("type") != "object":
            schema = {
                "type": "object",
                "properties": {"value": schema},
            }

        registry.register(
            ToolSpec(
                name=openai_name,
                description=f"[MCP:{server.name}] {tool.description}",
                parameters=schema,
                handler=_handler,
            )
        )
        registered.append(openai_name)
    return registered


async def attach_mcp_tools(
    registry: ToolRegistry,
    config: Optional[McpConfig] = None,
) -> McpAttachResult:
    """Discover + register MCP tools with a warm session pool when possible."""
    if config is None or not config.enabled_servers:
        return McpAttachResult()
    if not mcp_sdk_available():
        return McpAttachResult()

    pool = McpSessionPool()
    try:
        discovered = await discover_mcp_tools(config, pool=pool)
        names = register_mcp_tools(registry, discovered, pool=pool)
        if not names:
            await pool.aclose()
            return McpAttachResult(tool_names=[], pool=None)
        return McpAttachResult(tool_names=names, pool=pool)
    except Exception:
        await pool.aclose()
        raise
