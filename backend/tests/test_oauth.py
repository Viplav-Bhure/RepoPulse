"""Tests for the GitHub OAuth helpers without network access."""

import base64
import hashlib
import hmac
import json
import urllib.parse
import urllib.request

import pytest

from app.auth.oauth import (
    CALLBACK_PATH,
    HTTP_TIMEOUT_SECONDS,
    TOKEN_URL,
    USER_URL,
    GitHubProfile,
    HttpRequest,
    HttpResponse,
    OAuthAccessToken,
    OAuthAuthorizationRequest,
    OAuthProviderError,
    OAuthRedirectError,
    OAuthResponseError,
    OAuthStateError,
    OAuthTimeoutError,
    OAuthTransportError,
    _RejectRedirectHandler,
    create_authorization_request,
    exchange_code_for_token,
    fetch_github_profile,
    serialize_state_cookie,
    validate_state_cookie,
)

SESSION_SECRET = "test-session-secret-for-testing-only-32bytes"
CLIENT_ID = "oauth-client-id"
CLIENT_SECRET = "client-secret-sentinel"
AUTH_CODE = "authorization-code-sentinel"
ACCESS_TOKEN = "access-token-sentinel"
CODE_VERIFIER = "a" * 64
STATE = "b" * 43
CALLBACK_URI = f"http://localhost:8000{CALLBACK_PATH}"


class FakeTransport:
    def __init__(self, *results: HttpResponse | Exception) -> None:
        self.results = list(results)
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest, timeout: float) -> HttpResponse:
        self.requests.append(request)
        assert timeout == HTTP_TIMEOUT_SECONDS
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def json_response(payload: object, status: int = 200) -> HttpResponse:
    return HttpResponse(status=status, body=json.dumps(payload).encode("utf-8"))


def test_authorization_url_uses_pkce_and_omits_scope() -> None:
    authorization = create_authorization_request(
        client_id=CLIENT_ID,
        api_base_url="http://localhost:8000/",
        session_secret=SESSION_SECRET,
        now=1000,
    )
    parsed_url = urllib.parse.urlsplit(authorization.authorization_url)
    query = urllib.parse.parse_qs(parsed_url.query)

    assert parsed_url.scheme == "https"
    assert parsed_url.netloc == "github.com"
    assert parsed_url.path == "/login/oauth/authorize"
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [CALLBACK_URI]
    assert query["code_challenge_method"] == ["S256"]
    assert "scope" not in query

    state = validate_state_cookie(
        state_cookie=authorization.state_cookie,
        returned_state=query["state"][0],
        session_secret=SESSION_SECRET,
        now=1000,
    )
    expected_challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(state.code_verifier.encode("ascii")).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    assert query["code_challenge"] == [expected_challenge]


def test_state_cookie_round_trip_is_deterministic() -> None:
    first = serialize_state_cookie(
        state=STATE,
        code_verifier=CODE_VERIFIER,
        session_secret=SESSION_SECRET,
        issued_at=1000,
    )
    second = serialize_state_cookie(
        state=STATE,
        code_verifier=CODE_VERIFIER,
        session_secret=SESSION_SECRET,
        issued_at=1000,
    )
    validated = validate_state_cookie(
        state_cookie=first,
        returned_state=STATE,
        session_secret=SESSION_SECRET,
        now=1001,
    )

    assert first == second
    assert validated.state == STATE
    assert validated.code_verifier == CODE_VERIFIER
    assert repr(validated) == "ValidatedOAuthState(<redacted>)"


