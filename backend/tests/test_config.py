"""Configuration tests for required environment variables."""

import tempfile
from pathlib import Path

import pytest
from conftest import assert_safe_test_database
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
DEFAULT_TEMP_CLONE_DIR = Path(tempfile.gettempdir()) / "repopulse-clones"


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


def test_short_session_secret_is_rejected() -> None:
    values = REQUIRED_SETTINGS | {"SESSION_SECRET": "too-short"}

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, **values)

    assert "SESSION_SECRET" in str(exc_info.value)


def test_source_file_size_setting_default_and_boundaries() -> None:
    default_settings = Settings(_env_file=None, **REQUIRED_SETTINGS)
    assert default_settings.MAX_SOURCE_FILE_SIZE_BYTES == 1_048_576

    for size in (1, 16_777_216):
        configured = Settings(
            _env_file=None,
            **REQUIRED_SETTINGS,
            MAX_SOURCE_FILE_SIZE_BYTES=size,
        )
        assert configured.MAX_SOURCE_FILE_SIZE_BYTES == size


@pytest.mark.parametrize("size", [0, -1, 16_777_217, True, "not-an-integer"])
def test_invalid_source_file_size_setting_is_rejected(size: object) -> None:
    with pytest.raises(
        ValidationError,
        match="MAX_SOURCE_FILE_SIZE_BYTES must be an integer from 1 to 16777216.",
    ):
        Settings(
            _env_file=None,
            **REQUIRED_SETTINGS,
            MAX_SOURCE_FILE_SIZE_BYTES=size,
        )


def test_temp_clone_dir_defaults_and_accepts_absolute_path(tmp_path: Path) -> None:
    default_settings = Settings(_env_file=None, **REQUIRED_SETTINGS)
    assert default_settings.TEMP_CLONE_DIR == DEFAULT_TEMP_CLONE_DIR

    configured = Settings(
        _env_file=None,
        **REQUIRED_SETTINGS,
        TEMP_CLONE_DIR=tmp_path,
    )
    assert configured.TEMP_CLONE_DIR == tmp_path


@pytest.mark.parametrize("value", ["relative/path", ""])
def test_temp_clone_dir_optional_and_rejects_relative_path(value: str) -> None:
    if value == "":
        settings_value = Settings(
            _env_file=None,
            **REQUIRED_SETTINGS,
            TEMP_CLONE_DIR=value,
        )
        assert settings_value.TEMP_CLONE_DIR == DEFAULT_TEMP_CLONE_DIR
        return
    with pytest.raises(
        ValidationError, match="TEMP_CLONE_DIR must be an absolute path."
    ):
        Settings(_env_file=None, **REQUIRED_SETTINGS, TEMP_CLONE_DIR=value)


def test_safe_test_database_name_is_accepted() -> None:
    assert_safe_test_database(
        "postgresql+psycopg://user:password@localhost:5432/repopulse_test",
        {"repopulse"},
    )


@pytest.mark.parametrize(
    ("url", "forbidden_names"),
    [
        (
            "postgresql+psycopg://user:password@localhost:5432/repopulse",
            set(),
        ),
        (
            "postgresql+psycopg://user:password@localhost:5432/repopulse_test",
            {"repopulse_test"},
        ),
        ("sqlite:///repopulse_test.db", set()),
    ],
)
def test_unsafe_test_database_is_rejected(url: str, forbidden_names: set[str]) -> None:
    with pytest.raises(BaseException, match="TEST_DATABASE_URL"):
        assert_safe_test_database(url, forbidden_names)


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
