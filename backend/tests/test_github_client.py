"""Tests for safe GitHub repository retrieval without network access."""

import json
import logging
from datetime import UTC, datetime

import pytest

from app.auth.oauth import (
    GITHUB_API_VERSION,
    HTTP_TIMEOUT_SECONDS,
    HttpRequest,
    HttpResponse,
    OAuthRedirectError,
)
from app.github.client import (
    GITHUB_API_URL,
    GITHUB_USER_AGENT,
    GitHubAuthenticationError,
    GitHubForbiddenError,
    GitHubNotFoundError,
    GitHubProviderError,
    GitHubRateLimitError,
    GitHubRedirectError,
    GitHubRepository,
    GitHubResponseError,
    GitHubServerError,
    GitHubTimeoutError,
    GitHubTransportError,
    list_repositories,
)

ACCESS_TOKEN = "github-access-token-sentinel"
RESPONSE_SENTINEL = "provider-response-sentinel"


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


def repository_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": 123,
        "name": "RepoPulse",
        "owner": {"login": "octocat", "type": "User"},
        "default_branch": "main",
        "fork": True,
        "archived": False,
        "language": "Python",
        "updated_at": "2026-10-22T10:30:00Z",
        "size": 42,
        "private": False,
        "description": RESPONSE_SENTINEL,
    }
    payload.update(overrides)
    return payload


def json_response(
    payload: object,
    *,
    headers: dict[str, str] | None = None,
    status: int = 200,
) -> HttpResponse:
    return HttpResponse(
        status=status,
        body=json.dumps(payload).encode("utf-8"),
        headers=headers or {},
    )


def test_parses_repository_into_typed_non_secret_data() -> None:
    transport = FakeTransport(json_response([repository_payload()]))

    repositories = list_repositories(ACCESS_TOKEN, transport=transport)

    assert repositories == (
        GitHubRepository(
            github_repo_id=123,
            name="RepoPulse",
            owner_login="octocat",
            owner_type="User",
            default_branch="main",
            is_fork=True,
            is_archived=False,
            primary_language="Python",
            updated_at=datetime(2026, 10, 22, 10, 30, tzinfo=UTC),
            size=42,
        ),
    )
    assert RESPONSE_SENTINEL not in repr(repositories)
    assert ACCESS_TOKEN not in repr(repositories)


def test_follows_github_link_pagination() -> None:
    transport = FakeTransport(
        json_response(
            [repository_payload()],
            headers={
                "Link": (
                    "<https://api.github.com/user/repos?visibility=public"
                    '&per_page=100&page=2>; rel="next"'
                )
            },
        ),
        json_response([repository_payload(id=456, name="second")]),
    )

    repositories = list_repositories(ACCESS_TOKEN, transport=transport)

    assert [repository.github_repo_id for repository in repositories] == [123, 456]
    assert len(transport.requests) == 2
    assert transport.requests[1].url == (
        f"{GITHUB_API_URL}?visibility=public&per_page=100&page=2"
    )


def test_builds_authenticated_request_without_leaking_secret_repr() -> None:
    transport = FakeTransport(json_response([]))

    assert list_repositories(ACCESS_TOKEN, transport=transport) == ()

    request = transport.requests[0]
    assert request.method == "GET"
    assert request.url == (f"{GITHUB_API_URL}?visibility=public&per_page=100&page=1")
    assert request.headers == {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "User-Agent": GITHUB_USER_AGENT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    assert ACCESS_TOKEN not in repr(request)


@pytest.mark.parametrize(
    ("failure", "error_type"),
    [
        (TimeoutError(f"timeout {ACCESS_TOKEN}"), GitHubTimeoutError),
        (OSError(f"network failure {ACCESS_TOKEN}"), GitHubTransportError),
        (RuntimeError(f"unexpected {ACCESS_TOKEN}"), GitHubTransportError),
        (OAuthRedirectError(), GitHubRedirectError),
    ],
)
def test_maps_transport_failures_safely(
    failure: Exception, error_type: type[Exception]
) -> None:
    transport = FakeTransport(failure)

    with pytest.raises(error_type) as error:
        list_repositories(ACCESS_TOKEN, transport=transport)

    _assert_no_secrets(str(error.value), repr(error.value))


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, GitHubAuthenticationError),
        (403, GitHubForbiddenError),
        (404, GitHubNotFoundError),
        (500, GitHubServerError),
        (503, GitHubServerError),
        (400, GitHubProviderError),
    ],
)
def test_maps_http_statuses_without_response_body(
    status: int, error_type: type[Exception]
) -> None:
    transport = FakeTransport(
        HttpResponse(status=status, body=RESPONSE_SENTINEL.encode())
    )

    with pytest.raises(error_type) as error:
        list_repositories(ACCESS_TOKEN, transport=transport)

    _assert_no_secrets(str(error.value), repr(error.value))


@pytest.mark.parametrize(
    ("retry_after", "expected"),
    [
        ("17", 17),
        ("invalid-header", None),
        (None, None),
    ],
)
def test_rate_limit_retry_after_is_parsed_but_not_exposed(
    retry_after: str | None, expected: int | None
) -> None:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    transport = FakeTransport(
        HttpResponse(
            status=429,
            body=RESPONSE_SENTINEL.encode(),
            headers=headers,
        )
    )

    with pytest.raises(GitHubRateLimitError) as error:
        list_repositories(ACCESS_TOKEN, transport=transport)

    assert error.value.retry_after_seconds == expected
    _assert_no_secrets(str(error.value), repr(error.value))
    assert retry_after is None or retry_after not in str(error.value)


