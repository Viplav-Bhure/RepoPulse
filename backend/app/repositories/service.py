"""Repository queries and business logic (task 1.11).

Pure database access and response mapping for the repository domain.
Does NOT call GitHub, refresh repositories, clone, or analyze code.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from app.database.models import Repository
from app.repositories.schemas import RepositoryResponse

logger = logging.getLogger(__name__)


def is_repository_empty(default_branch: str | None) -> bool:
    """Return True if default_branch is null, whitespace, or empty.

    Defined by task 1.11 requirements: a null default branch means
    empty/unsupported for analysis without creating a new database field.
    """
    return default_branch is None or not default_branch.strip()


def compute_repository_status(
    *,
    is_archived: bool,
    default_branch: str | None,
) -> tuple[bool, str, str, str | None, bool]:
    """Compute repository display and analysis eligibility status.

    Returns:
        (is_empty, status, display_status, status_message, can_analyze)
    """
    empty = is_repository_empty(default_branch)
    archived = bool(is_archived)

    if archived and empty:
        status = "archived"
        display_status = "Archived"
        status_message = "Repository is archived and empty."
    elif archived:
        status = "archived"
        display_status = "Archived"
        status_message = "Repository is archived."
    elif empty:
        status = "empty"
        display_status = "Empty"
        status_message = "Repository is empty."
    else:
        status = "active"
        display_status = "Active"
        status_message = None

    can_analyze = (not archived) and (not empty)
    return empty, status, display_status, status_message, can_analyze


def build_repository_response(repo: Repository) -> RepositoryResponse:
    """Convert a Repository ORM instance into a typed RepositoryResponse."""
    empty, status, display_status, status_message, can_analyze = (
        compute_repository_status(
            is_archived=repo.is_archived,
            default_branch=repo.default_branch,
        )
    )

    return RepositoryResponse(
        id=repo.id,
        github_repo_id=repo.github_repo_id,
        name=repo.name,
        owner=repo.owner,
        primary_language=repo.primary_language,
        github_updated_at=repo.github_updated_at,
        default_branch=repo.default_branch,
        is_fork=repo.is_fork,
        is_archived=repo.is_archived,
        is_available=repo.is_available,
        is_empty=empty,
        status=status,
        display_status=display_status,
        status_message=status_message,
        can_analyze=can_analyze,
        analyze_enabled=can_analyze,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )


def list_user_repositories(
    db: DatabaseSession,
    user_id: int,
) -> list[RepositoryResponse]:
    """Return all available repositories owned by *user_id*.

    Filtered by user_id and is_available=True.
    Ordered deterministically by name ascending, id ascending.
    """
    statement = (
        select(Repository)
        .where(
            Repository.user_id == user_id,
            Repository.is_available.is_(True),
        )
        .order_by(Repository.name.asc(), Repository.id.asc())
    )
    rows: Sequence[Repository] = db.scalars(statement).all()
    return [build_repository_response(row) for row in rows]
