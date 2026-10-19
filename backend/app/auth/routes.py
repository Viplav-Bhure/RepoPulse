"""Temporary GitHub OAuth route orchestration."""

from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

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
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
STATE_COOKIE_NAME = "repopulse_oauth_state"
AUTHENTICATION_ERROR = "GitHub authentication could not be completed."
HANDOFF_PENDING = "OAuth verified; session creation is deferred to task 1.5."


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
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> JSONResponse:
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
            response = JSONResponse(
                status_code=501,
                content={"detail": HANDOFF_PENDING},
            )
    except OAuthStateError:
        response = JSONResponse(
            status_code=400,
            content={"detail": AUTHENTICATION_ERROR},
        )
    except OAuthError:
        response = JSONResponse(
            status_code=502,
            content={"detail": AUTHENTICATION_ERROR},
        )
    except Exception:
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
