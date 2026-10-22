"""Pytest configuration and shared fixtures for backend tests."""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session as DatabaseSession

# Set dummy environment variables before any app modules are imported.
# Direct assignment guarantees tests do not rely on an external .env file
# or use any real secret from the shell environment.
# These values satisfy required Settings fields without opening a database
# connection.
os.environ["SESSION_SECRET"] = "test-session-secret-for-testing-only-32bytes"
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost:5432/test"
os.environ["GITHUB_CLIENT_ID"] = "test-github-client-id"
os.environ["GITHUB_CLIENT_SECRET"] = "test-github-client-secret"
os.environ["GITHUB_PUBLIC_API_TOKEN"] = "test-public-api-token"
os.environ["FRONTEND_URL"] = "http://localhost:3000"
os.environ["API_BASE_URL"] = "http://localhost:8000"


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient fixture with lazy app import to avoid E402 import error."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def mock_default_github_repos(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock GitHub list_repositories during route tests to prevent network I/O."""
    try:
        from app.auth import routes

        monkeypatch.setattr(routes, "list_repositories", lambda token: ())
    except (ImportError, AttributeError):
        pass


@pytest.fixture(scope="session")
def test_database_engine() -> Generator[Engine, None, None]:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured for PostgreSQL tests.")

    engine = create_engine(database_url)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("Session tests require PostgreSQL; SQLite is not supported.")

    from app.database.models import Base

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def postgres_session(
    test_database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Connection, None, None]:
    from app.database.session import get_db
    from app.main import app

    with test_database_engine.connect() as connection:
        transaction = connection.begin()

        def override_get_db() -> Generator[DatabaseSession, None, None]:
            with DatabaseSession(
                bind=connection,
                join_transaction_mode="create_savepoint",
            ) as database_session:
                yield database_session

        monkeypatch.setitem(app.dependency_overrides, get_db, override_get_db)
        try:
            yield connection
        finally:
            transaction.rollback()
