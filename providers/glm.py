"""GLM (Zhipu) provider — OpenAI-compatible API."""

from __future__ import annotations

import os
from typing import Optional

from .base import ModelCapability, ModelInfo
from .openai_compatible import OpenAICompatibleProvider

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


def _default_models() -> list[ModelInfo]:
    return [
        ModelInfo(
            id="glm-4-flash",
            provider="glm",
            display_name="GLM-4 Flash",
            context_window=128_000,
            capabilities=[
                ModelCapability.CODE_GENERATION,
                ModelCapability.CODE_EDIT,
                ModelCapability.FAST,
                ModelCapability.CHEAP,
                ModelCapability.TOOL_USE,
            ],
            supports_tools=True,
            is_free_tier_available=True,
        ),
        ModelInfo(
            id="glm-4-plus",
            provider="glm",
            display_name="GLM-4 Plus",
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
    ]


class GLMProvider(OpenAICompatibleProvider):
    name = "glm"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        key = api_key or os.getenv("ZHIPU_API_KEY") or os.getenv("GLM_API_KEY")
        super().__init__(
            api_key=key,
            base_url=base_url or DEFAULT_BASE_URL,
            models=_default_models(),
            **kwargs,
        )
