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


def test_lifespan_reconciles_then_prepares_and_sweeps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main

    calls: list[str] = []
    monkeypatch.setattr(
        main, "reconcile_interrupted_runs", lambda: calls.append("reconcile")
    )
    monkeypatch.setattr(
        main,
        "prepare_temp_root",
        lambda root: calls.append("prepare") or root,
    )
    monkeypatch.setattr(main, "sweep_orphaned_runs", lambda root: calls.append("sweep"))

    with TestClient(main.app):
        assert calls == ["reconcile", "prepare", "sweep"]


def test_temp_root_failure_prevents_app_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main
    from app.github.workspace import WorkspaceError

    monkeypatch.setattr(main, "reconcile_interrupted_runs", lambda: ())

    def fail_prepare(root: object) -> None:
        raise WorkspaceError("unsafe temporary workspace")

    monkeypatch.setattr(main, "prepare_temp_root", fail_prepare)
    with pytest.raises(WorkspaceError, match="unsafe temporary workspace"):
        with TestClient(main.app):
            pass
