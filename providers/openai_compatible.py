"""
Shared OpenAI-compatible HTTP client.

Most Chinese coding models (DeepSeek, Qwen, GLM, Kimi) expose Chat Completions
compatible with the OpenAI SDK. Concrete providers only supply base_url,
default models, and capability metadata.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Optional

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
)

from .base import (
    BaseProvider,
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ModelInfo,
)
from .errors import AuthError, ProviderError, RateLimitError, ServerError, TimeoutError


class OpenAICompatibleProvider(BaseProvider):
    """Thin wrapper around AsyncOpenAI for OpenAI-compatible endpoints."""

    name = "openai_compatible"
    default_timeout: float = 120.0

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        *,
        models: Optional[list[ModelInfo]] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ):
        super().__init__(api_key=api_key, base_url=base_url, **kwargs)
        self._static_models = models or []
        self.timeout = timeout or self.default_timeout
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self.api_key:
                raise AuthError(
                    f"{self.name}: missing API key. Set the corresponding env var.",
                    provider=self.name,
                )
            if not self.base_url:
                raise ProviderError(f"{self.name}: base_url is required", provider=self.name)
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def list_models(self) -> list[ModelInfo]:
        return list(self._static_models)

    def _messages_payload(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for msg in messages:
            item: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.name:
                item["name"] = msg.name
            if msg.tool_call_id:
                item["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                item["tool_calls"] = msg.tool_calls
                # OpenAI requires content to be present; null is fine when tool_calls exist.
                if msg.content is None:
                    item["content"] = None
            payload.append(item)
        return payload

    def _build_kwargs(self, request: ChatCompletionRequest) -> dict[str, Any]:
        model = request.model
        if not model and self._static_models:
            model = self._static_models[0].id
        if not model:
            raise ProviderError(f"{self.name}: no model specified", provider=self.name)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._messages_payload(request.messages),
            "temperature": request.temperature,
            "stream": request.stream,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.tools:
            kwargs["tools"] = request.tools
        if request.tool_choice is not None:
            kwargs["tool_choice"] = request.tool_choice
        if request.extra:
            kwargs.update(request.extra)
        return kwargs

    def _map_exception(self, exc: Exception) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, AuthenticationError):
            return AuthError(str(exc), provider=self.name)
        if isinstance(exc, APITimeoutError):
            return TimeoutError(str(exc), provider=self.name)
        if isinstance(exc, APIConnectionError):
            return ServerError(str(exc), provider=self.name, status_code=503)
        if isinstance(exc, APIStatusError):
            code = exc.status_code
            if code == 429:
                return RateLimitError(str(exc), provider=self.name)
            if code in (401, 403):
                return AuthError(str(exc), provider=self.name)
            if code >= 500:
                return ServerError(str(exc), provider=self.name, status_code=code)
            return ProviderError(str(exc), provider=self.name, status_code=code, retryable=False)
        return ProviderError(str(exc), provider=self.name, retryable=False)

    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        kwargs = self._build_kwargs(request.model_copy(update={"stream": False}))
        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise self._map_exception(exc) from exc

        choice = response.choices[0]
        message = choice.message
        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for tc in message.tool_calls
            ]

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }

        return ChatCompletionResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage=usage,
            raw=response,
        )

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        kwargs = self._build_kwargs(request.model_copy(update={"stream": True}))
        try:
            stream = await self.client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                tool_calls = None
                if delta.tool_calls:
                    tool_calls = []
                    for tc in delta.tool_calls:
                        entry: dict[str, Any] = {"index": tc.index}
                        if tc.id:
                            entry["id"] = tc.id
                        if tc.function:
                            entry["function"] = {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments or "",
                            }
                        tool_calls.append(entry)
                yield ChatCompletionChunk(
                    content=delta.content,
                    tool_calls=tool_calls,
                    finish_reason=chunk.choices[0].finish_reason,
                )
        except Exception as exc:
            raise self._map_exception(exc) from exc


def parse_tool_arguments(raw: str) -> dict[str, Any]:
    """Parse tool-call argument JSON safely."""
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_raw": raw, "_error": "invalid_json"}
    return data if isinstance(data, dict) else {"_value": data}
