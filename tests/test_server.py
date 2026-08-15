"""Local HTTP API smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from codehub.server import app


def test_health() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_usage_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEHUB_USAGE_PATH", str(tmp_path / "usage.json"))
    # Reset module-level default store if any.
    import core.quota.store as store_mod

    store_mod._default_store = None

    client = TestClient(app)
    resp = client.get("/v1/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert "totals" in body
    assert body["totals"]["calls"] == 0

    from core.quota import get_usage_store

    get_usage_store().record(provider="mock", model="m", total_tokens=3)
    resp2 = client.get("/v1/usage")
    assert resp2.json()["totals"]["total_tokens"] == 3

    reset = client.post("/v1/usage/reset")
    assert reset.status_code == 200
    assert reset.json()["totals"]["calls"] == 0
