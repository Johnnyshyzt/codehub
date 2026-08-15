"""Router + fallback unit tests."""

from __future__ import annotations

import pytest

from core.router.router import SmartRouter
from providers.base import ChatCompletionRequest, ChatCompletionResponse, ChatMessage
from providers.mock import BackupProvider, FlakyThenOkProvider, MockProvider


@pytest.mark.asyncio
async def test_select_prefers_cheap_for_simple_edit() -> None:
    router = SmartRouter([MockProvider()], use_scores=False)
    provider, model = await router.select(task_type="simple_edit")
    assert provider.name == "mock"
    assert model.id == "mock-model"


@pytest.mark.asyncio
async def test_fallback_on_rate_limit() -> None:
    flaky = FlakyThenOkProvider(fail_times=99, fail_with="rate_limit")
    backup = BackupProvider(
        scripted_responses=[
            ChatCompletionResponse(content="from-backup", finish_reason="stop")
        ]
    )
    router = SmartRouter([flaky, backup], use_scores=False)
    # Prefer flaky first by default_order won't include them — order is insertion
    # via providers dict. Override default_order for determinism.
    router.default_order = ["flaky", "backup"]

    decision, response = await router.chat_with_fallback(
        ChatCompletionRequest(messages=[ChatMessage(role="user", content="hi")]),
        task_type="coding",
    )
    assert decision.provider.name == "backup"
    assert response.content == "from-backup"


@pytest.mark.asyncio
async def test_all_providers_fail_raises() -> None:
    a = MockProvider(fail_times=99)
    a.name = "a"
    b = MockProvider(fail_times=99)
    b.name = "b"
    router = SmartRouter([a, b], use_scores=False)
    router.default_order = ["a", "b"]

    with pytest.raises(RuntimeError, match="All providers failed"):
        await router.chat_with_fallback(
            ChatCompletionRequest(messages=[ChatMessage(role="user", content="hi")])
        )


@pytest.mark.asyncio
async def test_stream_emits_tokens() -> None:
    tokens: list[str] = []

    async def on_token(text: str) -> None:
        tokens.append(text)

    router = SmartRouter([MockProvider()], use_scores=False)
    decision, response = await router.chat_with_fallback(
        ChatCompletionRequest(messages=[ChatMessage(role="user", content="hello")]),
        stream=True,
        on_token=on_token,
    )
    assert decision.provider.name == "mock"
    assert response.content
    assert tokens
    assert "".join(tokens) == response.content
