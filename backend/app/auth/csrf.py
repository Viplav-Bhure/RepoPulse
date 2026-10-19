"""Origin checks for cookie-authenticated state-changing requests."""

from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from app.auth.session import SESSION_COOKIE_NAME
from app.config import settings


def frontend_origin(frontend_url: str) -> str:
    parsed = urlsplit(frontend_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or "*" in parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("FRONTEND_URL must be an absolute HTTP(S) URL.")
    return f"{parsed.scheme}://{parsed.netloc}"


def require_trusted_origin(request: Request) -> None:
    if not request.cookies.get(SESSION_COOKIE_NAME):
        return

    origins = request.headers.getlist("origin")
    if len(origins) != 1 or origins[0] != frontend_origin(settings.FRONTEND_URL):
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")
