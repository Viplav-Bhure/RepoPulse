"""GitHub OAuth authorization-code helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
GITHUB_API_VERSION = "2026-03-10"
STATE_LIFETIME_SECONDS = 600
HTTP_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 1_048_576
MAX_STATE_COOKIE_BYTES = 2048
CALLBACK_PATH = "/auth/github/callback"


class OAuthError(Exception):
    """Base class for OAuth failures with safe, fixed messages."""


class OAuthConfigurationError(OAuthError):
    def __init__(self) -> None:
        super().__init__("OAuth configuration is invalid.")


class OAuthStateError(OAuthError):
    def __init__(self) -> None:
        super().__init__("OAuth state validation failed.")


class OAuthTimeoutError(OAuthError):
    def __init__(self) -> None:
        super().__init__("GitHub request timed out.")


class OAuthRedirectError(OAuthError):
    def __init__(self) -> None:
        super().__init__("GitHub OAuth redirects are not accepted.")


class OAuthTransportError(OAuthError):
    def __init__(self) -> None:
        super().__init__("GitHub request failed.")


class OAuthProviderError(OAuthError):
    def __init__(self) -> None:
        super().__init__("GitHub rejected the OAuth request.")


class OAuthResponseError(OAuthError):
    def __init__(self) -> None:
        super().__init__("GitHub returned an invalid response.")


@dataclass(frozen=True, slots=True, repr=False)
class OAuthAuthorizationRequest:
    authorization_url: str = field(repr=False)
    state_cookie: str = field(repr=False)

    def __repr__(self) -> str:
        return "OAuthAuthorizationRequest(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ValidatedOAuthState:
    state: str = field(repr=False)
    code_verifier: str = field(repr=False)

    def __repr__(self) -> str:
        return "ValidatedOAuthState(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class OAuthAccessToken:
    access_token: str = field(repr=False)

    def __repr__(self) -> str:
        return "OAuthAccessToken(<redacted>)"


@dataclass(frozen=True, slots=True)
class GitHubProfile:
    github_user_id: int
    username: str
    email: str | None


@dataclass(frozen=True, slots=True, repr=False)
class HttpRequest:
    method: str
    url: str
    headers: dict[str, str] = field(repr=False)
    body: bytes | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        return f"HttpRequest(method={self.method!r}, <sensitive fields redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class HttpResponse:
    status: int
    body: bytes = field(repr=False)

    def __repr__(self) -> str:
        return f"HttpResponse(status={self.status}, body=<redacted>)"


class OAuthTransport(Protocol):
    def send(self, request: HttpRequest, timeout: float) -> HttpResponse: ...


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        raise OAuthRedirectError()


class UrllibTransport:
    """Small urllib transport that never follows HTTP redirects."""

    def send(self, request: HttpRequest, timeout: float) -> HttpResponse:
        urllib_request = urllib.request.Request(
            request.url,
            data=request.body,
            headers=request.headers,
            method=request.method,
        )
        opener = urllib.request.build_opener(_RejectRedirectHandler())
        try:
            with opener.open(urllib_request, timeout=timeout) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise OAuthResponseError()
                return HttpResponse(status=response.status, body=body)
        except (OAuthRedirectError, OAuthResponseError):
            raise
        except urllib.error.HTTPError as error:
            try:
                body = error.read(MAX_RESPONSE_BYTES + 1)
            except Exception:
                body = b""
            return HttpResponse(status=error.code, body=body)
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise OAuthTimeoutError() from None
            raise OAuthTransportError() from None
        except TimeoutError:
            raise OAuthTimeoutError() from None
        except Exception:
            raise OAuthTransportError() from None


def create_authorization_request(
    *,
    client_id: str,
    api_base_url: str,
    session_secret: str,
    now: int | None = None,
) -> OAuthAuthorizationRequest:
    """Create the GitHub redirect URL and signed state-cookie value."""
    if not client_id or not session_secret:
        raise OAuthConfigurationError()
    callback_uri = _callback_uri(api_base_url)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    issued_at = int(time.time()) if now is None else now
    state_cookie = serialize_state_cookie(
        state=state,
        code_verifier=verifier,
        session_secret=session_secret,
        issued_at=issued_at,
    )
    challenge = _pkce_challenge(verifier)
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": callback_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return OAuthAuthorizationRequest(
        authorization_url=f"{AUTHORIZE_URL}?{query}",
        state_cookie=state_cookie,
    )


def serialize_state_cookie(
    *, state: str, code_verifier: str, session_secret: str, issued_at: int
) -> str:
    """Serialize and HMAC-sign a state/verifier envelope for the browser cookie."""
    if (
        not _valid_state(state)
        or not _valid_verifier(code_verifier)
        or not session_secret
        or isinstance(issued_at, bool)
        or not isinstance(issued_at, int)
        or issued_at < 0
    ):
        raise OAuthStateError()
    payload = json.dumps(
        {"v": 1, "state": state, "verifier": code_verifier, "iat": issued_at},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    encoded_payload = _base64url_encode(payload)
    signed_value = f"v1.{encoded_payload}"
    signature = hmac.new(
        session_secret.encode("utf-8"), signed_value.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{signed_value}.{_base64url_encode(signature)}"


def validate_state_cookie(
    *,
    state_cookie: str | None,
    returned_state: str | None,
    session_secret: str,
    now: int | None = None,
) -> ValidatedOAuthState:
    """Verify signature, expiry, and browser-returned state before code exchange."""
    if (
        not isinstance(state_cookie, str)
        or not state_cookie
        or len(state_cookie) > MAX_STATE_COOKIE_BYTES
        or not isinstance(returned_state, str)
        or not returned_state
        or not isinstance(session_secret, str)
        or not session_secret
    ):
        raise OAuthStateError()
    if not _valid_state(returned_state):
        raise OAuthStateError()

    pieces = state_cookie.split(".")
    if len(pieces) != 3 or pieces[0] != "v1":
        raise OAuthStateError()
    _, encoded_payload, encoded_signature = pieces
    try:
        payload_bytes = _base64url_decode(encoded_payload)
        signature = _base64url_decode(encoded_signature)
    except (ValueError, TypeError):
        raise OAuthStateError() from None

    signed_value = f"v1.{encoded_payload}".encode("ascii", errors="strict")
    expected_signature = hmac.new(
        session_secret.encode("utf-8"), signed_value, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise OAuthStateError()

    try:
        payload = json.loads(payload_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise OAuthStateError() from None
    if not isinstance(payload, dict) or set(payload) != {
        "v",
        "state",
        "verifier",
        "iat",
    }:
        raise OAuthStateError()
    state = payload["state"]
    verifier = payload["verifier"]
    issued_at = payload["iat"]
    if (
        payload["v"] != 1
        or isinstance(payload["v"], bool)
        or not isinstance(state, str)
        or not isinstance(verifier, str)
        or isinstance(issued_at, bool)
        or not isinstance(issued_at, int)
        or not _valid_state(state)
        or not _valid_verifier(verifier)
        or not hmac.compare_digest(state, returned_state)
    ):
        raise OAuthStateError()

    current_time = int(time.time()) if now is None else now
    if (
        isinstance(current_time, bool)
        or not isinstance(current_time, int)
        or current_time < issued_at
        or current_time - issued_at >= STATE_LIFETIME_SECONDS
    ):
        raise OAuthStateError()
    return ValidatedOAuthState(state=state, code_verifier=verifier)


def exchange_code_for_token(
    *,
    code: str,
    code_verifier: str,
    client_id: str,
    client_secret: str,
    api_base_url: str,
    transport: OAuthTransport | None = None,
) -> OAuthAccessToken:
    """Exchange a validated authorization code without exposing the token."""
    if not all((code, client_id, client_secret, api_base_url)) or not _valid_verifier(
        code_verifier
    ):
        raise OAuthConfigurationError()
    callback_uri = _callback_uri(api_base_url)
    body = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": callback_uri,
            "code_verifier": code_verifier,
        }
    ).encode("ascii")
    request = HttpRequest(
        method="POST",
        url=TOKEN_URL,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "RepoPulse",
        },
        body=body,
    )
    payload = _request_json(request, transport)
    access_token = payload.get("access_token")
    token_type = payload.get("token_type")
    if (
        not isinstance(access_token, str)
        or not access_token
        or not isinstance(token_type, str)
        or token_type.lower() != "bearer"
    ):
        raise OAuthResponseError()
    return OAuthAccessToken(access_token=access_token)


def fetch_github_profile(
    access_token: OAuthAccessToken,
    *,
    transport: OAuthTransport | None = None,
) -> GitHubProfile:
    """Fetch and validate the authenticated user's public GitHub profile."""
    request = HttpRequest(
        method="GET",
        url=USER_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token.access_token}",
            "User-Agent": "RepoPulse",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
    )
    payload = _request_json(request, transport)
    user_id = payload.get("id")
    username = payload.get("login")
    email = payload.get("email")
    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id <= 0
        or not isinstance(username, str)
        or not username.strip()
        or len(username) > 255
        or "email" not in payload
        or (email is not None and not isinstance(email, str))
        or (
            isinstance(email, str)
            and (len(email) > 320 or "\r" in email or "\n" in email)
        )
    ):
        raise OAuthResponseError()
    return GitHubProfile(github_user_id=user_id, username=username, email=email)


