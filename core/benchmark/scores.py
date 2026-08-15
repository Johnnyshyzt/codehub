"""Local model score / benchmark telemetry for Smart Router."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def default_scores_path() -> Path:
    override = os.getenv("CODEHUB_SCORES_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".codehub" / "model_scores.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def model_key(provider: str, model: str) -> str:
    return f"{provider}/{model}"


@dataclass
class ModelScore:
    provider: str
    model: str
    # Manual / benchmark quality 0-100 (optional).
    quality: Optional[float] = None
    calls: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    updated_at: str = field(default_factory=_utc_now)

    @property
    def success_rate(self) -> float:
        if self.calls <= 0:
            return 0.5  # neutral prior
        return self.successes / self.calls

    @property
    def avg_latency_ms(self) -> float:
        if self.successes <= 0:
            return 0.0
        return self.total_latency_ms / self.successes

    def routing_bonus(self) -> int:
        """
        Integer bonus added to rule-based router score.

        quality (0-100) → up to +10
        success_rate → up to +5
        low latency → up to +3
        """
        bonus = 0
        if self.quality is not None:
            bonus += int(max(0.0, min(100.0, float(self.quality))) // 10)
        if self.calls >= 3:
            bonus += int(round(self.success_rate * 5))
            # Prefer snappier models when we have latency data.
            if self.avg_latency_ms > 0:
                if self.avg_latency_ms < 1500:
                    bonus += 3
                elif self.avg_latency_ms < 4000:
                    bonus += 1
        return bonus

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["success_rate"] = round(self.success_rate, 4)
        data["avg_latency_ms"] = round(self.avg_latency_ms, 2)
        data["routing_bonus"] = self.routing_bonus()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelScore:
        quality = data.get("quality")
        return cls(
            provider=str(data.get("provider") or "unknown"),
            model=str(data.get("model") or "unknown"),
            quality=float(quality) if quality is not None else None,
            calls=int(data.get("calls") or 0),
            successes=int(data.get("successes") or 0),
            failures=int(data.get("failures") or 0),
            total_latency_ms=float(data.get("total_latency_ms") or 0.0),
            updated_at=str(data.get("updated_at") or _utc_now()),
        )


class ModelScoreStore:
    """Thread-safe JSON store of per-model scores under ~/.codehub/model_scores.json."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_scores_path()
        self._lock = threading.Lock()

    def load_all(self) -> dict[str, ModelScore]:
        with self._lock:
            return self._load_unlocked()

    def get(self, provider: str, model: str) -> ModelScore:
        key = model_key(provider, model)
        scores = self.load_all()
        return scores.get(key) or ModelScore(provider=provider, model=model)

    def routing_bonus(self, provider: str, model: str) -> int:
        return self.get(provider, model).routing_bonus()

    def set_quality(self, provider: str, model: str, quality: float) -> ModelScore:
        quality = max(0.0, min(100.0, float(quality)))
        with self._lock:
            scores = self._load_unlocked()
            key = model_key(provider, model)
            entry = scores.get(key) or ModelScore(provider=provider, model=model)
            entry.quality = quality
            entry.updated_at = _utc_now()
            scores[key] = entry
            self._save_unlocked(scores)
            return entry

    def record_outcome(
        self,
        provider: str,
        model: str,
        *,
        success: bool,
        latency_ms: float = 0.0,
    ) -> ModelScore:
        with self._lock:
            scores = self._load_unlocked()
            key = model_key(provider, model)
            entry = scores.get(key) or ModelScore(provider=provider, model=model)
            entry.calls += 1
            if success:
                entry.successes += 1
                entry.total_latency_ms += max(0.0, float(latency_ms))
            else:
                entry.failures += 1
            entry.updated_at = _utc_now()
            scores[key] = entry
            self._save_unlocked(scores)
            return entry

    def summary(self) -> dict[str, Any]:
        scores = self.load_all()
        return {
            "path": str(self.path),
            "models": {k: v.to_dict() for k, v in sorted(scores.items())},
        }

    def reset(self) -> None:
        with self._lock:
            self._save_unlocked({})

    def _load_unlocked(self) -> dict[str, ModelScore]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        models = raw.get("models") if isinstance(raw, dict) else None
        if not isinstance(models, dict):
            return {}
        out: dict[str, ModelScore] = {}
        for key, value in models.items():
            if isinstance(value, dict):
                out[str(key)] = ModelScore.from_dict(value)
        return out

    def _save_unlocked(self, scores: dict[str, ModelScore]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": _utc_now(),
            "models": {k: v.to_dict() for k, v in sorted(scores.items())},
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)


_default_store: ModelScoreStore | None = None


def get_score_store(path: str | Path | None = None) -> ModelScoreStore:
    global _default_store
    if path is not None:
        return ModelScoreStore(path)
    if _default_store is None:
        _default_store = ModelScoreStore()
    return _default_store
