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


def test_build_providers_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.config import build_providers

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_API_KEY", raising=False)

    providers = build_providers(only=["deepseek"])
    assert len(providers) == 1
    assert providers[0].name == "deepseek"
    with pytest.raises(ValueError, match="Unknown"):
        build_providers(only=["nope"])


@pytest.mark.asyncio
async def test_benchmark_matrix_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Matrix loops providers; mock each live slice via patched run_benchmark."""
    from core.benchmark import runner as runner_mod
    from core.benchmark.runner import BenchReport, TaskResult, run_benchmark_matrix

    calls: list[list[str] | None] = []

    async def fake_run_benchmark(**kwargs):
        calls.append(kwargs.get("providers"))
        name = (kwargs.get("providers") or ["x"])[0]
        return BenchReport(
            mode=f"live:{name}",
            passed=1,
            failed=0,
            results=[
                TaskResult(
                    task_id="write_hello",
                    title="t",
                    passed=True,
                    detail="ok",
                    provider=name,
                    model="m",
                )
            ],
            quality=100.0,
        )

    monkeypatch.setattr(runner_mod, "run_benchmark", fake_run_benchmark)
    monkeypatch.setattr(
        "core.config.configured_provider_names",
        lambda: ["deepseek", "qwen"],
    )
    matrix = await run_benchmark_matrix(update_scores=False)
    assert matrix.providers == ["deepseek", "qwen"]
    assert matrix.passed_providers == 2
    assert calls == [["deepseek"], ["qwen"]]
