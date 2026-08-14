"""DeepSeek provider — OpenAI-compatible API."""

from __future__ import annotations

import os
from typing import Optional

from .base import ModelCapability, ModelInfo
from .openai_compatible import OpenAICompatibleProvider

DEFAULT_BASE_URL = "https://api.deepseek.com"


def _default_models() -> list[ModelInfo]:
    return [
        ModelInfo(
            id="deepseek-chat",
            provider="deepseek",
            display_name="DeepSeek Chat",
            context_window=128_000,
            max_output_tokens=8192,
            capabilities=[
                ModelCapability.CODE_GENERATION,
                ModelCapability.CODE_EDIT,
                ModelCapability.FAST,
                ModelCapability.CHEAP,
                ModelCapability.TOOL_USE,
            ],
            supports_tools=True,
            is_free_tier_available=True,
            input_price_per_million=0.14,
            output_price_per_million=0.28,
        ),
        ModelInfo(
            id="deepseek-reasoner",
            provider="deepseek",
            display_name="DeepSeek Reasoner",
            context_window=128_000,
            max_output_tokens=8192,
            capabilities=[
                ModelCapability.REASONING,
                ModelCapability.CODE_GENERATION,
                ModelCapability.TOOL_USE,
            ],
            supports_tools=True,
            is_free_tier_available=True,
        ),
    ]


class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        **kwargs,
    ):
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        super().__init__(
            api_key=key,
            base_url=base_url or DEFAULT_BASE_URL,
            models=_default_models(),
            **kwargs,
        )
