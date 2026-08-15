"""MCP server config loading (selective whitelist)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class McpServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    # Empty / ["*"] = all tools; otherwise only listed tool names.
    allow_tools: list[str] = field(default_factory=lambda: ["*"])

    def allows(self, tool_name: str) -> bool:
        if not self.allow_tools or "*" in self.allow_tools:
            return True
        return tool_name in self.allow_tools


@dataclass
class McpConfig:
    servers: list[McpServerConfig] = field(default_factory=list)

    @property
    def enabled_servers(self) -> list[McpServerConfig]:
        return [s for s in self.servers if s.enabled and s.command]


def default_config_paths(workspace: str | Path | None = None) -> list[Path]:
    paths: list[Path] = []
    env_path = os.getenv("CODEHUB_MCP_CONFIG", "").strip()
    if env_path:
        paths.append(Path(env_path).expanduser())
    if workspace:
        root = Path(workspace).resolve()
        paths.append(root / ".codehub" / "mcp.json")
        paths.append(root / "mcp.json")
    paths.append(Path.home() / ".codehub" / "mcp.json")
    return paths


def load_mcp_config(workspace: str | Path | None = None) -> McpConfig:
    """Load first existing MCP config file from search paths."""
    for path in default_config_paths(workspace):
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        return parse_mcp_config(raw)
    return McpConfig()


def parse_mcp_config(raw: Any) -> McpConfig:
    if not isinstance(raw, dict):
        return McpConfig()
    servers_raw = raw.get("servers") or {}
    servers: list[McpServerConfig] = []
    if isinstance(servers_raw, dict):
        for name, spec in servers_raw.items():
            cfg = _parse_server(str(name), spec)
            if cfg:
                servers.append(cfg)
    elif isinstance(servers_raw, list):
        for item in servers_raw:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            cfg = _parse_server(str(item["name"]), item)
            if cfg:
                servers.append(cfg)
    return McpConfig(servers=servers)


def _parse_server(name: str, spec: Any) -> Optional[McpServerConfig]:
    if not isinstance(spec, dict):
        return None
    command = str(spec.get("command") or "").strip()
    if not command:
        return None
    args = spec.get("args") or []
    if not isinstance(args, list):
        args = []
    env = spec.get("env") or {}
    if not isinstance(env, dict):
        env = {}
    allow = spec.get("allow_tools")
    if allow is None:
        allow_tools = ["*"]
    elif isinstance(allow, list):
        allow_tools = [str(x) for x in allow]
    else:
        allow_tools = ["*"]
    return McpServerConfig(
        name=name,
        command=command,
        args=[str(a) for a in args],
        env={str(k): str(v) for k, v in env.items()},
        enabled=bool(spec.get("enabled", True)),
        allow_tools=allow_tools,
    )


def mcp_tool_name(server: str, tool: str) -> str:
    """Stable OpenAI-tool name for an MCP tool."""
    safe_server = "".join(c if c.isalnum() or c in "_-" else "_" for c in server)
    safe_tool = "".join(c if c.isalnum() or c in "_-" else "_" for c in tool)
    return f"mcp__{safe_server}__{safe_tool}"
