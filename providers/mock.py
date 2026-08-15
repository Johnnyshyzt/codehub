"""In-memory mock provider for unit tests (no network)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Optional

from providers.base import (
    BaseProvider,
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelCapability,
    ModelInfo,
)
from providers.errors import RateLimitError, ServerError


class MockProvider(BaseProvider):
    name = "mock"

    def __init__(
        self,
        *,
        fail_times: int = 0,
        fail_with: str = "rate_limit",
        scripted_responses: Optional[list[ChatCompletionResponse]] = None,
        model_id: str = "mock-model",
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.fail_times = fail_times
        self.fail_with = fail_with
        self._calls = 0
        self.scripted_responses = list(scripted_responses or [])
        self.model_id = model_id

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id=self.model_id,
                provider=self.name,
                display_name="Mock Model",
                context_window=128_000,
                capabilities=[
                    ModelCapability.CODE_GENERATION,
                    ModelCapability.CODE_EDIT,
                    ModelCapability.FAST,
                    ModelCapability.CHEAP,
                    ModelCapability.TOOL_USE,
                ],
                supports_tools=True,
            )
        ]

    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        self._calls += 1
        if self._calls <= self.fail_times:
            if self.fail_with == "rate_limit":
                raise RateLimitError("mock 429", provider=self.name)
            raise ServerError("mock 500", provider=self.name, status_code=500)

        if self.scripted_responses:
            return self.scripted_responses.pop(0)

        # Echo last user message.
        last_user = next(
            (m.content for m in reversed(request.messages) if m.role == "user"),
            "ok",
        )
        return ChatCompletionResponse(
            content=f"mock-reply: {last_user}",
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        response = await self.chat_completion(request)
        yield ChatCompletionChunk(
            content=response.content,
            tool_calls=response.tool_calls,
            finish_reason=response.finish_reason or "stop",
            usage=response.usage,
        )


class FlakyThenOkProvider(MockProvider):
    name = "flaky"


class BackupProvider(MockProvider):
    name = "backup"
