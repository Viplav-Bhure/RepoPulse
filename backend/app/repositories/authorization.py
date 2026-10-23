"""Repository ownership authorization dependencies."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session as DatabaseSession

from app.auth.session import get_current_user
from app.database.models import Repository, User
from app.database.session import get_db

REPOSITORY_NOT_FOUND = "Repository not found."


def get_owned_repository(
    repo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    database_session: Annotated[DatabaseSession, Depends(get_db)],
) -> Repository:
    """Return a repository owned by the authenticated user or raise 404."""
    repository = database_session.get(Repository, repo_id)
    if repository is None or repository.user_id != current_user.id:
        raise HTTPException(status_code=404, detail=REPOSITORY_NOT_FOUND)
    return repository


def get_owned_file(
    file_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    database_session: Annotated[DatabaseSession, Depends(get_db)],
) -> NoReturn:
    """Reserve the file -> analysis -> repository -> user authorization contract."""
    raise NotImplementedError("File authorization is implemented in Phase 2.")


def get_owned_finding(
    finding_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    database_session: Annotated[DatabaseSession, Depends(get_db)],
) -> NoReturn:
    """Reserve the finding -> file -> analysis -> repository -> user contract."""
    raise NotImplementedError("Finding authorization is implemented in Phase 2.")