def test_rate_limit_accepts_http_date_without_exposing_header() -> None:
    retry_after = "Fri, 31 Dec 9999 23:59:59 GMT"
    transport = FakeTransport(
        HttpResponse(
            status=429,
            body=b"",
            headers={"Retry-After": retry_after},
        )
    )

    with pytest.raises(GitHubRateLimitError) as error:
        list_repositories(ACCESS_TOKEN, transport=transport)

    assert error.value.retry_after_seconds is not None
    assert error.value.retry_after_seconds > 0
    assert retry_after not in str(error.value)
    assert retry_after not in repr(error.value)


def test_forbidden_rate_limit_with_retry_after_maps_to_rate_limit_error() -> None:
    transport = FakeTransport(
        HttpResponse(
            status=403,
            body=RESPONSE_SENTINEL.encode(),
            headers={"Retry-After": "17"},
        )
    )

    with pytest.raises(GitHubRateLimitError) as error:
        list_repositories(ACCESS_TOKEN, transport=transport)

    assert error.value.retry_after_seconds == 17
    _assert_no_secrets(str(error.value), repr(error.value))


def test_forbidden_primary_rate_limit_uses_reset_header() -> None:
    reset = str(int(datetime.now(UTC).timestamp()) + 17)
    transport = FakeTransport(
        HttpResponse(
            status=403,
            body=RESPONSE_SENTINEL.encode(),
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": reset},
        )
    )

    with pytest.raises(GitHubRateLimitError) as error:
        list_repositories(ACCESS_TOKEN, transport=transport)

    assert error.value.retry_after_seconds in {16, 17}
    _assert_no_secrets(str(error.value), repr(error.value))


@pytest.mark.parametrize(
    "response",
    [
        HttpResponse(status=302, body=b"redirect"),
        HttpResponse(status=307, body=b"redirect"),
    ],
)
def test_rejects_redirect_responses(response: HttpResponse) -> None:
    transport = FakeTransport(response)

    with pytest.raises(GitHubRedirectError):
        list_repositories(ACCESS_TOKEN, transport=transport)


def test_maps_not_modified_to_provider_error_not_redirect() -> None:
    transport = FakeTransport(HttpResponse(status=304, body=b""))

    with pytest.raises(GitHubProviderError):
        list_repositories(ACCESS_TOKEN, transport=transport)


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"{",
        b"{}",
        b"null",
        b'"not-a-list"',
    ],
)
def test_rejects_malformed_json_or_unexpected_top_level_shape(body: bytes) -> None:
    transport = FakeTransport(HttpResponse(status=200, body=body))

    with pytest.raises(GitHubResponseError):
        list_repositories(ACCESS_TOKEN, transport=transport)


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": True},
        {"id": "123"},
        {"name": ""},
        {"owner": None},
        {"owner": {"type": "User"}},
        {"owner": {"login": "octocat"}},
        {"owner": {"login": 3, "type": "User"}},
        {"owner": {"login": "octocat", "type": ""}},
        {"default_branch": 4},
        {"fork": 1},
        {"archived": "false"},
        {"language": 12},
        {"updated_at": "not-a-date"},
        {"updated_at": "2026-10-22T10:30:00"},
        {"size": True},
        {"size": -1},
    ],
)
def test_rejects_missing_or_wrongly_typed_repository_fields(
    overrides: dict[str, object],
) -> None:
    transport = FakeTransport(json_response([repository_payload(**overrides)]))

    with pytest.raises(GitHubResponseError):
        list_repositories(ACCESS_TOKEN, transport=transport)


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "name",
        "owner",
        "default_branch",
        "fork",
        "archived",
        "language",
        "updated_at",
        "size",
    ],
)
def test_rejects_missing_repository_fields(field: str) -> None:
    payload = repository_payload()
    payload.pop(field)
    transport = FakeTransport(json_response([payload]))

    with pytest.raises(GitHubResponseError):
        list_repositories(ACCESS_TOKEN, transport=transport)


def test_rejects_untrusted_or_repeated_pagination_links() -> None:
    untrusted = FakeTransport(
        json_response(
            [],
            headers={
                "Link": ('<https://attacker.example/user/repos?page=2>; rel="next"')
            },
        )
    )
    repeated = FakeTransport(
        json_response(
            [],
            headers={
                "Link": ('<https://api.github.com/user/repos?page=1>; rel="next"')
            },
        )
    )

    for transport in (untrusted, repeated):
        with pytest.raises(GitHubResponseError):
            list_repositories(ACCESS_TOKEN, transport=transport)


def test_token_is_absent_from_errors_logs_and_captured_output(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    response_body = f"{ACCESS_TOKEN} {RESPONSE_SENTINEL}".encode()
    transport = FakeTransport(HttpResponse(status=503, body=response_body))

    caplog.set_level(logging.DEBUG)
    with pytest.raises(GitHubServerError) as error:
        list_repositories(ACCESS_TOKEN, transport=transport)

    captured = capsys.readouterr()
    _assert_no_secrets(
        str(error.value),
        repr(error.value),
        caplog.text,
        captured.out,
        captured.err,
        repr(transport.requests[0]),
    )


def _assert_no_secrets(*values: str) -> None:
    for value in values:
        assert ACCESS_TOKEN not in value
        assert RESPONSE_SENTINEL not in value
