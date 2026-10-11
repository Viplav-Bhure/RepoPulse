"""Pytest configuration and shared fixtures for backend tests."""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

# Set dummy environment variable before any app modules are imported.
# Direct assignment guarantees tests do not rely on an external .env file
# or use any real secret from the shell environment.
# SESSION_SECRET is the only required field in Settings.
os.environ["SESSION_SECRET"] = "test-session-secret-for-testing-only-32bytes"


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient fixture with lazy app import to avoid E402 import error."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
