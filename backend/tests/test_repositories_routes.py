"""Tests for the repository listing route and service (task 1.11).

Coverage:
- unauthenticated request returns 401
- authenticated user receives only their own available repositories
- unavailable rows (is_available=False) are excluded
- another user's rows are excluded
- another user's repository IDs are never exposed
- archived repository has explanatory status and Analyze disabled
- empty repository (null default branch) has explanatory status and Analyze disabled
- archived and empty repository has explanatory status and Analyze disabled
- normal supported repository has Analyze enabled
- user-owned forks are returned normally
- response schema and datetime serialization are correct
- no GitHub network call occurs
- empty list returned when user has no repositories
- trailing slash is supported transparently
- status computation unit logic
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session as DatabaseSession

from app.auth.session import SESSION_COOKIE_NAME, create_session
from app.database.models import Repository, User
from app.repositories.service import (
    compute_repository_status,
    is_repository_empty,
)

_UPDATED_AT = datetime(2026, 10, 20, 14, 30, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def _client() -> TestClient:
    from app.main import app

    return TestClient(app, follow_redirects=False)


def _create_user(
    db: DatabaseSession,
    *,
    github_user_id: int,
    username: str,
) -> User:
    user = User(
        github_user_id=github_user_id,
        username=username,
        email=f"{username}@example.test",
    )
    db.add(user)
    db.flush()
    return user


def _create_repo(
    db: DatabaseSession,
    *,
    user_id: int,
    github_repo_id: int,
    name: str,
    owner: str,
    default_branch: str | None = "main",
    is_fork: bool = False,
    is_archived: bool = False,
    is_available: bool = True,
    primary_language: str | None = "Python",
    github_updated_at: datetime | None = _UPDATED_AT,
) -> Repository:
    repo = Repository(
        user_id=user_id,
        github_repo_id=github_repo_id,
        name=name,
        owner=owner,
        default_branch=default_branch,
        is_fork=is_fork,
        is_archived=is_archived,
        is_available=is_available,
        primary_language=primary_language,
        github_updated_at=github_updated_at,
    )
    db.add(repo)
    db.flush()
    return repo


def _login_user(db: DatabaseSession, client: TestClient, user_id: int) -> str:
    token = create_session(db, user_id)
    raw_token = token.value
    db.commit()
    client.cookies.set(SESSION_COOKIE_NAME, raw_token)
    return raw_token


# ---------------------------------------------------------------------------
# Pure unit tests for status logic
# ---------------------------------------------------------------------------


def test_is_repository_empty() -> None:
    assert is_repository_empty(None) is True
    assert is_repository_empty("") is True
    assert is_repository_empty("   ") is True
    assert is_repository_empty("main") is False
    assert is_repository_empty("master") is False


def test_compute_repository_status_normal() -> None:
    empty, status, display, message, can_analyze = compute_repository_status(
        is_archived=False,
        default_branch="main",
    )
    assert empty is False
    assert status == "active"
    assert display == "Active"
    assert message is None
    assert can_analyze is True


def test_compute_repository_status_archived() -> None:
    empty, status, display, message, can_analyze = compute_repository_status(
        is_archived=True,
        default_branch="main",
    )
    assert empty is False
    assert status == "archived"
    assert display == "Archived"
    assert message == "Repository is archived."
    assert can_analyze is False


def test_compute_repository_status_empty() -> None:
    empty, status, display, message, can_analyze = compute_repository_status(
        is_archived=False,
        default_branch=None,
    )
    assert empty is True
    assert status == "empty"
    assert display == "Empty"
    assert message == "Repository is empty."
    assert can_analyze is False


def test_compute_repository_status_archived_and_empty() -> None:
    empty, status, display, message, can_analyze = compute_repository_status(
        is_archived=True,
        default_branch=None,
    )
    assert empty is True
    assert status == "archived"
    assert display == "Archived"
    assert message == "Repository is archived and empty."
    assert can_analyze is False


# ---------------------------------------------------------------------------
# API Route Tests (PostgreSQL backed)
# ---------------------------------------------------------------------------


def test_get_repositories_unauthenticated_returns_401(
    postgres_session: Connection,
) -> None:
    client = _client()
    response = client.get("/repositories")
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


def test_get_repositories_invalid_session_returns_401(
    postgres_session: Connection,
) -> None:
    client = _client()
    client.cookies.set(SESSION_COOKIE_NAME, "invalid-session-token-not-found")
    response = client.get("/repositories")
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


def test_get_repositories_empty_list_when_no_repos(
    postgres_session: Connection,
) -> None:
    client = _client()
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        user = _create_user(db, github_user_id=1001, username="empty_alice")
        _login_user(db, client, user.id)

    response = client.get("/repositories")
    assert response.status_code == 200
    assert response.json() == []


def test_get_repositories_returns_only_own_available_repositories(
    postgres_session: Connection,
) -> None:
    client = _client()
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        alice = _create_user(db, github_user_id=1002, username="alice_user")
        bob = _create_user(db, github_user_id=1003, username="bob_user")

        # Alice's available repositories
        repo_a = _create_repo(
            db,
            user_id=alice.id,
            github_repo_id=2001,
            name="alpha-repo",
            owner="alice_user",
        )
        repo_b = _create_repo(
            db,
            user_id=alice.id,
            github_repo_id=2002,
            name="beta-repo",
            owner="alice_user",
        )

        # Alice's unavailable repository (should be excluded)
        _create_repo(
            db,
            user_id=alice.id,
            github_repo_id=2003,
            name="gamma-unavailable",
            owner="alice_user",
            is_available=False,
        )

        # Bob's repository (should be excluded)
        bob_repo = _create_repo(
            db,
            user_id=bob.id,
            github_repo_id=2004,
            name="bob-private-work",
            owner="bob_user",
            is_available=True,
        )

        repo_a_id = repo_a.id
        repo_b_id = repo_b.id
        bob_repo_id = bob_repo.id
        _login_user(db, client, alice.id)

    response = client.get("/repositories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    repo_names = [r["name"] for r in data]
    assert repo_names == ["alpha-repo", "beta-repo"]

    returned_ids = {r["id"] for r in data}
    assert repo_a_id in returned_ids
    assert repo_b_id in returned_ids
    assert bob_repo_id not in returned_ids

    returned_gh_ids = {r["github_repo_id"] for r in data}
    assert 2004 not in returned_gh_ids

    # Verify Bob's name, username, and repo never appear anywhere in the response text
    assert "bob-private-work" not in response.text
    assert "bob_user" not in response.text
    assert "gamma-unavailable" not in response.text


def test_get_repositories_archived_repo_status_and_disabled_analyze(
    postgres_session: Connection,
) -> None:
    client = _client()
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        user = _create_user(db, github_user_id=1004, username="archivist")
        repo = _create_repo(
            db,
            user_id=user.id,
            github_repo_id=2010,
            name="legacy-project",
            owner="archivist",
            default_branch="master",
            is_archived=True,
            primary_language="Python",
        )
        repo_id = repo.id
        _login_user(db, client, user.id)

    response = client.get("/repositories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    item = data[0]
    assert item["id"] == repo_id
    assert item["name"] == "legacy-project"
    assert item["is_archived"] is True
    assert item["is_empty"] is False
    assert item["can_analyze"] is False
    assert item["analyze_enabled"] is False
    assert item["status"] == "archived"
    assert item["display_status"] == "Archived"
    assert item["status_message"] == "Repository is archived."


def test_get_repositories_empty_repo_status_and_disabled_analyze(
    postgres_session: Connection,
) -> None:
    client = _client()
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        user = _create_user(db, github_user_id=1005, username="starter")
        repo = _create_repo(
            db,
            user_id=user.id,
            github_repo_id=2020,
            name="empty-workspace",
            owner="starter",
            default_branch=None,
            is_archived=False,
            primary_language=None,
        )
        repo_id = repo.id
        _login_user(db, client, user.id)

    response = client.get("/repositories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    item = data[0]
    assert item["id"] == repo_id
    assert item["name"] == "empty-workspace"
    assert item["default_branch"] is None
    assert item["is_archived"] is False
    assert item["is_empty"] is True
    assert item["can_analyze"] is False
    assert item["analyze_enabled"] is False
    assert item["status"] == "empty"
    assert item["display_status"] == "Empty"
    assert item["status_message"] == "Repository is empty."


def test_get_repositories_archived_and_empty_repo_status(
    postgres_session: Connection,
) -> None:
    client = _client()
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        user = _create_user(db, github_user_id=1006, username="cleanup_user")
        _create_repo(
            db,
            user_id=user.id,
            github_repo_id=2030,
            name="abandoned-empty",
            owner="cleanup_user",
            default_branch="",
            is_archived=True,
            primary_language=None,
        )
        _login_user(db, client, user.id)

    response = client.get("/repositories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    item = data[0]
    assert item["is_archived"] is True
    assert item["is_empty"] is True
    assert item["can_analyze"] is False
    assert item["analyze_enabled"] is False
    assert item["status"] == "archived"
    assert item["display_status"] == "Archived"
    assert item["status_message"] == "Repository is archived and empty."


def test_get_repositories_normal_supported_has_analyze_enabled(
    postgres_session: Connection,
) -> None:
    client = _client()
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        user = _create_user(db, github_user_id=1007, username="active_dev")
        repo = _create_repo(
            db,
            user_id=user.id,
            github_repo_id=2040,
            name="repopulse-core",
            owner="active_dev",
            default_branch="main",
            is_archived=False,
            primary_language="Python",
        )
        repo_id = repo.id
        _login_user(db, client, user.id)

    response = client.get("/repositories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    item = data[0]
    assert item["id"] == repo_id
    assert item["name"] == "repopulse-core"
    assert item["is_archived"] is False
    assert item["is_empty"] is False
    assert item["can_analyze"] is True
    assert item["analyze_enabled"] is True
    assert item["status"] == "active"
    assert item["display_status"] == "Active"
    assert item["status_message"] is None


def test_get_repositories_fork_returned_normally(
    postgres_session: Connection,
) -> None:
    client = _client()
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        user = _create_user(db, github_user_id=1008, username="forker")
        repo = _create_repo(
            db,
            user_id=user.id,
            github_repo_id=2050,
            name="forked-repo",
            owner="forker",
            default_branch="main",
            is_fork=True,
            is_archived=False,
            primary_language="TypeScript",
        )
        repo_id = repo.id
        _login_user(db, client, user.id)

    response = client.get("/repositories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    item = data[0]
    assert item["id"] == repo_id
    assert item["name"] == "forked-repo"
    assert item["is_fork"] is True
    assert item["is_archived"] is False
    assert item["is_empty"] is False
    assert item["can_analyze"] is True
    assert item["analyze_enabled"] is True


def test_get_repositories_schema_and_datetime_serialization(
    postgres_session: Connection,
) -> None:
    client = _client()
    test_dt = datetime(2026, 10, 22, 18, 0, 0, tzinfo=UTC)
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        user = _create_user(db, github_user_id=1009, username="schema_tester")
        repo = _create_repo(
            db,
            user_id=user.id,
            github_repo_id=2060,
            name="full-schema-repo",
            owner="schema_tester",
            default_branch="develop",
            is_fork=False,
            is_archived=False,
            primary_language="JavaScript",
            github_updated_at=test_dt,
        )
        repo_id = repo.id
        _login_user(db, client, user.id)

    response = client.get("/repositories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    item: dict[str, Any] = data[0]
    required_keys = {
        "id",
        "name",
        "owner",
        "primary_language",
        "github_updated_at",
        "default_branch",
        "is_fork",
        "is_archived",
        "is_available",
        "is_empty",
        "status",
        "display_status",
        "status_message",
        "can_analyze",
        "analyze_enabled",
    }
    assert required_keys.issubset(item.keys())

    assert item["id"] == repo_id
    assert item["name"] == "full-schema-repo"
    assert item["owner"] == "schema_tester"
    assert item["primary_language"] == "JavaScript"
    assert item["default_branch"] == "develop"
    assert item["is_fork"] is False
    assert item["is_archived"] is False
    assert item["is_available"] is True
    assert item["is_empty"] is False
    assert item["status"] == "active"
    assert item["display_status"] == "Active"
    assert item["can_analyze"] is True
    assert item["analyze_enabled"] is True

    # Datetime serialization check
    assert isinstance(item["github_updated_at"], str)
    parsed_dt = datetime.fromisoformat(item["github_updated_at"])
    assert parsed_dt == test_dt


def test_get_repositories_no_github_network_call(
    postgres_session: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify GET /repositories reads purely from DB without calling GitHub."""
    import app.github.client as gh_client
    import app.repositories.sync as repo_sync

    def forbid_call(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Network call to GitHub occurred during GET /repositories")

    monkeypatch.setattr(gh_client, "list_repositories", forbid_call)
    monkeypatch.setattr(repo_sync, "refresh_repositories", forbid_call)
    monkeypatch.setattr(repo_sync, "sync_repositories", forbid_call)

    client = _client()
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        user = _create_user(db, github_user_id=1010, username="offline_user")
        _create_repo(
            db,
            user_id=user.id,
            github_repo_id=2070,
            name="local-cached-repo",
            owner="offline_user",
        )
        _login_user(db, client, user.id)

    response = client.get("/repositories")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_repositories_trailing_slash_support(
    postgres_session: Connection,
) -> None:
    client = _client()
    with DatabaseSession(
        bind=postgres_session,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        user = _create_user(db, github_user_id=1011, username="slash_user")
        _login_user(db, client, user.id)

    # Test both /repositories and /repositories/
    resp_no_slash = client.get("/repositories")
    assert resp_no_slash.status_code == 200

    resp_slash = client.get("/repositories/")
    assert resp_slash.status_code == 200
