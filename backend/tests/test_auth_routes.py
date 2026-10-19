"""Tests for the temporary GitHub OAuth routes; all provider calls are mocked."""

import logging
import time
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from app.auth import routes
from app.auth.oauth import (
    STATE_LIFETIME_SECONDS,
    GitHubProfile,
    OAuthAccessToken,
    OAuthProviderError,
    serialize_state_cookie,
    validate_state_cookie,
)
from app.config import settings

SESSION_SECRET = "test-session-secret-for-testing-only-32bytes"
STATE = "test-state-value-that-is-long-enough-for-validation"
VERIFIER = "v" * 64
COOKIE_NAME = routes.STATE_COOKIE_NAME
SENSITIVE_VALUES = (
    "code-sentinel",
    STATE,
    "access-token-sentinel",
    "cookie-sentinel",
    "authorization-header-sentinel",
    "provider-body-sentinel",
    "client-secret-sentinel",
    SESSION_SECRET,
)


def _state_cookie(*, issued_at: int | None = None) -> str:
    return serialize_state_cookie(
        state=STATE,
        code_verifier=VERIFIER,
        session_secret=SESSION_SECRET,
        issued_at=int(time.time()) if issued_at is None else issued_at,
    )


def _client() -> TestClient:
    from app.main import app

    return TestClient(app, follow_redirects=False)


def _set_callback_cookie(client: TestClient, cookie: str | None = None) -> None:
    client.cookies.set(COOKIE_NAME, cookie or _state_cookie())


def _assert_callback_cookie_cleared(response: object) -> None:
    set_cookie = response.headers.get("set-cookie", "")
    assert f'{COOKIE_NAME}="";' in set_cookie
    assert "Max-Age=0" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie


def test_login_redirect_sets_signed_state_cookie_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "settings",
        settings.model_copy(update={"SESSION_SECRET": SESSION_SECRET}),
    )

    response = _client().get("/auth/github/login")

    assert response.status_code == 302
    location = urllib.parse.urlsplit(response.headers["location"])
    assert location.netloc == "github.com"
    assert location.path == "/login/oauth/authorize"
    query = urllib.parse.parse_qs(location.query)
    assert query["redirect_uri"] == ["http://localhost:8000/auth/github/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert "scope" not in query

    state_cookie = response.cookies[COOKIE_NAME]
    assert len(state_cookie) < 2048
    validated = validate_state_cookie(
        state_cookie=state_cookie,
        returned_state=query["state"][0],
        session_secret=SESSION_SECRET,
    )
    assert validated.code_verifier
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie
    assert f"Max-Age={STATE_LIFETIME_SECONDS}" in set_cookie
    assert "Domain=" not in set_cookie
    assert "Secure" not in set_cookie


def test_login_cookie_is_secure_for_https_api_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    https_settings = settings.model_copy(
        update={"API_BASE_URL": "https://api.example.test"}
    )
    monkeypatch.setattr(routes, "settings", https_settings)

    response = _client().get("/auth/github/login")

    assert response.status_code == 302
    assert "Secure" in response.headers["set-cookie"]


def test_callback_success_uses_helpers_and_returns_temporary_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        routes,
        "exchange_code_for_token",
        lambda **kwargs: (
            calls.append(("exchange", kwargs))
            or OAuthAccessToken("access-token-sentinel")
        ),
    )
    monkeypatch.setattr(
        routes,
        "fetch_github_profile",
        lambda token: (
            calls.append(("profile", token)) or GitHubProfile(42, "octocat", None)
        ),
    )
    client = _client()
    _set_callback_cookie(client)

    response = client.get(f"/auth/github/callback?code=code-sentinel&state={STATE}")

    assert response.status_code == 501
    assert response.json() == {"detail": routes.HANDOFF_PENDING}
    assert calls[0][0] == "exchange"
    assert calls[0][1] == {
        "code": "code-sentinel",
        "code_verifier": VERIFIER,
        "client_id": settings.GITHUB_CLIENT_ID,
        "client_secret": settings.GITHUB_CLIENT_SECRET,
        "api_base_url": settings.API_BASE_URL,
    }
    assert calls[1] == ("profile", OAuthAccessToken("access-token-sentinel"))
    assert "code-sentinel" not in response.text
    assert "access-token-sentinel" not in response.text
    _assert_callback_cookie_cleared(response)


