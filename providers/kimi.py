"""Kimi (Moonshot) provider — strong long-context, OpenAI-compatible."""

from __future__ import annotations

import os
from typing import Optional

from .base import ModelCapability, ModelInfo
from .openai_compatible import OpenAICompatibleProvider

DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"


def _default_models() -> list[ModelInfo]:
    return [
        ModelInfo(
            id="moonshot-v1-128k",
            provider="kimi",
            display_name="Kimi 128K",
            context_window=128_000,
            capabilities=[
                ModelCapability.LONG_CONTEXT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.REASONING,
                ModelCapability.TOOL_USE,
            ],
            supports_tools=True,
            is_free_tier_available=True,
        ),
        ModelInfo(
            id="kimi-latest",
            provider="kimi",
            display_name="Kimi Latest",
            context_window=256_000,
            capabilities=[
                ModelCapability.LONG_CONTEXT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.TOOL_USE,
                ModelCapability.REASONING,
            ],
            supports_tools=True,
            is_free_tier_available=True,
        ),
    ]


class KimiProvider(OpenAICompatibleProvider):
    name = "kimi"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        key = api_key or os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY")
        super().__init__(
            api_key=key,
            base_url=base_url or DEFAULT_BASE_URL,
            models=_default_models(),
            **kwargs,
        )
