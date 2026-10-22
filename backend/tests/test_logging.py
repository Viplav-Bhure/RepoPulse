"""Credential redaction tests for application and request/access logs."""

import logging
import time

import pytest
from fastapi.testclient import TestClient

from app.auth import routes, session
from app.auth.oauth import serialize_state_cookie
from app.auth.session import SESSION_COOKIE_NAME
from app.logging import (
    SensitiveDataFilter,
    configure_logging,
    redact_sensitive_data,
)
from app.main import app

REDACTED = "<redacted>"
TEST_STATE = "test-oauth-state-sentinel-long-enough"
TEST_VERIFIER = "v" * 64
TEST_SESSION_SECRET = "test-session-secret-for-testing-only-32bytes"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "https://example.test/callback?code=authorization-code-sentinel"
            "&state=oauth-state-sentinel&client_id=public-client",
            "https://example.test/callback?code=<redacted>"
            "&state=<redacted>&client_id=public-client",
        ),
        (
            "access_token=github-token-sentinel "
            "code_verifier=pkce-verifier-sentinel "
            "verifier=pkce-verifier-sentinel "
            "client_secret=client-secret-sentinel api_key=api-key-sentinel",
            "access_token=<redacted> code_verifier=<redacted> "
            "verifier=<redacted> "
            "client_secret=<redacted> api_key=<redacted>",
        ),
        (
            "GITHUB_CLIENT_SECRET=github-client-secret-sentinel "
            "OPENAI_API_KEY=openai-key-sentinel",
            "GITHUB_CLIENT_SECRET=<redacted> OPENAI_API_KEY=<redacted>",
        ),
        (
            '{"access_token": "json-token-sentinel", "event": "login_failed"}',
            '{"access_token": <redacted>, "event": "login_failed"}',
        ),
        (
            "Authorization: Bearer header-token-sentinel",
            "Authorization: <redacted header>",
        ),
        (
            "Cookie: repopulse_session=cookie-token-sentinel",
            "Cookie: <redacted header>",
        ),
        (
            "Set-Cookie: repopulse_oauth_state=state-cookie-sentinel; HttpOnly",
            "Set-Cookie: <redacted header>",
        ),
        (
            "repopulse_session=session-cookie-sentinel",
            "repopulse_session=<redacted>",
        ),
    ],
)
def test_redacts_sensitive_strings(value: str, expected: str) -> None:
    assert redact_sensitive_data(value) == expected


def test_redacts_sensitive_mapping_values_and_preserves_event_fields() -> None:
    result = redact_sensitive_data(
        {
            "event": "github_oauth_callback_failed",
            "reason": "provider",
            "user_id": 42,
            "headers": {
                "Authorization": "Bearer header-token-sentinel",
                "Cookie": "repopulse_session=cookie-token-sentinel",
                "X-Request-ID": "request-123",
            },
            "access_token": "github-token-sentinel",
            "GITHUB_CLIENT_SECRET": "github-client-secret-sentinel",
            "OPENAI_API_KEY": "openai-key-sentinel",
        }
    )

    assert result == {
        "event": "github_oauth_callback_failed",
        "reason": "provider",
        "user_id": 42,
        "headers": {
            "Authorization": REDACTED,
            "Cookie": REDACTED,
            "X-Request-ID": "request-123",
        },
        "access_token": REDACTED,
        "GITHUB_CLIENT_SECRET": REDACTED,
        "OPENAI_API_KEY": REDACTED,
    }


def test_redacts_exception_message() -> None:
    error = RuntimeError(
        "provider failed access_token=github-token-sentinel "
        "and state=oauth-state-sentinel"
    )

    assert redact_sensitive_data(error) == (
        "RuntimeError: provider failed access_token=<redacted> and state=<redacted>"
    )


def test_filter_redacts_log_record_message_exception_and_extra_fields() -> None:
    error = RuntimeError("client_secret=client-secret-sentinel")
    record = logging.LogRecord(
        "app.auth.routes",
        logging.ERROR,
        __file__,
        10,
        "event=%s code=%s",
        ("github_oauth_callback_failed", "authorization-code-sentinel"),
        (type(error), error, error.__traceback__),
    )
    record.user_id = 42
    record.api_key = "api-key-sentinel"

    assert SensitiveDataFilter().filter(record)
    formatted = record.getMessage()

    assert "github_oauth_callback_failed" in formatted
    assert "user_id=42" not in formatted
    assert record.user_id == 42
    assert record.api_key == REDACTED
    for sensitive_value in (
        "authorization-code-sentinel",
        "client-secret-sentinel",
        "api-key-sentinel",
    ):
        assert sensitive_value not in formatted
    assert "RuntimeError" in formatted
    assert record.exc_info is None


def test_oauth_failure_logs_safe_event_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_exchange(**kwargs: object) -> None:
        raise RuntimeError(
            "client_secret=client-secret-sentinel "
            "access_token=github-token-sentinel "
            "api_key=api-key-sentinel"
        )

    monkeypatch.setattr(routes, "exchange_code_for_token", fail_exchange)
    client = TestClient(app, follow_redirects=False)
    client.cookies.set(
        routes.STATE_COOKIE_NAME,
        serialize_state_cookie(
            state=TEST_STATE,
            code_verifier=TEST_VERIFIER,
            session_secret=TEST_SESSION_SECRET,
            issued_at=int(time.time()),
        ),
    )

    with caplog.at_level(logging.ERROR, logger="app.auth.routes"):
        response = client.get(
            f"/auth/github/callback?code=authorization-code-sentinel&state={TEST_STATE}"
        )

    assert response.status_code == 500
    assert "github_oauth_callback_failed reason=unexpected" in caplog.text
    for sensitive_value in (
        "authorization-code-sentinel",
        TEST_STATE,
        TEST_VERIFIER,
        TEST_SESSION_SECRET,
        "client-secret-sentinel",
        "github-token-sentinel",
        "api-key-sentinel",
    ):
        assert sensitive_value not in caplog.text


def test_session_failure_logs_safe_event_without_cookie(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cookie_token = "session-cookie-token-sentinel"
    monkeypatch.setattr(
        session,
        "get_session_user",
        lambda database_session, token: None,
    )
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, cookie_token)

    with caplog.at_level(logging.WARNING, logger="app.auth.session"):
        response = client.get("/auth/me")

    assert response.status_code == 401
    assert "session_authentication_failed reason=missing_or_invalid" in caplog.text
    assert cookie_token not in caplog.text


def test_uvicorn_access_log_redacts_callback_query_parameters(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging()
    access_logger = logging.getLogger("uvicorn.access")

    with caplog.at_level(logging.INFO, logger="uvicorn.access"):
        access_logger.info(
            '%s - "%s %s HTTP/%s" %d',
            "127.0.0.1:12345",
            "GET",
            "/auth/github/callback?code=authorization-code-sentinel"
            "&state=oauth-state-sentinel",
            "1.1",
            400,
        )

    assert "/auth/github/callback" in caplog.text
    assert "GET" in caplog.text
    assert "400" in caplog.text
    assert "code=<redacted>" in caplog.text
    assert "state=<redacted>" in caplog.text
    assert "authorization-code-sentinel" not in caplog.text
    assert "oauth-state-sentinel" not in caplog.text
