"""
Base Model Provider abstraction for CodeHub.

All concrete providers (DeepSeek, Qwen, GLM, Kimi, OpenAI, Anthropic...)
must implement this interface. The Agent and Router never bind to a
specific vendor.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class ModelCapability(str, Enum):
    """High-level capability tags used by the Smart Router."""
    CODE_GENERATION = "code_generation"
    CODE_EDIT = "code_edit"
    REASONING = "reasoning"
    LONG_CONTEXT = "long_context"
    TOOL_USE = "tool_use"
    FAST = "fast"
    CHEAP = "cheap"


class ChatMessage(BaseModel):
    role: str  # "system" | "user" | "assistant" | "tool"
    content: Optional[str] = None
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class ChatCompletionRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    temperature: float = 0.2
    max_tokens: Optional[int] = None
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class ChatCompletionChunk(BaseModel):
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None


class ChatCompletionResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    raw: Optional[Any] = None


class ModelInfo(BaseModel):
    """Metadata used by Router and Quota Manager."""
    id: str
    provider: str
    display_name: str
    context_window: int = 128_000
    max_output_tokens: int = 8192
    capabilities: List[ModelCapability] = Field(default_factory=list)
    input_price_per_million: Optional[float] = None   # USD
    output_price_per_million: Optional[float] = None
    supports_tools: bool = True
    supports_vision: bool = False
    is_free_tier_available: bool = False


class BaseProvider(ABC):
    """
    Abstract base class for every model provider.

    Concrete implementations live in providers/*.py
    """

    name: str = "base"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.kwargs = kwargs

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Return models this provider can serve."""
        ...

    @abstractmethod
    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Non-streaming chat completion."""
        ...

    @abstractmethod
    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Streaming chat completion."""
        ...

    async def health_check(self) -> bool:
        """Simple connectivity / auth check. Override if needed."""
        try:
            models = await self.list_models()
            return len(models) > 0
        except Exception:
            return False
