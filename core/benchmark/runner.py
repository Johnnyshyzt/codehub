"""Run CodeHub offline / live benchmark suites."""

from __future__ import annotations

import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from core.agent.runtime import AgentRuntime
from core.benchmark.scores import ModelScoreStore, get_score_store
from core.benchmark.tasks import BenchTask, default_tasks
from core.factory import create_agent
from core.router.router import SmartRouter
from core.tools.filesystem import WorkspaceSandbox
from core.tools.registry import ToolRegistry
from providers.mock import MockProvider


@dataclass
class TaskResult:
    task_id: str
    title: str
    passed: bool
    detail: str
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    steps: int = 0
    tool_calls: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchReport:
    mode: str
    passed: int
    failed: int
    results: list[TaskResult] = field(default_factory=list)
    quality: Optional[float] = None

    @property
    def total(self) -> int:
        return self.passed + self.failed

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.passed / self.total

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 4),
            "quality": self.quality,
            "results": [r.to_dict() for r in self.results],
        }


async def _run_one(
    task: BenchTask,
    *,
    mock: bool,
    max_steps: int = 10,
    providers: Optional[list[str]] = None,
) -> TaskResult:
    with tempfile.TemporaryDirectory(prefix="codehub-bench-") as tmp:
        root = Path(tmp)
        task.setup(root)
        started = time.monotonic()
        provider_name = ""
        model_id = ""
        steps = 0
        tool_calls = 0
        error = ""
        try:
            if mock:
                provider = MockProvider(scripted_responses=list(task.mock_script))
                router = SmartRouter([provider], use_scores=False)
                tools = ToolRegistry(WorkspaceSandbox(root))
                agent = AgentRuntime(
                    router,
                    tools=tools,
                    max_steps=max_steps,
                    record_usage=False,
                )
            else:
                agent = create_agent(
                    workspace=root,
                    max_steps=max_steps,
                    with_tools=True,
                    record_usage=False,
                    providers=providers,
                )
                await agent.router.refresh_models()

            result = await agent.run(task.prompt, task_type="coding")
            provider_name = result.provider
            model_id = result.model
            steps = result.steps
            tool_calls = result.tool_calls
            ok, detail = task.verify(root)
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, "agent error"
            error = str(exc)
        latency_ms = (time.monotonic() - started) * 1000.0
        return TaskResult(
            task_id=task.id,
            title=task.title,
            passed=ok,
            detail=detail if ok else (error or detail),
            provider=provider_name,
            model=model_id,
            latency_ms=latency_ms,
            steps=steps,
            tool_calls=tool_calls,
            error=error,
        )


async def run_benchmark(
    *,
    mock: bool = True,
    tasks: Optional[list[BenchTask]] = None,
    only: Optional[list[str]] = None,
    providers: Optional[list[str]] = None,
    score_store: Optional[ModelScoreStore] = None,
    update_scores: bool = True,
    max_steps: int = 10,
) -> BenchReport:
    """
    Run the built-in coding bench.

    mock=True uses scripted MockProvider (CI / offline).
    mock=False uses configured live providers (needs API keys).
    providers= pin live run to one or more named providers.
    """
    if tasks is not None:
        selected = tasks
    else:
        selected = default_tasks(only=only)
    if not selected:
        raise ValueError("No benchmark tasks selected")
    if mock and providers:
        raise ValueError("providers= is only valid for live bench (mock=False)")
    results: list[TaskResult] = []
    for task in selected:
        results.append(
            await _run_one(
                task,
                mock=mock,
                max_steps=max_steps,
                providers=providers,
            )
        )

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    quality = round(100.0 * passed / len(results), 1) if results else 0.0
    mode = "mock" if mock else "live"
    if providers and len(providers) == 1:
        mode = f"live:{providers[0]}"
    elif providers:
        mode = f"live:{'+'.join(providers)}"
    report = BenchReport(
        mode=mode,
        passed=passed,
        failed=failed,
        results=results,
        quality=quality,
    )

    if update_scores and score_store is None and not mock:
        score_store = get_score_store()

    if update_scores and score_store is not None and results:
        # Attribute outcomes to the provider/model used on each task.
        for item in results:
            if not item.provider or not item.model:
                continue
            score_store.record_outcome(
                item.provider,
                item.model,
                success=item.passed,
                latency_ms=item.latency_ms,
            )
        # Blend pass-rate into quality for the primary model of the run.
        primary = next((r for r in results if r.provider and r.model), None)
        if primary and not mock:
            score_store.set_quality(primary.provider, primary.model, quality)

    return report


@dataclass
class MatrixReport:
    """Per-provider live bench results."""

    reports: list[BenchReport] = field(default_factory=list)

    @property
    def providers(self) -> list[str]:
        return [r.mode.replace("live:", "", 1) for r in self.reports]

    @property
    def passed_providers(self) -> int:
        return sum(1 for r in self.reports if r.failed == 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "providers": self.providers,
            "passed_providers": self.passed_providers,
            "reports": [r.to_dict() for r in self.reports],
        }


async def run_benchmark_matrix(
    *,
    only: Optional[list[str]] = None,
    providers: Optional[list[str]] = None,
    score_store: Optional[ModelScoreStore] = None,
    update_scores: bool = True,
    max_steps: int = 10,
) -> MatrixReport:
    """
    Run the live bench once per configured provider (no cross-provider fallback).

    Useful for comparing DeepSeek / Qwen / GLM / Kimi on the same task corpus.
    """
    from core.config import configured_provider_names, load_env

    load_env()
    names = providers or configured_provider_names()
    if not names:
        raise RuntimeError(
            "No provider API keys found for matrix bench. "
            "Configure at least one key or pass providers=."
        )

    reports: list[BenchReport] = []
    for name in names:
        report = await run_benchmark(
            mock=False,
            only=only,
            providers=[name],
            score_store=score_store,
            update_scores=update_scores,
            max_steps=max_steps,
        )
        reports.append(report)
    return MatrixReport(reports=reports)
