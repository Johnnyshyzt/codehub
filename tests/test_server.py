"""Local HTTP API smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from codehub.server import app


def test_health() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