def _request_json(
    request: HttpRequest, transport: OAuthTransport | None
) -> dict[str, object]:
    selected_transport = transport if transport is not None else UrllibTransport()
    try:
        response = selected_transport.send(request, HTTP_TIMEOUT_SECONDS)
    except (
        OAuthTimeoutError,
        OAuthRedirectError,
        OAuthTransportError,
        OAuthResponseError,
        OAuthProviderError,
    ):
        raise
    except TimeoutError:
        raise OAuthTimeoutError() from None
    except Exception:
        raise OAuthTransportError() from None
    if (
        not isinstance(response, HttpResponse)
        or isinstance(response.status, bool)
        or not isinstance(response.status, int)
        or not isinstance(response.body, bytes)
    ):
        raise OAuthTransportError()
    if 300 <= response.status < 400:
        raise OAuthRedirectError()
    if not 200 <= response.status < 300:
        raise OAuthProviderError()
    if len(response.body) > MAX_RESPONSE_BYTES:
        raise OAuthResponseError()
    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        raise OAuthResponseError() from None
    if not isinstance(payload, dict):
        raise OAuthResponseError()
    return payload


def _callback_uri(api_base_url: str) -> str:
    if not isinstance(api_base_url, str):
        raise OAuthConfigurationError()
    try:
        parsed = urllib.parse.urlsplit(api_base_url)
        valid = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
        )
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise OAuthConfigurationError()
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, CALLBACK_PATH, "", "")
    )


def _validate_callback_uri(callback_uri: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(callback_uri)
        valid = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and parsed.path == CALLBACK_PATH
        )
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise OAuthConfigurationError()
    return callback_uri


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _base64url_encode(digest)


def _valid_state(value: object) -> bool:
    return (
        isinstance(value, str)
        and 32 <= len(value) <= 128
        and value.isascii()
        and all(character.isalnum() or character in "-_" for character in value)
    )


def _valid_verifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and 43 <= len(value) <= 128
        and value.isascii()
        and all(character.isalnum() or character in "-._~" for character in value)
    )


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    if not value or not value.isascii():
        raise ValueError
    decoded = base64.b64decode(
        value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
    )
    if _base64url_encode(decoded) != value:
        raise ValueError
    return decoded
