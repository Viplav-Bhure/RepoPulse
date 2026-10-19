"""Tests for the temporary GitHub OAuth routes; all provider calls are mocked."""

import hashlib
import logging
import time
import urllib.parse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session as DatabaseSession

from app.auth import csrf, routes
from app.auth.oauth import (
    STATE_LIFETIME_SECONDS,
    GitHubProfile,
    OAuthAccessToken,
    OAuthProviderError,
    serialize_state_cookie,
    validate_state_cookie,
)
from app.auth.session import SESSION_COOKIE_NAME, SessionToken
from app.config import settings
from app.database.models import Session as StoredSession
from app.database.models import User

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
    set_cookie = "\n".join(response.headers.get_list("set-cookie"))
    assert f'{COOKIE_NAME}="";' in set_cookie
    assert "Max-Age=0" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie


def _create_test_session(postgres_session: Connection, user_id: int) -> str:
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
    ) as database_session:
        user = User(github_user_id=user_id, username=f"user-{user_id}", email=None)
        database_session.add(user)
        database_session.flush()
        from app.auth.session import create_session

        token = create_session(database_session, user.id)
        database_session.commit()
        return token.value


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
    set_cookie = "\n".join(response.headers.get_list("set-cookie"))
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


def test_callback_success_creates_session_and_redirects(
    monkeypatch: pytest.MonkeyPatch,
    postgres_session: object,
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

    assert response.status_code == 302
    assert response.headers["location"] == f"{settings.FRONTEND_URL}/"
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

    session_cookie = response.cookies[SESSION_COOKIE_NAME]
    set_cookie = "\n".join(response.headers.get_list("set-cookie"))
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie
    assert "Max-Age=604800" in set_cookie
    assert "Domain=" not in set_cookie
    assert "Secure" not in set_cookie
    assert "access-token-sentinel" not in set_cookie

    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
    ) as database_session:
        user = database_session.scalar(select(User).where(User.github_user_id == 42))
        assert user is not None
        assert user.username == "octocat"
        assert (
            database_session.scalar(select(func.count()).select_from(StoredSession))
            == 1
        )
        stored = database_session.scalar(select(StoredSession))
        assert stored is not None
        assert (
            stored.token_hash
            == hashlib.sha256(session_cookie.encode("ascii")).hexdigest()
        )


def test_callback_upserts_user_and_failed_callback_creates_no_session(
    monkeypatch: pytest.MonkeyPatch,
    postgres_session: object,
) -> None:
    monkeypatch.setattr(
        routes,
        "exchange_code_for_token",
        lambda **kwargs: OAuthAccessToken("access-token-sentinel"),
    )
    monkeypatch.setattr(
        routes,
        "fetch_github_profile",
        lambda token: GitHubProfile(42, "updated-octocat", "octo@example.test"),
    )
    client = _client()
    _set_callback_cookie(client)

    response = client.get(f"/auth/github/callback?code=code-sentinel&state={STATE}")

    assert response.status_code == 302
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
    ) as database_session:
        user = database_session.scalar(select(User).where(User.github_user_id == 42))
        assert user is not None
        assert user.username == "updated-octocat"
        assert user.email == "octo@example.test"

    def fail_exchange(**kwargs: object) -> None:
        raise OAuthProviderError()

    monkeypatch.setattr(routes, "exchange_code_for_token", fail_exchange)
    failed_client = _client()
    _set_callback_cookie(failed_client)
    failed_response = failed_client.get(
        f"/auth/github/callback?code=code-sentinel&state={STATE}"
    )

    assert failed_response.status_code == 502
    _assert_callback_cookie_cleared(failed_response)
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
    ) as database_session:
        assert (
            database_session.scalar(select(func.count()).select_from(StoredSession))
            == 1
        )


def test_callback_session_cookie_is_secure_for_https_api_base(
    monkeypatch: pytest.MonkeyPatch,
    postgres_session: Connection,
) -> None:
    monkeypatch.setattr(
        routes,
        "settings",
        settings.model_copy(update={"API_BASE_URL": "https://api.example.test"}),
    )
    monkeypatch.setattr(
        routes,
        "exchange_code_for_token",
        lambda **kwargs: OAuthAccessToken("access-token-sentinel"),
    )
    monkeypatch.setattr(
        routes,
        "fetch_github_profile",
        lambda token: GitHubProfile(52, "secure-octocat", None),
    )
    client = _client()
    _set_callback_cookie(client)

    response = client.get(f"/auth/github/callback?code=code-sentinel&state={STATE}")

    assert response.status_code == 302
    set_cookie = "\n".join(response.headers.get_list("set-cookie"))
    assert SESSION_COOKIE_NAME in set_cookie
    assert "Secure" in set_cookie
    assert "Domain=" not in set_cookie


def test_auth_me_requires_valid_session_and_returns_profile(
    postgres_session: Connection,
) -> None:
    unauthenticated = _client().get("/auth/me")
    assert unauthenticated.status_code == 401

    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
    ) as database_session:
        user = User(github_user_id=77, username="session-user", email=None)
        database_session.add(user)
        database_session.flush()
        user_id = user.id
        from app.auth.session import create_session

        token = create_session(database_session, user_id)
        raw_token = token.value
        database_session.commit()

    client = _client()
    client.cookies.set(SESSION_COOKIE_NAME, raw_token)
    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": user_id,
        "github_user_id": 77,
        "username": "session-user",
        "email": None,
    }


