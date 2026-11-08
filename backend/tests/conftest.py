"""Pytest configuration and shared fixtures for backend tests."""

import os
from collections.abc import Generator, Iterable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session as DatabaseSession

_ORIGINAL_DATABASE_URL = os.environ.get("DATABASE_URL")
_ORIGINAL_POSTGRES_DB = os.environ.get("POSTGRES_DB")

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


def _database_name(url: str) -> str | None:
    try:
        return make_url(url).database
    except ArgumentError:
        return None


def assert_safe_test_database(url: str, forbidden_names: Iterable[str | None]) -> None:
    """Reject test database URLs that could point at a development database."""
    try:
        parsed_url = make_url(url)
    except ArgumentError:
        pytest.fail("TEST_DATABASE_URL is not a valid PostgreSQL URL.")

    if parsed_url.get_backend_name() != "postgresql":
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL.")

    database_name = parsed_url.database
    if not database_name or not database_name.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL database name must end with '_test'.")

    if database_name in {name for name in forbidden_names if name}:
        pytest.fail("TEST_DATABASE_URL must differ from the development database.")


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient fixture with lazy app import to avoid E402 import error."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def mock_startup_reconciliation(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Keep ordinary TestClient startup independent of PostgreSQL."""
    if "real_lifespan_reconciliation" in request.fixturenames:
        return

    from app import main

    monkeypatch.setattr(main, "reconcile_interrupted_runs", lambda: ())


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
        if os.environ.get("REQUIRE_TEST_DATABASE") == "1":
            pytest.fail("TEST_DATABASE_URL is required for PostgreSQL tests.")
        pytest.skip("TEST_DATABASE_URL is not configured for PostgreSQL tests.")

    forbidden_names = [_ORIGINAL_POSTGRES_DB]
    development_url = _ORIGINAL_DATABASE_URL
    if development_url:
        forbidden_names.append(_database_name(development_url))
    assert_safe_test_database(database_url, forbidden_names)

    engine = create_engine(database_url)

    from app.database.models import Base

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            Base.metadata.drop_all(connection)
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
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
