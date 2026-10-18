"""Configuration tests for required environment variables."""

import pytest
from pydantic import ValidationError

from app.config import Settings

REQUIRED_SETTINGS = {
    "SESSION_SECRET": "test-session-secret-for-testing-only-32bytes",
    "DATABASE_URL": "postgresql+psycopg://test:test@localhost:5432/test",
    "GITHUB_CLIENT_ID": "test-github-client-id",
    "GITHUB_CLIENT_SECRET": "test-github-client-secret",
    "GITHUB_PUBLIC_API_TOKEN": "test-public-api-token",
    "FRONTEND_URL": "http://localhost:3000",
    "API_BASE_URL": "http://localhost:8000",
}


@pytest.mark.parametrize("missing_field", REQUIRED_SETTINGS)
def test_missing_required_env_var_fails_fast(
    monkeypatch: pytest.MonkeyPatch, missing_field: str
) -> None:
    """A missing required value is named in the validation error."""
    for field in REQUIRED_SETTINGS:
        monkeypatch.delenv(field, raising=False)

    values = {
        field: value
        for field, value in REQUIRED_SETTINGS.items()
        if field != missing_field
    }
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, **values)
    assert missing_field in str(exc_info.value)
    assert REQUIRED_SETTINGS["SESSION_SECRET"] not in str(exc_info.value)


def test_blank_github_public_api_token_is_rejected() -> None:
    """A required credential cannot be configured as an empty value."""
    values = REQUIRED_SETTINGS | {"GITHUB_PUBLIC_API_TOKEN": "  "}

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, **values)
    assert "GITHUB_PUBLIC_API_TOKEN" in str(exc_info.value)


def test_missing_settings_error_redacts_process_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings validation does not render supplied secrets in error output."""
    for field in REQUIRED_SETTINGS:
        monkeypatch.delenv(field, raising=False)

    dummy_secrets = {
        "SESSION_SECRET": "dummy-session-secret-must-not-appear",
        "GITHUB_CLIENT_SECRET": "dummy-oauth-secret-must-not-appear",
        "GITHUB_PUBLIC_API_TOKEN": "dummy-api-token-must-not-appear",
    }
    for field, value in dummy_secrets.items():
        monkeypatch.setenv(field, value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    error_output = f"{exc_info.value}\n{exc_info.value!r}"
    assert "GITHUB_CLIENT_ID" in error_output
    for value in dummy_secrets.values():
        assert value not in error_output
