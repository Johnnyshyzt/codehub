"""Offline benchmark suite tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.benchmark.runner import run_benchmark
from core.benchmark.scores import ModelScoreStore
from core.benchmark.tasks import default_tasks


def test_default_tasks_non_empty() -> None:
    tasks = default_tasks()
    assert len(tasks) >= 3
    assert {t.id for t in tasks} >= {"write_hello", "implement_add", "find_marker"}


@pytest.mark.asyncio
async def test_mock_benchmark_passes(tmp_path: Path) -> None:
    store = ModelScoreStore(tmp_path / "scores.json")
    report = await run_benchmark(mock=True, score_store=store, update_scores=True)
    assert report.failed == 0
    assert report.passed == report.total
    assert report.quality == 100.0
    # mock mode should not force-write quality unless we passed a store + update;
    # runner only set_quality on live. Outcomes may still be skipped without provider.
    assert report.mode == "mock"
