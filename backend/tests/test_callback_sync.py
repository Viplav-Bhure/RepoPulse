"""Callback integration tests for repository sync (task 1.10).

Tests verify that:
- callback fetches repos with the transient user token (not GITHUB_PUBLIC_API_TOKEN)
- refresh_repositories uses GITHUB_PUBLIC_API_TOKEN only
- sync failure returns 502 and does not create an authenticated session
- no token appears in responses, logs, or database rows
- existing passing callback tests are unaffected (smoke check only here;
  the full suite is in test_auth_routes.py)
"""

from __future__ import annotations

import logging
import time

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session as DatabaseSession

from app.auth.oauth import (
    GitHubProfile,
    OAuthAccessToken,
    serialize_state_cookie,
)
from app.auth.session import SESSION_COOKIE_NAME
from app.config import settings
from app.database.models import Repository, User
from app.database.models import Session as StoredSession
from app.github.client import GitHubRepository, GitHubTransportError

SESSION_SECRET = "test-session-secret-for-testing-only-32bytes"
STATE = "test-state-value-that-is-long-enough-for-validation"
VERIFIER = "v" * 64
TOKEN_SENTINEL = "access-token-sentinel"

_BASE_DT_STR = "2024-01-01T00:00:00+00:00"


def _state_cookie(*, issued_at: int | None = None) -> str:
    return serialize_state_cookie(
        state=STATE,
        code_verifier=VERIFIER,
        session_secret=SESSION_SECRET,
        issued_at=int(time.time()) if issued_at is None else issued_at,
    )


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, follow_redirects=False)


def _good_repo_payload(*, owner_login: str = "octocat") -> GitHubRepository:
    from datetime import UTC, datetime

    return GitHubRepository(
        github_repo_id=9001,
        name="my-repo",
        owner_login=owner_login,
        owner_type="User",
        default_branch="main",
        is_fork=False,
        is_archived=False,
        primary_language="Python",
        updated_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        size=50,
    )


