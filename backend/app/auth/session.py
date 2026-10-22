"""Opaque PostgreSQL-backed browser sessions."""

import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DatabaseSession

from app.database.models import Session as StoredSession
from app.database.models import User
from app.database.session import get_db

SESSION_COOKIE_NAME = "repopulse_session"
SESSION_LIFETIME = timedelta(days=7)
SESSION_LIFETIME_SECONDS = int(SESSION_LIFETIME.total_seconds())
SESSION_TOKEN_BYTES = 32
SESSION_TOKEN_LENGTH = 43
AUTHENTICATION_REQUIRED = "Authentication required."
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, repr=False)
class SessionToken:
    value: str = field(repr=False)

    def __repr__(self) -> str:
        return "SessionToken(<redacted>)"


def _current_time(now: datetime | None) -> datetime:
    return datetime.now(UTC) if now is None else now


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _is_valid_token(token: object) -> bool:
    return (
        isinstance(token, str)
        and len(token) == SESSION_TOKEN_LENGTH
        and token.isascii()
        and all(character.isalnum() or character in "_-" for character in token)
    )


def _delete_expired_sessions(database_session: DatabaseSession, now: datetime) -> None:
    database_session.execute(
        delete(StoredSession).where(StoredSession.expires_at <= now)
    )


def create_session(
    database_session: DatabaseSession,
    user_id: int,
    *,
    now: datetime | None = None,
) -> SessionToken:
    issued_at = _current_time(now)
    _delete_expired_sessions(database_session, issued_at)
    raw_token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    database_session.add(
        StoredSession(
            user_id=user_id,
            token_hash=_token_digest(raw_token),
            expires_at=issued_at + SESSION_LIFETIME,
        )
    )
    database_session.flush()
    return SessionToken(raw_token)


def get_session_user(
    database_session: DatabaseSession,
    token: object,
    *,
    now: datetime | None = None,
) -> User | None:
    current_time = _current_time(now)
    _delete_expired_sessions(database_session, current_time)
    if not _is_valid_token(token):
        database_session.commit()
        return None

    stored_session = database_session.scalar(
        select(StoredSession).where(StoredSession.token_hash == _token_digest(token))
    )
    if stored_session is None or stored_session.expires_at <= current_time:
        if stored_session is not None:
            database_session.delete(stored_session)
        database_session.commit()
        return None

    user = database_session.get(User, stored_session.user_id)
    database_session.commit()
    return user


def revoke_session(
    database_session: DatabaseSession,
    token: object,
    *,
    now: datetime | None = None,
) -> None:
    _delete_expired_sessions(database_session, _current_time(now))
    if _is_valid_token(token):
        stored_session = database_session.scalar(
            select(StoredSession).where(
                StoredSession.token_hash == _token_digest(token)
            )
        )
        if stored_session is not None:
            database_session.delete(stored_session)
    database_session.commit()


def get_current_user(
    request: Request,
    database_session: Annotated[DatabaseSession, Depends(get_db)],
) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = get_session_user(database_session, token)
    if user is None:
        logger.warning("session_authentication_failed reason=missing_or_invalid")
        raise HTTPException(status_code=401, detail=AUTHENTICATION_REQUIRED)
    return user
