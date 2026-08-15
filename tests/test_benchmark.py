"""Model score store / router bonus tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.benchmark.scores import ModelScoreStore
from core.router.router import SmartRouter
from providers.mock import MockProvider


def test_score_store_quality_and_bonus(tmp_path: Path) -> None:
    store = ModelScoreStore(tmp_path / "scores.json")
    store.set_quality("deepseek", "deepseek-chat", 85)
    for _ in range(3):
        store.record_outcome("deepseek", "deepseek-chat", success=True, latency_ms=800)
    entry = store.get("deepseek", "deepseek-chat")
    assert entry.quality == 85
    assert entry.routing_bonus() >= 8  # quality//10=8 + success + latency
    assert store.summary()["models"]["deepseek/deepseek-chat"]["calls"] == 3


@pytest.mark.asyncio
async def test_router_prefers_higher_benchmark_score(tmp_path: Path) -> None:
    store = ModelScoreStore(tmp_path / "scores.json")
    store.set_quality("backup", "mock-model", 95)

    a = MockProvider(model_id="mock-model")
    a.name = "flaky"
    b = MockProvider(model_id="mock-model")
    b.name = "backup"

    router = SmartRouter([a, b], score_store=store, use_scores=True)
    router.default_order = ["flaky", "backup"]
    await router.refresh_models()

    # Equal rule score; backup should win via quality bonus.
    decisions = await router.candidates(task_type="coding")
    assert decisions[0].provider.name == "backup"


@pytest.mark.asyncio
async def test_router_records_outcomes(tmp_path: Path) -> None:
    store = ModelScoreStore(tmp_path / "scores.json")
    router = SmartRouter([MockProvider()], score_store=store, use_scores=True)
    from providers.base import ChatCompletionRequest, ChatMessage

    await router.chat_with_fallback(
        ChatCompletionRequest(messages=[ChatMessage(role="user", content="hi")])
    )
    entry = store.get("mock", "mock-model")
    assert entry.calls == 1
    assert entry.successes == 1
