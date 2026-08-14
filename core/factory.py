"""Factory helpers to assemble a ready-to-run agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.agent.runtime import AgentRuntime, EventCallback
from core.config import build_providers, load_env, missing_key_help
from core.context.workspace import ContextBundle, context_from_payload
from core.router.router import SmartRouter
from core.tools.filesystem import WorkspaceSandbox
from core.tools.registry import ToolRegistry


def create_agent(
    workspace: str | Path | None = None,
    *,
    max_steps: int = 12,
    with_tools: bool = True,
    on_event: Optional[EventCallback] = None,
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
    )


def build_run_context(
    workspace: str | Path,
    context_payload: Optional[Dict[str, Any]] = None,
) -> ContextBundle:
    """Build a ContextBundle for an agent run."""
    return context_from_payload(workspace, context_payload)
