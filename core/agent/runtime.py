"""
Agent Runtime with multi-step tool calling loop.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Optional, Union

from core.router.router import RouteDecision, SmartRouter
from core.tools.registry import ToolRegistry
from providers.base import ChatCompletionRequest, ChatMessage

try:
    from core.quota.store import UsageStore, get_usage_store
except ImportError:  # pragma: no cover
    UsageStore = None  # type: ignore[misc, assignment]
    get_usage_store = None  # type: ignore[misc, assignment]

EventCallback = Callable[[str, dict[str, Any]], Union[Awaitable[None], None]]
CancelCheck = Callable[[], bool]


class AgentCancelled(Exception):
    """Raised when the user cancels an in-flight agent run."""


DEFAULT_SYSTEM_PROMPT = """You are CodeHub, an open-source AI coding agent.
You help developers complete real coding tasks by reading and editing files
and running commands inside their workspace.

Rules:
- Prefer using tools over guessing file contents.
- Start with workspace context, then grep/search_files/read_file before editing.
- Use git_status / git_diff / git_log to understand the repo state; do not invent git history.
- Only use git_commit when the user clearly asks to commit; pass confirm=true and a clear message.
- MCP tools (names starting with mcp__) are optional external tools; use them only when relevant.
- Keep changes minimal and correct.
- After editing code, run relevant tests or checks when practical.
- When finished, give a short summary of what you changed.
- Paths are relative to the workspace root.
"""


@dataclass
class AgentResult:
    content: str
    provider: str
    model: str
    steps: int
    tool_calls: int = 0
    usage_total_tokens: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    file_changes: list[dict[str, Any]] = field(default_factory=list)


class AgentRuntime:
    def __init__(
        self,
        router: SmartRouter,
        tools: Optional[ToolRegistry] = None,
        *,
        max_steps: int = 12,
        on_event: Optional[EventCallback] = None,
        cancel_check: Optional[CancelCheck] = None,
        usage_store: Optional[Any] = None,
        record_usage: bool = True,
    ):
        self.router = router
        self.tools = tools
        self.max_steps = max_steps
        self.on_event = on_event
        self.cancel_check = cancel_check
        self.history: list[ChatMessage] = []
        self.record_usage = record_usage
        if usage_store is not None:
            self.usage_store = usage_store
        elif record_usage and get_usage_store is not None:
            self.usage_store = get_usage_store()
        else:
            self.usage_store = None

    def add_message(self, role: str, content: Optional[str], **kwargs: Any) -> None:
        self.history.append(ChatMessage(role=role, content=content, **kwargs))

    def _raise_if_cancelled(self) -> None:
        if self.cancel_check and self.cancel_check():
            raise AgentCancelled("Cancelled by user")

    def _record_usage(self, provider: str, model: str, usage: Optional[dict[str, Any]]) -> None:
        if not self.record_usage or self.usage_store is None or not usage:
            return
        try:
            self.usage_store.record(
                provider=provider,
                model=model,
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
            )
        except Exception:  # noqa: BLE001 — usage must never break the agent
            return

    async def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.on_event:
            result = self.on_event(event_type, payload)
            if hasattr(result, "__await__"):
                await result  # type: ignore[misc]

    def _make_token_emitter(self, step: int) -> Callable[[str], Any]:
        async def _on_token(text: str) -> None:
            self._raise_if_cancelled()
            if text:
                await self._emit("token", {"step": step, "text": text})

        return _on_token

    async def run(
        self,
        user_input: str,
        task_type: str = "coding",
        system_prompt: Optional[str] = None,
        context_text: Optional[str] = None,
    ) -> AgentResult:
        """
        Multi-step agent loop:
        model -> optional tool calls -> tool results -> model ... until final answer.
        """
        self.history = [
            ChatMessage(role="system", content=system_prompt or DEFAULT_SYSTEM_PROMPT)
        ]
        if context_text:
            self.add_message(
                "user",
                (
                    "Here is the current workspace context. "
                    "Use it to orient yourself, then use tools for details.\n\n"
                    f"{context_text}"
                ),
            )
        self.add_message("user", user_input)
        if self.tools:
            self.tools.clear_changes()

        events: list[dict[str, Any]] = []
        tool_call_count = 0
        usage_total = 0
        steps_used = 0
        last_decision: RouteDecision | None = None
        final_content = ""

        tools_payload = self.tools.openai_tools() if self.tools else None
        require_tools = bool(tools_payload)

        for step in range(1, self.max_steps + 1):
            self._raise_if_cancelled()
            steps_used = step
            request = ChatCompletionRequest(
                messages=list(self.history),
                temperature=0.2,
                tools=tools_payload,
                tool_choice="auto" if tools_payload else None,
            )

            decision, response = await self.router.chat_with_fallback(
                request,
                task_type=task_type,
                require_tools=require_tools,
                stream=True,
                on_token=self._make_token_emitter(step),
            )
            self._raise_if_cancelled()
            last_decision = decision

            if response.usage:
                usage_total += int(response.usage.get("total_tokens") or 0)
                self._record_usage(
                    decision.provider.name,
                    decision.model.id,
                    response.usage,
                )

            await self._emit(
                "model_response",
                {
                    "step": step,
                    "provider": decision.provider.name,
                    "model": decision.model.id,
                    "has_tool_calls": bool(response.tool_calls),
                    "usage": response.usage,
                },
            )
            events.append(
                {
                    "type": "model_response",
                    "step": step,
                    "provider": decision.provider.name,
                    "model": decision.model.id,
                }
            )

            if response.tool_calls and self.tools:
                self.add_message(
                    "assistant",
                    response.content,
                    tool_calls=response.tool_calls,
                )
                self._raise_if_cancelled()
                results = await self.tools.execute_tool_calls(response.tool_calls)
                tool_call_count += len(results)
                for item in results:
                    self._raise_if_cancelled()
                    self.add_message(
                        "tool",
                        item["content"],
                        tool_call_id=item["tool_call_id"],
                        name=item["name"],
                    )
                    await self._emit(
                        "tool_result",
                        {
                            "step": step,
                            "tool": item["name"],
                            "preview": item["content"][:300],
                        },
                    )
                    events.append(
                        {
                            "type": "tool_result",
                            "step": step,
                            "tool": item["name"],
                        }
                    )
                continue

            final_content = response.content or ""
            self.add_message("assistant", final_content)
            break
        else:
            final_content = (
                "Reached max agent steps without a final answer. "
                "Partial work may already be applied via tools."
            )

        if last_decision is None:
            raise RuntimeError("Agent did not receive any model response")

        file_changes = self.tools.export_changes() if self.tools else []
        return AgentResult(
            content=final_content,
            provider=last_decision.provider.name,
            model=last_decision.model.id,
            steps=steps_used,
            tool_calls=tool_call_count,
            usage_total_tokens=usage_total,
            events=events,
            file_changes=file_changes,
        )

    def reset(self) -> None:
        self.history.clear()