@pytest.mark.parametrize(
    ("state_cookie", "returned_state", "now"),
    [
        (None, STATE, 1000),
        ("not-a-cookie", STATE, 1000),
        ("v1.!!!!.!!!!", STATE, 1000),
        ("v1.eyJub3QiOiJzdGF0ZSJ9.AA", STATE, 1000),
        ("valid", None, 1000),
        ("valid", "c" * 43, 1000),
        ("valid", STATE, 1600),
        ("valid", STATE, 999),
    ],
)
def test_state_validation_rejects_invalid_inputs(
    state_cookie: str | None, returned_state: str | None, now: int
) -> None:
    if state_cookie == "valid":
        state_cookie = serialize_state_cookie(
            state=STATE,
            code_verifier=CODE_VERIFIER,
            session_secret=SESSION_SECRET,
            issued_at=1000,
        )
    with pytest.raises(OAuthStateError):
        validate_state_cookie(
            state_cookie=state_cookie,
            returned_state=returned_state,
            session_secret=SESSION_SECRET,
            now=now,
        )


def test_state_validation_rejects_invalid_signature() -> None:
    cookie = serialize_state_cookie(
        state=STATE,
        code_verifier=CODE_VERIFIER,
        session_secret=SESSION_SECRET,
        issued_at=1000,
    )
    payload, signature = cookie.rsplit(".", 1)
    altered_signature = ("A" if signature[0] != "A" else "B") + signature[1:]

    with pytest.raises(OAuthStateError):
        validate_state_cookie(
            state_cookie=f"{payload}.{altered_signature}",
            returned_state=STATE,
            session_secret=SESSION_SECRET,
            now=1001,
        )


def test_state_validation_rejects_malformed_signed_payload() -> None:
    payload = base64.urlsafe_b64encode(b"not-json").rstrip(b"=").decode("ascii")
    signed_value = f"v1.{payload}"
    signature = hmac.new(
        SESSION_SECRET.encode(), signed_value.encode(), hashlib.sha256
    ).digest()
    cookie = (
        f"{signed_value}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"
    )

    with pytest.raises(OAuthStateError):
        validate_state_cookie(
            state_cookie=cookie,
            returned_state=STATE,
            session_secret=SESSION_SECRET,
            now=1001,
        )


def test_exchange_and_profile_use_injected_transport() -> None:
    transport = FakeTransport(
        json_response({"access_token": ACCESS_TOKEN, "token_type": "bearer"}),
        json_response({"id": 123, "login": "octocat", "email": None}),
    )
    token = exchange_code_for_token(
        code=AUTH_CODE,
        code_verifier=CODE_VERIFIER,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        api_base_url="http://localhost:8000",
        transport=transport,
    )
    profile = fetch_github_profile(token, transport=transport)

    assert profile == GitHubProfile(github_user_id=123, username="octocat", email=None)
    token_request, profile_request = transport.requests
    assert token_request.method == "POST"
    assert token_request.url == TOKEN_URL
    assert token_request.headers["Accept"] == "application/json"
    assert token_request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    token_body = urllib.parse.parse_qs(token_request.body.decode("ascii"))
    assert token_body == {
        "code": [AUTH_CODE],
        "client_id": [CLIENT_ID],
        "client_secret": [CLIENT_SECRET],
        "redirect_uri": [CALLBACK_URI],
        "code_verifier": [CODE_VERIFIER],
    }
    assert profile_request.method == "GET"
    assert profile_request.url == USER_URL
    assert profile_request.headers["Authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert profile_request.headers["Accept"] == "application/vnd.github+json"
    assert profile_request.headers["X-GitHub-Api-Version"] == "2026-03-10"
    assert repr(token) == "OAuthAccessToken(<redacted>)"
    assert ACCESS_TOKEN not in repr(token)
    assert "email" not in profile_request.url


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"access_token": ACCESS_TOKEN},
        {"access_token": 42, "token_type": "bearer"},
        {"access_token": ACCESS_TOKEN, "token_type": "Basic"},
    ],
)
def test_malformed_token_response_is_sanitized(payload: object) -> None:
    transport = FakeTransport(json_response(payload))
    with pytest.raises(OAuthResponseError) as error:
        exchange_code_for_token(
            code=AUTH_CODE,
            code_verifier=CODE_VERIFIER,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            api_base_url="http://localhost:8000",
            transport=transport,
        )
    _assert_no_secrets(str(error.value), repr(error.value))


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        json.dumps([]).encode(),
        json.dumps({"id": True, "login": "octocat", "email": None}).encode(),
        json.dumps({"id": 1, "login": "", "email": None}).encode(),
        json.dumps({"id": 1, "login": "octocat"}).encode(),
        json.dumps({"id": 1, "login": "octocat", "email": 12}).encode(),
    ],
)
def test_malformed_profile_response_is_sanitized(payload: bytes) -> None:
    transport = FakeTransport(HttpResponse(status=200, body=payload))
    with pytest.raises(OAuthResponseError) as error:
        fetch_github_profile(OAuthAccessToken(ACCESS_TOKEN), transport=transport)
    _assert_no_secrets(str(error.value), repr(error.value))


