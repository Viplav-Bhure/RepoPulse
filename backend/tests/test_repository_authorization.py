"""Tests for reusable repository ownership authorization."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session as DatabaseSession

from app.auth.session import SESSION_COOKIE_NAME, create_session
from app.database.models import Repository, User
from app.database.session import get_db
from app.repositories.authorization import (
    REPOSITORY_NOT_FOUND,
    get_owned_repository,
)


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
    is_available: bool = True,
) -> Repository:
    repository = Repository(
        user_id=user_id,
        github_repo_id=github_repo_id,
        name=name,
        owner="owner",
        default_branch="main",
        is_fork=False,
        is_archived=False,
        is_available=is_available,
        primary_language="Python",
        github_updated_at=datetime(2026, 10, 23, tzinfo=UTC),
    )
    db.add(repository)
    db.flush()
    return repository


def _app() -> FastAPI:
    application = FastAPI()

    @application.get("/repositories/{repo_id}")
    def get_repository_route(
        repository: Annotated[Repository, Depends(get_owned_repository)],
    ) -> dict[str, Any]:
        return {"id": repository.id, "name": repository.name}

    return application


def _login_user(
    db: DatabaseSession,
    client: TestClient,
    user_id: int,
) -> None:
    token = create_session(db, user_id)
    db.commit()
    client.cookies.set(SESSION_COOKIE_NAME, token.value)


@pytest.fixture
def authorization_client(
    postgres_session: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, DatabaseSession], None, None]:
    application = _app()

    def override_get_db() -> Generator[DatabaseSession, None, None]:
        with DatabaseSession(
            bind=postgres_session,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as db:
            yield db

    application.dependency_overrides[get_db] = override_get_db

    import app.github.client as github_client
    import app.repositories.sync as repository_sync

    def forbid_github_call(*args: object, **kwargs: object) -> None:
        pytest.fail("GitHub network call occurred during ownership authorization")

    monkeypatch.setattr(github_client, "list_repositories", forbid_github_call)
    monkeypatch.setattr(repository_sync, "refresh_repositories", forbid_github_call)
    monkeypatch.setattr(repository_sync, "sync_repositories", forbid_github_call)

    with TestClient(application, follow_redirects=False) as client:
        with DatabaseSession(
            bind=postgres_session,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as db:
            yield client, db


def test_owner_receives_repository(
    authorization_client: tuple[TestClient, DatabaseSession],
) -> None:
    client, db = authorization_client
    owner = _create_user(db, github_user_id=1201, username="owner")
    repository = _create_repo(
        db,
        user_id=owner.id,
        github_repo_id=2201,
        name="owned-repository",
    )
    _login_user(db, client, owner.id)

    response = client.get(f"/repositories/{repository.id}")

    assert response.status_code == 200
    assert response.json() == {"id": repository.id, "name": "owned-repository"}


def test_missing_repository_returns_404(
    authorization_client: tuple[TestClient, DatabaseSession],
) -> None:
    client, db = authorization_client
    owner = _create_user(db, github_user_id=1202, username="missing-owner")
    _login_user(db, client, owner.id)

    response = client.get("/repositories/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": REPOSITORY_NOT_FOUND}


def test_another_users_repository_returns_same_404(
    authorization_client: tuple[TestClient, DatabaseSession],
) -> None:
    client, db = authorization_client
    owner = _create_user(db, github_user_id=1203, username="alice")
    other_user = _create_user(db, github_user_id=1204, username="bob")
    repository = _create_repo(
        db,
        user_id=other_user.id,
        github_repo_id=2204,
        name="bob-repository",
    )
    _login_user(db, client, owner.id)

    response = client.get(f"/repositories/{repository.id}")

    assert response.status_code == 404
    assert response.json() == {"detail": REPOSITORY_NOT_FOUND}
    assert "bob-repository" not in response.text


def test_unauthenticated_request_returns_401(
    authorization_client: tuple[TestClient, DatabaseSession],
) -> None:
    client, db = authorization_client
    owner = _create_user(db, github_user_id=1205, username="unauthenticated")
    repository = _create_repo(
        db,
        user_id=owner.id,
        github_repo_id=2205,
        name="protected-repository",
    )

    response = client.get(f"/repositories/{repository.id}")

    assert response.status_code == 401
    assert "protected-repository" not in response.text


def test_unavailable_owned_repository_still_passes_ownership_check(
    authorization_client: tuple[TestClient, DatabaseSession],
) -> None:
    client, db = authorization_client
    owner = _create_user(db, github_user_id=1206, username="unavailable-owner")
    repository = _create_repo(
        db,
        user_id=owner.id,
        github_repo_id=2206,
        name="unavailable-repository",
        is_available=False,
    )
    _login_user(db, client, owner.id)

    response = client.get(f"/repositories/{repository.id}")

    assert response.status_code == 200
    assert response.json()["id"] == repository.id
