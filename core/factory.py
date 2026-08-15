"""Factory helpers to assemble a ready-to-run agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.agent.runtime import AgentRuntime, CancelCheck, EventCallback
from core.config import build_providers, load_env, missing_key_help
from core.context.workspace import ContextBundle, context_from_payload
from core.mcp import McpAttachResult, attach_mcp_tools, load_mcp_config
from core.router.router import SmartRouter
from core.tools.filesystem import WorkspaceSandbox
from core.tools.registry import ToolRegistry


def create_agent(
    workspace: str | Path | None = None,
    *,
    max_steps: int = 12,
    with_tools: bool = True,
    on_event: Optional[EventCallback] = None,
    cancel_check: Optional[CancelCheck] = None,
    record_usage: bool = True,
    load_dotenv: bool = True,
) -> AgentRuntime:
    if load_dotenv:
        load_env()

    providers = build_providers()
    if not providers:
        raise RuntimeError(missing_key_help())

    router = SmartRouter(providers)
    tools = None
    if with_tools:
        root = Path(workspace or Path.cwd()).resolve()
        tools = ToolRegistry(WorkspaceSandbox(root))

    return AgentRuntime(
        router=router,
        tools=tools,
        max_steps=max_steps,
        on_event=on_event,
        cancel_check=cancel_check,
        record_usage=record_usage,
    )


async def attach_configured_mcp(
    agent: AgentRuntime,
    workspace: str | Path | None = None,
) -> McpAttachResult:
    """Attach selective MCP tools from config (no-op if none / SDK missing)."""
    if not agent.tools:
        return McpAttachResult()
    config = load_mcp_config(workspace)
    attached = await attach_mcp_tools(agent.tools, config)
    # Keep pool on the agent so callers can close after the run.
    agent.mcp_pool = attached.pool  # type: ignore[attr-defined]
    return attached


async def close_configured_mcp(agent: AgentRuntime) -> None:
    """Close warm MCP sessions attached to the agent, if any."""
    pool = getattr(agent, "mcp_pool", None)
    if pool is not None:
        await pool.aclose()
        agent.mcp_pool = None  # type: ignore[attr-defined]


def build_run_context(
    workspace: str | Path,
    context_payload: Optional[Dict[str, Any]] = None,
) -> ContextBundle:
    """Build a ContextBundle for an agent run."""
    return context_from_payload(workspace, context_payload)