@pytest.mark.parametrize("status", [400, 401, 403, 500])
def test_provider_http_errors_hide_response_body(status: int) -> None:
    response_body = f"{ACCESS_TOKEN} {CLIENT_SECRET} {AUTH_CODE}".encode()
    transport = FakeTransport(HttpResponse(status=status, body=response_body))
    with pytest.raises(OAuthProviderError) as error:
        fetch_github_profile(OAuthAccessToken(ACCESS_TOKEN), transport=transport)
    _assert_no_secrets(str(error.value), repr(error.value))
    assert response_body.decode() not in str(error.value)


def test_timeout_is_sanitized() -> None:
    timeout_message = f"timeout included {ACCESS_TOKEN} {CLIENT_SECRET}"
    transport = FakeTransport(TimeoutError(timeout_message))
    with pytest.raises(OAuthTimeoutError) as error:
        fetch_github_profile(OAuthAccessToken(ACCESS_TOKEN), transport=transport)
    _assert_no_secrets(str(error.value), repr(error.value))
    assert timeout_message not in str(error.value)


def test_injected_transport_redirect_response_is_rejected() -> None:
    transport = FakeTransport(
        HttpResponse(status=302, body=f"redirect {ACCESS_TOKEN}".encode())
    )
    with pytest.raises(OAuthRedirectError) as error:
        fetch_github_profile(OAuthAccessToken(ACCESS_TOKEN), transport=transport)
    _assert_no_secrets(str(error.value), repr(error.value), repr(transport.requests[0]))


def test_urllib_redirect_handler_rejects_before_following() -> None:
    handler = _RejectRedirectHandler()
    request = urllib.request.Request(USER_URL)
    with pytest.raises(OAuthRedirectError):
        handler.redirect_request(
            request,
            object(),
            302,
            "Found",
            {},
            "https://untrusted.example/profile",
        )


def test_unexpected_transport_failure_is_sanitized() -> None:
    transport = FakeTransport(RuntimeError(f"request leaked {ACCESS_TOKEN}"))
    with pytest.raises(OAuthTransportError) as error:
        fetch_github_profile(OAuthAccessToken(ACCESS_TOKEN), transport=transport)
    _assert_no_secrets(str(error.value), repr(error.value))


def test_authorization_and_http_repr_redact_sensitive_values() -> None:
    authorization = create_authorization_request(
        client_id=CLIENT_ID,
        api_base_url="http://localhost:8000",
        session_secret=SESSION_SECRET,
        now=1000,
    )
    request = HttpRequest(
        method="POST",
        url=TOKEN_URL,
        headers={"Authorization": ACCESS_TOKEN, "Cookie": "cookie-sentinel"},
        body=f"{AUTH_CODE} {CLIENT_SECRET}".encode(),
    )
    response = HttpResponse(status=500, body=b"response-body-sentinel")

    output = " ".join(
        (
            repr(authorization),
            repr(request),
            repr(response),
        )
    )
    _assert_no_secrets(output)
    assert isinstance(authorization, OAuthAuthorizationRequest)


def _assert_no_secrets(*values: str) -> None:
    forbidden = (
        ACCESS_TOKEN,
        AUTH_CODE,
        CLIENT_SECRET,
        "cookie-sentinel",
        "response-body-sentinel",
    )
    for value in values:
        assert all(secret not in value for secret in forbidden)
