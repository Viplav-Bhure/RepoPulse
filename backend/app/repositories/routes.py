"""Repository route endpoints (task 1.11).

Provides GET /repositories for listing the authenticated user's own public
repositories with display status and analysis eligibility.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DatabaseSession

from app.auth.session import get_current_user
from app.database.models import User
from app.database.session import get_db
from app.repositories.schemas import RepositoryResponse
from app.repositories.service import list_user_repositories

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("", response_model=list[RepositoryResponse])
@router.get("/", response_model=list[RepositoryResponse], include_in_schema=False)
def list_repositories_route(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[DatabaseSession, Depends(get_db)],
) -> list[RepositoryResponse]:
    """List public repositories owned by the authenticated user."""
    return list_user_repositories(db, current_user.id)
