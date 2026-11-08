"""Smoke test for GET /health endpoint."""

import pytest
from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    """Smoke test: verify /health returns status 200 and {'status': 'ok'}."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_reconciliation_error_prevents_app_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main

    def fail_reconciliation() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "reconcile_interrupted_runs", fail_reconciliation)
    with pytest.raises(RuntimeError, match="database unavailable"):
        with TestClient(main.app):
            pass
