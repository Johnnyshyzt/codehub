"""MCP client wrapper (optional `mcp` package)."""

from __future__ import annotations

import json
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


async def list_server_tools(server: McpServerConfig) -> list[McpToolInfo]:
    if not mcp_sdk_available():
        raise RuntimeError(
            "MCP SDK not installed. Install with: pip install 'codehub[mcp]' "
            "or pip install mcp"
        )
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=server.command,
        args=list(server.args),
        env=server.env or None,
    )
    tools: list[McpToolInfo] = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
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


async def call_server_tool(
    server: McpServerConfig,
    tool_name: str,
    arguments: Optional[dict[str, Any]] = None,
) -> str:
    if not server.allows(tool_name):
        return f"ERROR: tool {tool_name!r} is not allow-listed for MCP server {server.name}"
    if not mcp_sdk_available():
        return (
            "ERROR: MCP SDK not installed. "
            "Install with: pip install 'codehub[mcp]' or pip install mcp"
        )
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=server.command,
        args=list(server.args),
        env=server.env or None,
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments or {})
                text = _result_to_text(result)
                if getattr(result, "isError", False):
                    return f"ERROR: {text}"
                return text
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: MCP call failed ({server.name}/{tool_name}): {exc}"
