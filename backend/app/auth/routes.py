"""Temporary GitHub OAuth route orchestration."""

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DatabaseSession

from app.auth.csrf import require_trusted_origin
from app.auth.oauth import (
    STATE_LIFETIME_SECONDS,
    GitHubProfile,
    OAuthError,
    OAuthStateError,
    create_authorization_request,
    exchange_code_for_token,
    fetch_github_profile,
    validate_state_cookie,
)
from app.auth.session import (
    SESSION_COOKIE_NAME,
    SESSION_LIFETIME_SECONDS,
    SessionToken,
    create_session,
    get_current_user,
    revoke_session,
)
from app.config import settings
from app.database.models import User
from app.database.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])
STATE_COOKIE_NAME = "repopulse_oauth_state"
AUTHENTICATION_ERROR = "GitHub authentication could not be completed."


def _secure_cookie() -> bool:
    return urlsplit(settings.API_BASE_URL).scheme == "https"


def _valid_profile(profile: object) -> bool:
    return (
        isinstance(profile, GitHubProfile)
        and isinstance(profile.github_user_id, int)
        and not isinstance(profile.github_user_id, bool)
        and profile.github_user_id > 0
        and isinstance(profile.username, str)
        and bool(profile.username.strip())
        and len(profile.username) <= 255
        and (profile.email is None or isinstance(profile.email, str))
        and (profile.email is None or len(profile.email) <= 320)
        and (profile.email is None or "\r" not in profile.email)
        and (profile.email is None or "\n" not in profile.email)
    )


def _upsert_user(database_session: DatabaseSession, profile: GitHubProfile) -> User:
    statement = (
        insert(User)
        .values(
            github_user_id=profile.github_user_id,
            username=profile.username,
            email=profile.email,
        )
        .on_conflict_do_update(
            index_elements=[User.github_user_id],
            set_={"username": profile.username, "email": profile.email},
        )
        .returning(User)
    )
    user = database_session.scalar(statement)
    if user is None:
        raise RuntimeError("User persistence failed.")
    return user


def _set_session_cookie(response: Response, token: SessionToken) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token.value,
        max_age=SESSION_LIFETIME_SECONDS,
        path="/",
        secure=_secure_cookie(),
        httponly=True,
        samesite="lax",
    )


@router.get("/github/login")
def github_login() -> Response:
    try:
        authorization = create_authorization_request(
            client_id=settings.GITHUB_CLIENT_ID,
            api_base_url=settings.API_BASE_URL,
            session_secret=settings.SESSION_SECRET,
        )
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"detail": AUTHENTICATION_ERROR},
        )

    response = RedirectResponse(authorization.authorization_url, status_code=302)
    response.set_cookie(
        key=STATE_COOKIE_NAME,
        value=authorization.state_cookie,
        max_age=STATE_LIFETIME_SECONDS,
        path="/",
        secure=_secure_cookie(),
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/github/callback")
def github_callback(
    request: Request,
    database_session: Annotated[DatabaseSession, Depends(get_db)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    response: JSONResponse
    try:
        validated_state = validate_state_cookie(
            state_cookie=request.cookies.get(STATE_COOKIE_NAME),
            returned_state=state,
            session_secret=settings.SESSION_SECRET,
        )
        if error is not None or not code:
            response = JSONResponse(
                status_code=400,
                content={"detail": AUTHENTICATION_ERROR},
            )
        else:
            token = exchange_code_for_token(
                code=code,
                code_verifier=validated_state.code_verifier,
                client_id=settings.GITHUB_CLIENT_ID,
                client_secret=settings.GITHUB_CLIENT_SECRET,
                api_base_url=settings.API_BASE_URL,
            )
            profile = fetch_github_profile(token)
            if not _valid_profile(profile):
                raise OAuthError()
            user = _upsert_user(database_session, profile)
            session_token = create_session(database_session, user.id)
            database_session.commit()
            response = RedirectResponse(
                url=f"{settings.FRONTEND_URL.rstrip('/')}/",
                status_code=302,
            )
            _set_session_cookie(response, session_token)
    except OAuthStateError:
        database_session.rollback()
        response = JSONResponse(
            status_code=400,
            content={"detail": AUTHENTICATION_ERROR},
        )
    except OAuthError:
        database_session.rollback()
        response = JSONResponse(
            status_code=502,
            content={"detail": AUTHENTICATION_ERROR},
        )
    except Exception:
        database_session.rollback()
        response = JSONResponse(
            status_code=500,
            content={"detail": AUTHENTICATION_ERROR},
        )

    response.delete_cookie(
        key=STATE_COOKIE_NAME,
        path="/",
        secure=_secure_cookie(),
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/me")
def auth_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    return {
        "id": current_user.id,
        "github_user_id": current_user.github_user_id,
        "username": current_user.username,
        "email": current_user.email,
    }


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    _origin_check: Annotated[None, Depends(require_trusted_origin)],
    database_session: Annotated[DatabaseSession, Depends(get_db)],
) -> Response:
    revoke_session(database_session, request.cookies.get(SESSION_COOKIE_NAME))
    response = Response(status_code=204)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=_secure_cookie(),
        httponly=True,
        samesite="lax",
    )
    return response
