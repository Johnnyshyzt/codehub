"""
Smart Model Router with automatic fallback.

V0.1: rule-based selection + retryable failure chain across providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from providers.base import (
    BaseProvider,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelCapability,
    ModelInfo,
)
from providers.errors import AuthError, ProviderError


@dataclass
class RouteDecision:
    provider: BaseProvider
    model: ModelInfo


class SmartRouter:
    """Select a model, then fall back across providers on retryable failures."""

    def __init__(self, providers: list[BaseProvider]):
        self.providers = {p.name: p for p in providers}
        self._model_cache: dict[str, list[ModelInfo]] = {}
        # Preferred provider order for general coding tasks.
        self.default_order = ["deepseek", "qwen", "glm", "kimi"]

    async def refresh_models(self) -> None:
        for name, provider in self.providers.items():
            try:
                self._model_cache[name] = await provider.list_models()
            except Exception:
                self._model_cache[name] = []

    def _ordered_provider_names(self) -> list[str]:
        ordered = [n for n in self.default_order if n in self.providers]
        for name in self.providers:
            if name not in ordered:
                ordered.append(name)
        return ordered

    def _score(
        self,
        model: ModelInfo,
        task_type: str,
        preferred_capabilities: list[ModelCapability],
        require_tools: bool,
    ) -> int:
        if require_tools and not model.supports_tools:
            return -1

        score = 0
        caps = set(model.capabilities)

        if task_type in ("simple_edit", "fast_completion", "general", "coding"):
            if ModelCapability.CHEAP in caps:
                score += 3
            if ModelCapability.FAST in caps:
                score += 2
            if ModelCapability.CODE_EDIT in caps or ModelCapability.CODE_GENERATION in caps:
                score += 2

        if task_type in ("reasoning", "complex"):
            if ModelCapability.REASONING in caps:
                score += 5

        if task_type in ("long_context", "large_codebase"):
            if ModelCapability.LONG_CONTEXT in caps:
                score += 5
            score += min(model.context_window // 100_000, 5)

        for cap in preferred_capabilities:
            if cap in caps:
                score += 2

        if ModelCapability.TOOL_USE in caps:
            score += 1

        return score

    async def candidates(
        self,
        task_type: str = "general",
        preferred_capabilities: Optional[list[ModelCapability]] = None,
        require_tools: bool = False,
    ) -> list[RouteDecision]:
        if not self._model_cache:
            await self.refresh_models()

        preferred_capabilities = preferred_capabilities or []
        scored: list[tuple[int, RouteDecision]] = []

        for name in self._ordered_provider_names():
            provider = self.providers[name]
            for model in self._model_cache.get(name, []):
                s = self._score(model, task_type, preferred_capabilities, require_tools)
                if s < 0:
                    continue
                scored.append((s, RouteDecision(provider=provider, model=model)))

        scored.sort(key=lambda item: item[0], reverse=True)

        # Keep one best model per provider to avoid hammering the same vendor.
        seen_providers: set[str] = set()
        result: list[RouteDecision] = []
        for _, decision in scored:
            if decision.provider.name in seen_providers:
                continue
            seen_providers.add(decision.provider.name)
            result.append(decision)
        return result

    async def select(
        self,
        task_type: str = "general",
        preferred_capabilities: Optional[list[ModelCapability]] = None,
        require_tools: bool = False,
    ) -> tuple[BaseProvider, ModelInfo]:
        decisions = await self.candidates(
            task_type=task_type,
            preferred_capabilities=preferred_capabilities,
            require_tools=require_tools,
        )
        if not decisions:
            raise RuntimeError("No available models from any provider")
        best = decisions[0]
        return best.provider, best.model

    async def chat_with_fallback(
        self,
        request: ChatCompletionRequest,
        *,
        task_type: str = "general",
        require_tools: bool = False,
        max_attempts: int = 4,
    ) -> tuple[RouteDecision, ChatCompletionResponse]:
        """
        Try providers in ranked order. On retryable errors (429/5xx/timeout),
        automatically switch to the next provider.
        """
        decisions = await self.candidates(task_type=task_type, require_tools=require_tools)
        if not decisions:
            raise RuntimeError("No available models from any provider")

        errors: list[str] = []
        for decision in decisions[:max_attempts]:
            attempt = request.model_copy(update={"model": decision.model.id})
            try:
                response = await decision.provider.chat_completion(attempt)
                return decision, response
            except AuthError as exc:
                # Bad key for this provider — skip, try others.
                errors.append(f"{decision.provider.name}: {exc}")
                continue
            except ProviderError as exc:
                if exc.retryable:
                    errors.append(f"{decision.provider.name}: {exc}")
                    continue
                raise
        detail = "; ".join(errors) if errors else "unknown"
        raise RuntimeError(f"All providers failed. Last errors: {detail}")

    def list_available_models(self) -> list[ModelInfo]:
        result: list[ModelInfo] = []
        for name in self._ordered_provider_names():
            result.extend(self._model_cache.get(name, []))
        return result
