"""Local usage / quota telemetry for CodeHub (BYOK, on-disk)."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEFAULT_RECENT_LIMIT = 100


def default_usage_path() -> Path:
    override = os.getenv("CODEHUB_USAGE_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".codehub" / "usage.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class UsageCounters:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0

    def add(
        self,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        calls: int = 1,
    ) -> None:
        self.prompt_tokens += max(0, int(prompt_tokens))
        self.completion_tokens += max(0, int(completion_tokens))
        self.total_tokens += max(0, int(total_tokens))
        self.calls += max(0, int(calls))

    def to_dict(self) -> dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> UsageCounters:
        data = data or {}
        return cls(
            prompt_tokens=int(data.get("prompt_tokens") or 0),
            completion_tokens=int(data.get("completion_tokens") or 0),
            total_tokens=int(data.get("total_tokens") or 0),
            calls=int(data.get("calls") or 0),
        )


@dataclass
class UsageEvent:
    ts: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UsageEvent:
        return cls(
            ts=str(data.get("ts") or _utc_now()),
            provider=str(data.get("provider") or "unknown"),
            model=str(data.get("model") or "unknown"),
            prompt_tokens=int(data.get("prompt_tokens") or 0),
            completion_tokens=int(data.get("completion_tokens") or 0),
            total_tokens=int(data.get("total_tokens") or 0),
        )


@dataclass
class UsageSnapshot:
    version: int = 1
    updated_at: str = field(default_factory=_utc_now)
    totals: UsageCounters = field(default_factory=UsageCounters)
    by_provider: dict[str, UsageCounters] = field(default_factory=dict)
    by_model: dict[str, UsageCounters] = field(default_factory=dict)
    recent: list[UsageEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "updated_at": self.updated_at,
            "totals": self.totals.to_dict(),
            "by_provider": {k: v.to_dict() for k, v in sorted(self.by_provider.items())},
            "by_model": {k: v.to_dict() for k, v in sorted(self.by_model.items())},
            "recent": [e.to_dict() for e in self.recent],
        }

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> UsageSnapshot:
        data = data or {}
        by_provider = {
            str(k): UsageCounters.from_dict(v)
            for k, v in (data.get("by_provider") or {}).items()
        }
        by_model = {
            str(k): UsageCounters.from_dict(v)
            for k, v in (data.get("by_model") or {}).items()
        }
        recent_raw = data.get("recent") or []
        recent = [
            UsageEvent.from_dict(item)
            for item in recent_raw
            if isinstance(item, dict)
        ]
        return cls(
            version=int(data.get("version") or 1),
            updated_at=str(data.get("updated_at") or _utc_now()),
            totals=UsageCounters.from_dict(data.get("totals")),
            by_provider=by_provider,
            by_model=by_model,
            recent=recent,
        )


class UsageStore:
    """Thread-safe JSON usage store under ~/.codehub/usage.json."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        recent_limit: int = DEFAULT_RECENT_LIMIT,
    ):
        self.path = Path(path) if path else default_usage_path()
        self.recent_limit = max(10, int(recent_limit))
        self._lock = threading.Lock()

    def load(self) -> UsageSnapshot:
        with self._lock:
            return self._load_unlocked()

    def record(
        self,
        *,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> UsageSnapshot:
        prompt_tokens = max(0, int(prompt_tokens))
        completion_tokens = max(0, int(completion_tokens))
        total_tokens = max(0, int(total_tokens))
        if total_tokens == 0 and (prompt_tokens or completion_tokens):
            total_tokens = prompt_tokens + completion_tokens

        with self._lock:
            snap = self._load_unlocked()
            snap.updated_at = _utc_now()
            snap.totals.add(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
            provider_key = provider or "unknown"
            model_key = f"{provider_key}/{model or 'unknown'}"
            snap.by_provider.setdefault(provider_key, UsageCounters()).add(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
            snap.by_model.setdefault(model_key, UsageCounters()).add(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
            snap.recent.append(
                UsageEvent(
                    ts=snap.updated_at,
                    provider=provider_key,
                    model=model or "unknown",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )
            )
            if len(snap.recent) > self.recent_limit:
                snap.recent = snap.recent[-self.recent_limit :]
            self._save_unlocked(snap)
            return snap

    def reset(self) -> UsageSnapshot:
        with self._lock:
            snap = UsageSnapshot()
            self._save_unlocked(snap)
            return snap

    def summary(self) -> dict[str, Any]:
        return self.load().to_dict()

    def _load_unlocked(self) -> UsageSnapshot:
        if not self.path.exists():
            return UsageSnapshot()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return UsageSnapshot()
        if not isinstance(data, dict):
            return UsageSnapshot()
        return UsageSnapshot.from_dict(data)

    def _save_unlocked(self, snap: UsageSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(snap.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)


_default_store: UsageStore | None = None


def get_usage_store(path: str | Path | None = None) -> UsageStore:
    global _default_store
    if path is not None:
        return UsageStore(path)
    if _default_store is None:
        _default_store = UsageStore()
    return _default_store
