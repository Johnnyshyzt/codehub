"""Qwen (DashScope) provider — OpenAI-compatible mode."""

from __future__ import annotations

import os
from typing import Optional

from .base import ModelCapability, ModelInfo
from .openai_compatible import OpenAICompatibleProvider

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _default_models() -> list[ModelInfo]:
    return [
        ModelInfo(
            id="qwen-coder-plus",
            provider="qwen",
            display_name="Qwen Coder Plus",
            context_window=128_000,
            capabilities=[
                ModelCapability.CODE_GENERATION,
                ModelCapability.CODE_EDIT,
                ModelCapability.REASONING,
                ModelCapability.TOOL_USE,
            ],
            supports_tools=True,
            is_free_tier_available=True,
        ),
        ModelInfo(
            id="qwen-plus",
            provider="qwen",
            display_name="Qwen Plus",
            context_window=1_000_000,
            capabilities=[
                ModelCapability.LONG_CONTEXT,
                ModelCapability.REASONING,
                ModelCapability.CODE_GENERATION,
                ModelCapability.TOOL_USE,
            ],
            supports_tools=True,
            is_free_tier_available=True,
        ),
    ]


class QwenProvider(OpenAICompatibleProvider):
    name = "qwen"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        key = api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
        super().__init__(
            api_key=key,
            base_url=base_url or DEFAULT_BASE_URL,
            models=_default_models(),
            **kwargs,
        )
