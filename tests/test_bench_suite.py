"""Offline benchmark suite tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.benchmark.runner import run_benchmark
from core.benchmark.scores import ModelScoreStore
from core.benchmark.tasks import default_tasks, list_task_ids


def test_default_tasks_non_empty() -> None:
    tasks = default_tasks()
    assert len(tasks) >= 8
    ids = {t.id for t in tasks}
    assert ids >= {
        "write_hello",
        "implement_add",
        "find_marker",
        "fix_mul_bug",
        "write_config",
        "list_inventory",
        "find_secret_key",
        "implement_factorial",
    }
    assert list_task_ids() == [t.id for t in tasks]


def test_default_tasks_only_filter() -> None:
    subset = default_tasks(only=["write_hello", "fix_mul_bug"])
    assert [t.id for t in subset] == ["write_hello", "fix_mul_bug"]
    with pytest.raises(ValueError, match="Unknown"):
        default_tasks(only=["nope"])


@pytest.mark.asyncio
async def test_mock_benchmark_passes(tmp_path: Path) -> None:
    store = ModelScoreStore(tmp_path / "scores.json")
    report = await run_benchmark(mock=True, score_store=store, update_scores=True)
    assert report.failed == 0
    assert report.passed == report.total
    assert report.total >= 8
    assert report.quality == 100.0
    assert report.mode == "mock"


@pytest.mark.asyncio
async def test_mock_benchmark_only(tmp_path: Path) -> None:
    report = await run_benchmark(mock=True, only=["write_config"], update_scores=False)
    assert report.total == 1
    assert report.results[0].task_id == "write_config"
    assert report.passed == 1