@pytest.mark.parametrize(
    ("cookie", "returned_state"),
    [
        (_state_cookie(), None),
        (_state_cookie(), "mismatched-state-value-that-is-long-enough"),
        (_state_cookie(issued_at=1), STATE),
    ],
    ids=["missing", "mismatched", "expired"],
)
def test_callback_rejects_invalid_state_and_clears_cookie(
    cookie: str,
    returned_state: str | None,
) -> None:
    client = _client()
    _set_callback_cookie(client, cookie)
    query = "" if returned_state is None else f"&state={returned_state}"

    response = client.get(f"/auth/github/callback?code=code-sentinel{query}")

    assert response.status_code == 400
    assert response.json() == {"detail": routes.AUTHENTICATION_ERROR}
    _assert_callback_cookie_cleared(response)


def test_callback_missing_cookie_clears_cookie() -> None:
    response = _client().get(f"/auth/github/callback?code=code-sentinel&state={STATE}")

    assert response.status_code == 400
    _assert_callback_cookie_cleared(response)


def test_callback_missing_code_clears_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_exchange(**kwargs: object) -> OAuthAccessToken:
        pytest.fail("code exchange must not run when the code is missing")

    monkeypatch.setattr(routes, "exchange_code_for_token", unexpected_exchange)
    client = _client()
    _set_callback_cookie(client)

    response = client.get(f"/auth/github/callback?state={STATE}")

    assert response.status_code == 400
    _assert_callback_cookie_cleared(response)


def test_callback_provider_error_is_generic_and_clears_cookie() -> None:
    client = _client()
    _set_callback_cookie(client)

    response = client.get(
        f"/auth/github/callback?state={STATE}&error=access_denied"
        "&error_description=provider-secret-sentinel"
    )

    assert response.status_code == 400
    assert "provider-secret-sentinel" not in response.text
    _assert_callback_cookie_cleared(response)


@pytest.mark.parametrize(
    "failure",
    [
        OAuthProviderError(),
        RuntimeError("unexpected " + " ".join(SENSITIVE_VALUES)),
    ],
    ids=["provider", "unexpected"],
)
def test_callback_helper_failures_are_sanitized_and_clear_cookie(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: Exception,
) -> None:
    def fail_exchange(**kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(routes, "exchange_code_for_token", fail_exchange)
    client = _client()
    _set_callback_cookie(client)

    with caplog.at_level(logging.DEBUG, logger="app.auth.routes"):
        response = client.get(f"/auth/github/callback?code=code-sentinel&state={STATE}")

    assert response.status_code == (
        502 if isinstance(failure, OAuthProviderError) else 500
    )
    assert response.json() == {"detail": routes.AUTHENTICATION_ERROR}
    _assert_callback_cookie_cleared(response)
    for sensitive_value in SENSITIVE_VALUES:
        assert sensitive_value not in response.text
        assert sensitive_value not in caplog.text


def test_callback_rejects_malformed_profile_and_clears_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "exchange_code_for_token",
        lambda **kwargs: OAuthAccessToken("access-token-sentinel"),
    )
    monkeypatch.setattr(routes, "fetch_github_profile", lambda token: object())
    client = _client()
    _set_callback_cookie(client)

    response = client.get(f"/auth/github/callback?code=code-sentinel&state={STATE}")

    assert response.status_code == 502
    assert response.json() == {"detail": routes.AUTHENTICATION_ERROR}
    assert "access-token-sentinel" not in response.text
    _assert_callback_cookie_cleared(response)
