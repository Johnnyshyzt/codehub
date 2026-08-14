"""Agent loop tests with scripted mock provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.agent.runtime import AgentRuntime
from core.router.router import SmartRouter
from core.tools.filesystem import WorkspaceSandbox
from core.tools.registry import ToolRegistry
from providers.base import ChatCompletionResponse
from providers.mock import MockProvider


@pytest.mark.asyncio
async def test_agent_tool_loop(tmp_path: Path) -> None:
    # 1) model asks to write_file  2) model returns final answer
    scripted = [
        ChatCompletionResponse(
            content=None,
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": '{"path": "note.txt", "content": "hello"}',
                    },
                }
            ],
            finish_reason="tool_calls",
        ),
        ChatCompletionResponse(
            content="Created note.txt",
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        ),
    ]
    provider = MockProvider(scripted_responses=scripted)
    router = SmartRouter([provider])
    tools = ToolRegistry(WorkspaceSandbox(tmp_path))
    agent = AgentRuntime(router, tools=tools, max_steps=5)

    result = await agent.run("create a note", task_type="coding")
    assert result.content == "Created note.txt"
    assert result.tool_calls == 1
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "hello"
    assert len(result.file_changes) == 1
    assert result.file_changes[0]["path"] == "note.txt"
    assert result.file_changes[0]["action"] == "created"
