"""Pytest configuration and shared fixtures for backend tests."""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

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
