"""Environment / bootstrap helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from providers.base import BaseProvider
from providers.deepseek import DeepSeekProvider
from providers.glm import GLMProvider
from providers.kimi import KimiProvider
from providers.qwen import QwenProvider

ENV_KEYS = {
    "deepseek": ("DEEPSEEK_API_KEY",),
    "qwen": ("DASHSCOPE_API_KEY", "QWEN_API_KEY"),
    "glm": ("ZHIPU_API_KEY", "GLM_API_KEY"),
    "kimi": ("MOONSHOT_API_KEY", "KIMI_API_KEY"),
}


def load_env(dotenv_path: str | Path | None = None) -> None:
    """Load .env from cwd (or explicit path) without overriding existing env."""
    if dotenv_path:
        load_dotenv(dotenv_path, override=False)
    else:
        load_dotenv(override=False)


def _has_any_key(keys: tuple[str, ...]) -> bool:
    return any(os.getenv(k) for k in keys)


def configured_provider_names() -> list[str]:
    return [name for name, keys in ENV_KEYS.items() if _has_any_key(keys)]


def build_providers(
    *,
    include_unconfigured: bool = False,
    only: Optional[list[str]] = None,
) -> list[BaseProvider]:
    """
    Construct providers that have API keys configured.

    Set include_unconfigured=True only for listing metadata in demos.
    Pass only=["deepseek"] (etc.) to restrict to named providers.
    """
    factories: dict[str, type[BaseProvider]] = {
        "deepseek": DeepSeekProvider,
        "qwen": QwenProvider,
        "glm": GLMProvider,
        "kimi": KimiProvider,
    }
    wanted = {n.strip().lower() for n in only} if only else None
    if wanted is not None:
        unknown = wanted - set(factories)
        if unknown:
            raise ValueError(
                f"Unknown provider(s): {sorted(unknown)}. "
                f"Known: {', '.join(factories)}"
            )
    providers: list[BaseProvider] = []
    for name, cls in factories.items():
        if wanted is not None and name not in wanted:
            continue
        if include_unconfigured or _has_any_key(ENV_KEYS[name]):
            providers.append(cls())  # type: ignore[call-arg]
    return providers


def missing_key_help() -> str:
    lines = [
        "No provider API keys found. Set at least one of:",
        "  DEEPSEEK_API_KEY",
        "  DASHSCOPE_API_KEY or QWEN_API_KEY",
        "  ZHIPU_API_KEY or GLM_API_KEY",
        "  MOONSHOT_API_KEY or KIMI_API_KEY",
        "",
        "Copy .env.example to .env and fill in your keys.",
    ]
    return "\n".join(lines)
