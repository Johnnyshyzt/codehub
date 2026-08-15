"""Bridge MCP tools into CodeHub ToolRegistry."""

from __future__ import annotations

from typing import Any, Optional

from core.mcp.client import McpToolInfo, call_server_tool, list_server_tools, mcp_sdk_available
from core.mcp.config import McpConfig, McpServerConfig, mcp_tool_name
from core.tools.registry import ToolRegistry, ToolSpec


async def discover_mcp_tools(config: McpConfig) -> list[tuple[McpServerConfig, McpToolInfo]]:
    discovered: list[tuple[McpServerConfig, McpToolInfo]] = []
    for server in config.enabled_servers:
        tools = await list_server_tools(server)
        for tool in tools:
            discovered.append((server, tool))
    return discovered


def register_mcp_tools(
    registry: ToolRegistry,
    discovered: list[tuple[McpServerConfig, McpToolInfo]],
) -> list[str]:
    """
    Register discovered MCP tools onto the registry.

    Returns registered OpenAI tool names.
    """
    registered: list[str] = []
    for server, tool in discovered:
        openai_name = mcp_tool_name(server.name, tool.name)
        if registry.has_tool(openai_name):
            continue

        # Bind server/tool into closure for the handler.
        server_cfg = server
        remote_name = tool.name

        async def _handler(
            __server: McpServerConfig = server_cfg,
            __tool: str = remote_name,
            **kwargs: Any,
        ) -> str:
            return await call_server_tool(__server, __tool, arguments=kwargs)

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
) -> list[str]:
    """Discover + register MCP tools. No-op if none configured or SDK missing."""
    if config is None or not config.enabled_servers:
        return []
    if not mcp_sdk_available():
        return []
    discovered = await discover_mcp_tools(config)
    return register_mcp_tools(registry, discovered)