def test_logout_revokes_session_and_repeated_logout_is_safe(
    postgres_session: Connection,
) -> None:
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
    ) as database_session:
        user = User(github_user_id=88, username="logout-user", email=None)
        database_session.add(user)
        database_session.flush()
        user_id = user.id
        from app.auth.session import create_session

        token = create_session(database_session, user_id)
        raw_token = token.value
        database_session.commit()

    client = _client()
    client.cookies.set(SESSION_COOKIE_NAME, raw_token)

    response = client.post(
        "/auth/logout",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 204
    set_cookie = "\n".join(response.headers.get_list("set-cookie"))
    assert f'{SESSION_COOKIE_NAME}="";' in set_cookie
    assert "Max-Age=0" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie
    assert "Secure" not in set_cookie
    assert "Domain=" not in set_cookie
    assert client.get("/auth/me").status_code == 401

    repeated = client.post("/auth/logout")
    assert repeated.status_code == 204


def test_logout_accepts_configured_production_origin(
    monkeypatch: pytest.MonkeyPatch,
    postgres_session: Connection,
) -> None:
    production_settings = settings.model_copy(
        update={
            "FRONTEND_URL": "https://app.example.test",
            "API_BASE_URL": "https://api.example.test",
        }
    )
    monkeypatch.setattr(
        csrf,
        "settings",
        production_settings,
    )
    monkeypatch.setattr(routes, "settings", production_settings)
    token = _create_test_session(postgres_session, 89)
    client = _client()
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.post(
        "/auth/logout",
        headers={"Origin": "https://app.example.test"},
    )

    assert response.status_code == 204
    set_cookie = "\n".join(response.headers.get_list("set-cookie"))
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie
    assert "Secure" in set_cookie
    assert "Domain=" not in set_cookie
    assert client.get("/auth/me").status_code == 401


@pytest.mark.parametrize("origin", [None, "https://untrusted.example.test"])
def test_logout_rejects_invalid_origin_without_revoking_session(
    origin: str | None,
    postgres_session: Connection,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = _create_test_session(postgres_session, 90 if origin is None else 91)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    client = _client()
    client.cookies.set(SESSION_COOKIE_NAME, token)
    headers = {} if origin is None else {"Origin": origin}

    with caplog.at_level(logging.DEBUG):
        response = client.post("/auth/logout", headers=headers)

    assert response.status_code == 403
    assert token not in response.text
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
    ) as database_session:
        stored_session = database_session.scalar(
            select(StoredSession).where(StoredSession.token_hash == token_hash)
        )
        assert stored_session is not None
    application_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name == "app" or record.name.startswith("app.")
    )
    assert token not in application_logs


def test_callback_redacts_session_token_from_repr_body_and_logs(
    monkeypatch: pytest.MonkeyPatch,
    postgres_session: Connection,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        routes,
        "exchange_code_for_token",
        lambda **kwargs: OAuthAccessToken("access-token-sentinel"),
    )
    monkeypatch.setattr(
        routes,
        "fetch_github_profile",
        lambda token: GitHubProfile(93, "redacted-user", None),
    )
    client = _client()
    _set_callback_cookie(client)

    with caplog.at_level(logging.DEBUG):
        response = client.get(f"/auth/github/callback?code=code-sentinel&state={STATE}")

    session_token = response.cookies[SESSION_COOKIE_NAME]
    assert session_token not in repr(SessionToken(session_token))
    assert session_token
    application_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name == "app" or record.name.startswith("app.")
    )
    for sensitive_value in (
        session_token,
        "access-token-sentinel",
        "code-sentinel",
        STATE,
        SESSION_SECRET,
    ):
        assert sensitive_value not in response.text
        assert sensitive_value not in repr(response)
        assert sensitive_value not in application_logs
    assert "<redacted>" not in response.text
    assert response.cookies[SESSION_COOKIE_NAME] == session_token


def test_session_lookup_hashes_token_and_rejects_expired_or_invalid_tokens(
    postgres_session: Connection,
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.auth.session import create_session, get_session_user

    issued_at = datetime(2026, 10, 19, tzinfo=UTC)
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
    ) as database_session:
        user = User(github_user_id=99, username="expiry-user", email=None)
        database_session.add(user)
        database_session.flush()
        user_id = user.id
        valid_token = create_session(database_session, user_id, now=issued_at)
        expired_token = create_session(
            database_session,
            user_id,
            now=issued_at - timedelta(days=8),
        )
        valid_raw = valid_token.value
        expired_raw = expired_token.value
        database_session.commit()

    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
    ) as database_session:
        assert get_session_user(database_session, valid_raw, now=issued_at) is not None
        assert get_session_user(database_session, expired_raw, now=issued_at) is None
        assert (
            get_session_user(
                database_session,
                "not-a-session-token",
                now=issued_at,
            )
            is None
        )

        stored = database_session.scalars(select(StoredSession)).all()
        assert len(stored) == 1
        assert stored[0].user_id == user_id


def test_auth_me_rejects_invalid_session_cookie(postgres_session: Connection) -> None:
    client = _client()
    client.cookies.set(SESSION_COOKIE_NAME, "invalid-session-token")

    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


def test_expired_session_cookie_is_rejected_and_deleted(
    postgres_session: Connection,
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.auth.session import create_session

    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
    ) as database_session:
        user = User(github_user_id=100, username="expired-user", email=None)
        database_session.add(user)
        database_session.flush()
        token = create_session(
            database_session,
            user.id,
            now=datetime.now(UTC) - timedelta(days=8),
        )
        raw_token = token.value
        database_session.commit()

    client = _client()
    client.cookies.set(SESSION_COOKIE_NAME, raw_token)

    response = client.get("/auth/me")

    assert response.status_code == 401


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