# ---------------------------------------------------------------------------
# Callback uses transient user token, not GITHUB_PUBLIC_API_TOKEN
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("postgres_session")
def test_callback_uses_transient_token_not_public_token(
    postgres_session: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """list_repositories must be called with the transient OAuth token."""
    from app.auth import routes

    tokens_used: list[str] = []

    monkeypatch.setattr(
        routes,
        "exchange_code_for_token",
        lambda **kwargs: OAuthAccessToken(TOKEN_SENTINEL),
    )
    monkeypatch.setattr(
        routes,
        "fetch_github_profile",
        lambda token: GitHubProfile(42, "octocat", None),
    )
    monkeypatch.setattr(
        routes,
        "list_repositories",
        lambda token, **kw: tokens_used.append(token) or (_good_repo_payload(),),
    )
    monkeypatch.setattr(
        routes,
        "sync_repositories",
        lambda db, uid, uname, repos: None,
    )

    client = _client()
    client.cookies.set(routes.STATE_COOKIE_NAME, _state_cookie())

    response = client.get(f"/auth/github/callback?code=code-abc&state={STATE}")

    assert response.status_code == 302
    # list_repositories was called exactly once with the transient token
    assert tokens_used == [TOKEN_SENTINEL]
    # Public API token must not have been passed
    assert settings.GITHUB_PUBLIC_API_TOKEN not in tokens_used


# ---------------------------------------------------------------------------
# refresh_repositories uses GITHUB_PUBLIC_API_TOKEN
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("postgres_session")
def test_refresh_repositories_uses_public_api_token(
    postgres_session: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """refresh_repositories must call list_repositories with GITHUB_PUBLIC_API_TOKEN."""
    from app.repositories import sync as sync_mod

    tokens_used: list[str] = []

    monkeypatch.setattr(
        sync_mod,
        "list_repositories",
        lambda token, **kw: tokens_used.append(token) or (),
    )

    with DatabaseSession(
        bind=postgres_session, join_transaction_mode="create_savepoint"
    ) as db:
        from app.repositories.sync import refresh_repositories

        user = User(github_user_id=77, username="octocat", email=None)
        db.add(user)
        db.flush()

        refresh_repositories(db, user.id, user.username)

    assert len(tokens_used) == 1
    assert tokens_used[0] == settings.GITHUB_PUBLIC_API_TOKEN
    # Must NOT use any other token
    assert TOKEN_SENTINEL not in tokens_used


# ---------------------------------------------------------------------------
# Sync failure does not create a session
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("postgres_session")
def test_callback_sync_failure_returns_502_and_no_session(
    postgres_session: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.auth import routes

    monkeypatch.setattr(
        routes,
        "exchange_code_for_token",
        lambda **kwargs: OAuthAccessToken(TOKEN_SENTINEL),
    )
    monkeypatch.setattr(
        routes,
        "fetch_github_profile",
        lambda token: GitHubProfile(55, "failcat", None),
    )
    monkeypatch.setattr(
        routes,
        "list_repositories",
        lambda token, **kw: (_ for _ in ()).throw(GitHubTransportError()),
    )

    client = _client()
    client.cookies.set(routes.STATE_COOKIE_NAME, _state_cookie())

    response = client.get(f"/auth/github/callback?code=code-abc&state={STATE}")

    assert response.status_code == 502
    assert SESSION_COOKIE_NAME not in response.cookies

    with DatabaseSession(
        bind=postgres_session, join_transaction_mode="create_savepoint"
    ) as db:
        assert db.scalar(select(func.count()).select_from(StoredSession)) == 0, (
            "no session must be created when sync fails"
        )


# ---------------------------------------------------------------------------
# Token not in response or logs
# ---------------------------------------------------------------------------


def test_token_not_in_callback_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.auth import routes

    monkeypatch.setattr(
        routes,
        "exchange_code_for_token",
        lambda **kwargs: OAuthAccessToken(TOKEN_SENTINEL),
    )
    monkeypatch.setattr(
        routes,
        "fetch_github_profile",
        lambda token: GitHubProfile(66, "safecat", None),
    )
    monkeypatch.setattr(
        routes,
        "list_repositories",
        lambda token, **kw: (_ for _ in ()).throw(GitHubTransportError()),
    )

    client = _client()
    client.cookies.set(routes.STATE_COOKIE_NAME, _state_cookie())

    response = client.get(f"/auth/github/callback?code=code-abc&state={STATE}")

    assert TOKEN_SENTINEL not in response.text
    assert TOKEN_SENTINEL not in str(response.headers)


def test_token_not_in_logs_on_sync_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from app.auth import routes

    monkeypatch.setattr(
        routes,
        "exchange_code_for_token",
        lambda **kwargs: OAuthAccessToken(TOKEN_SENTINEL),
    )
    monkeypatch.setattr(
        routes,
        "fetch_github_profile",
        lambda token: GitHubProfile(99, "logcat", None),
    )
    monkeypatch.setattr(
        routes,
        "list_repositories",
        lambda token, **kw: (_ for _ in ()).throw(GitHubTransportError()),
    )

    client = _client()
    client.cookies.set(routes.STATE_COOKIE_NAME, _state_cookie())

    with caplog.at_level(logging.DEBUG):
        client.get(f"/auth/github/callback?code=code-abc&state={STATE}")

    for record in caplog.records:
        assert TOKEN_SENTINEL not in record.getMessage(), (
            f"token found in log: {record.getMessage()!r}"
        )


# ---------------------------------------------------------------------------
# Callback success still creates session and redirects (smoke check)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("postgres_session")
def test_callback_success_with_sync_creates_session(
    postgres_session: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.auth import routes

    monkeypatch.setattr(
        routes,
        "exchange_code_for_token",
        lambda **kwargs: OAuthAccessToken(TOKEN_SENTINEL),
    )
    monkeypatch.setattr(
        routes,
        "fetch_github_profile",
        lambda token: GitHubProfile(43, "syncat", None),
    )
    monkeypatch.setattr(
        routes,
        "list_repositories",
        lambda token, **kw: (_good_repo_payload(owner_login="syncat"),),
    )
    # sync_repositories is the real function here; we rely on PostgreSQL

    client = _client()
    client.cookies.set(routes.STATE_COOKIE_NAME, _state_cookie())

    response = client.get(f"/auth/github/callback?code=code-abc&state={STATE}")

    assert response.status_code == 302
    assert SESSION_COOKIE_NAME in response.cookies

    with DatabaseSession(
        bind=postgres_session, join_transaction_mode="create_savepoint"
    ) as db:
        user = db.scalar(select(User).where(User.github_user_id == 43))
        assert user is not None

        repos = list(
            db.scalars(select(Repository).where(Repository.user_id == user.id))
        )
        assert len(repos) == 1
        assert repos[0].github_repo_id == 9001
        assert repos[0].name == "my-repo"
        assert repos[0].is_available is True

        sessions = db.scalar(
            select(func.count())
            .select_from(StoredSession)
            .where(StoredSession.user_id == user.id)
        )
        assert sessions == 1
