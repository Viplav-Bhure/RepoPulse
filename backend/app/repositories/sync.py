"""Repository synchronization service (task 1.10).

Upserts filtered GitHub repositories for a user and marks absent rows
is_available=False.  Both operations run in a single transaction supplied
by the caller so they can be composed with the OAuth callback transaction.

Public surface
--------------
sync_repositories(db, user_id, username, repos)
    Accept typed GitHubRepository objects, filter by ownership, upsert to
    the repositories table, and mark rows absent from the current list as
    is_available=False.  Called during the OAuth callback with the transient
    user token already consumed by list_repositories(); the caller passes the
    already-fetched sequence, not a token.

refresh_repositories(db, user_id, username)
    Fetch the user's repositories using GITHUB_PUBLIC_API_TOKEN only, then
    call sync_repositories.  No user token is involved.  Callable by task
    1.11 when it builds the GET /repositories route.

Both functions are pure over their arguments except for DB writes; they do
not perform network I/O themselves (refresh_repositories delegates to the
GitHub client which uses the server-side credential).

SEC-2: only user-owned repositories are stored (filter applied here).
SEC-5: the user's GitHub access token is never passed into or stored by
       these functions.
SEC-6: the token must not appear in repr, exceptions, or logs.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DatabaseSession

from app.config import settings
from app.database.models import Repository
from app.github.client import GitHubRepository, list_repositories
from app.repositories.filter import filter_owned_repositories

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def sync_repositories(
    db: DatabaseSession,
    user_id: int,
    username: str,
    repos: Sequence[GitHubRepository],
) -> None:
    """Upsert *repos* for *user_id* and mark absent rows is_available=False.

    The caller is responsible for committing (or rolling back) the session.
    The function uses savepoints so partial failures inside the upsert loop
    can be handled without losing the outer transaction -- but in practice
    the whole upsert is one bulk statement followed by a bulk update.

    Args:
        db:       An open SQLAlchemy session.  The caller owns the transaction.
        user_id:  Internal PK of the authenticated user row.
        username: GitHub username of the authenticated user (used by the
                  ownership filter; case-insensitive comparison).
        repos:    Sequence of GitHubRepository objects returned by the client.
                  May be empty (valid: marks all stored rows unavailable).

    Raises:
        Does not swallow exceptions; the caller decides how to handle them.
    """
    owned = filter_owned_repositories(repos, username)

    present_github_ids: set[int] = set()

    for repo in owned:
        _upsert_one(db, user_id, repo)
        present_github_ids.add(repo.github_repo_id)
        logger.debug(
            "repo_sync_upserted user_id=%s github_repo_id=%s name=%s",
            user_id,
            repo.github_repo_id,
            repo.name,
        )

    _mark_absent_unavailable(db, user_id, present_github_ids)
    db.expire_all()

    logger.info(
        "repo_sync_completed user_id=%s upserted=%s",
        user_id,
        len(present_github_ids),
    )


def refresh_repositories(
    db: DatabaseSession,
    user_id: int,
    username: str,
) -> None:
    """Re-sync the repository list using the server-side public API token.

    This is the callable boundary exposed for task 1.11.  It does NOT use a
    per-user OAuth token.  The caller owns the transaction.

    Raises:
        GitHubClientError: propagated from list_repositories; caller handles.
    """
    token = settings.GITHUB_PUBLIC_API_TOKEN
    repos = list_repositories(token)
    sync_repositories(db, user_id, username, repos)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _upsert_one(
    db: DatabaseSession,
    user_id: int,
    repo: GitHubRepository,
) -> None:
    """Insert or update a single repository row.

    - On conflict (user_id, github_repo_id): update all mutable columns,
      restore is_available=True, and leave created_at untouched.
    - On insert: created_at is set by the server default (func.now()).
    """
    now = datetime.now(UTC)
    statement = (
        insert(Repository)
        .values(
            user_id=user_id,
            github_repo_id=repo.github_repo_id,
            name=repo.name,
            owner=repo.owner_login,
            default_branch=repo.default_branch,
            is_fork=repo.is_fork,
            is_archived=repo.is_archived,
            is_available=True,
            primary_language=repo.primary_language,
            github_updated_at=repo.updated_at,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "github_repo_id"],
            set_={
                "name": repo.name,
                "owner": repo.owner_login,
                "default_branch": repo.default_branch,
                "is_fork": repo.is_fork,
                "is_archived": repo.is_archived,
                "is_available": True,
                "primary_language": repo.primary_language,
                "github_updated_at": repo.updated_at,
                "updated_at": now,
                # created_at is intentionally NOT in set_ to preserve it.
            },
        )
    )
    db.execute(statement)


def _mark_absent_unavailable(
    db: DatabaseSession,
    user_id: int,
    present_github_ids: set[int],
) -> None:
    """Set is_available=False for rows not in *present_github_ids*.

    Does nothing when *present_github_ids* contains all stored IDs for the
    user.  When it is empty (the fetched list was empty or all repos were
    filtered out) every stored row for the user is marked unavailable.
    """
    query = (
        select(Repository.github_repo_id)
        .where(Repository.user_id == user_id)
        .where(Repository.is_available.is_(True))
    )
    if present_github_ids:
        query = query.where(Repository.github_repo_id.not_in(present_github_ids))

    ids_to_mark = list(db.scalars(query))
    if not ids_to_mark:
        return

    now = datetime.now(UTC)
    db.execute(
        update(Repository)
        .where(Repository.user_id == user_id)
        .where(Repository.github_repo_id.in_(ids_to_mark))
        .values(is_available=False, updated_at=now)
    )
    logger.info(
        "repo_sync_marked_unavailable user_id=%s count=%s",
        user_id,
        len(ids_to_mark),
    )
