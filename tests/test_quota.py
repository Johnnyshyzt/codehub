"""Quota / usage store tests."""

from __future__ import annotations

from pathlib import Path

from core.quota.store import UsageStore


def test_usage_store_record_and_summary(tmp_path: Path) -> None:
    path = tmp_path / "usage.json"
    store = UsageStore(path)

    store.record(
        provider="deepseek",
        model="deepseek-chat",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )
    store.record(
        provider="deepseek",
        model="deepseek-chat",
        prompt_tokens=3,
        completion_tokens=2,
        total_tokens=5,
    )
    store.record(
        provider="qwen",
        model="qwen-plus",
        prompt_tokens=7,
        completion_tokens=1,
        total_tokens=8,
    )

    snap = store.load()
    assert snap.totals.calls == 3
    assert snap.totals.total_tokens == 28
    assert snap.by_provider["deepseek"].total_tokens == 20
    assert snap.by_provider["qwen"].calls == 1
    assert snap.by_model["deepseek/deepseek-chat"].calls == 2
    assert len(snap.recent) == 3
    assert path.exists()


def test_usage_store_reset(tmp_path: Path) -> None:
    path = tmp_path / "usage.json"
    store = UsageStore(path)
    store.record(provider="mock", model="m", total_tokens=9)
    store.reset()
    snap = store.load()
    assert snap.totals.calls == 0
    assert snap.totals.total_tokens == 0
    assert snap.by_provider == {}
    assert snap.recent == []


def test_usage_infers_total(tmp_path: Path) -> None:
    store = UsageStore(tmp_path / "u.json")
    store.record(provider="a", model="b", prompt_tokens=4, completion_tokens=6)
    snap = store.load()
    assert snap.totals.total_tokens == 10
