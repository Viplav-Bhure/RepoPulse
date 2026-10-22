"""Safe GitHub REST API access for repository retrieval."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import ceil

from app.auth.oauth import (
    GITHUB_API_VERSION,
    HTTP_TIMEOUT_SECONDS,
    MAX_RESPONSE_BYTES,
    HttpRequest,
    HttpResponse,
    OAuthRedirectError,
    OAuthResponseError,
    OAuthTimeoutError,
    OAuthTransport,
    OAuthTransportError,
    UrllibTransport,
)

GITHUB_API_URL = "https://api.github.com/user/repos"
GITHUB_USER_AGENT = "RepoPulse"
PAGE_SIZE = 100


class GitHubClientError(Exception):
    """Base class for GitHub API failures with safe, fixed messages."""


class GitHubConfigurationError(GitHubClientError):
    def __init__(self) -> None:
        super().__init__("GitHub API request configuration is invalid.")


class GitHubTimeoutError(GitHubClientError):
    def __init__(self) -> None:
        super().__init__("GitHub API request timed out.")


class GitHubTransportError(GitHubClientError):
    def __init__(self) -> None:
        super().__init__("GitHub API request failed.")


class GitHubRedirectError(GitHubClientError):
    def __init__(self) -> None:
        super().__init__("GitHub API redirects are not accepted.")


class GitHubAuthenticationError(GitHubClientError):
    def __init__(self) -> None:
        super().__init__("GitHub rejected the API credentials.")


class GitHubForbiddenError(GitHubClientError):
    def __init__(self) -> None:
        super().__init__("GitHub denied the API request.")


class GitHubNotFoundError(GitHubClientError):
    def __init__(self) -> None:
        super().__init__("GitHub API resource was not found.")


class GitHubRateLimitError(GitHubClientError):
    def __init__(self, retry_after_seconds: int | None) -> None:
        super().__init__("GitHub API rate limit exceeded.")
        self.retry_after_seconds = retry_after_seconds


class GitHubServerError(GitHubClientError):
    def __init__(self) -> None:
        super().__init__("GitHub API is temporarily unavailable.")


class GitHubProviderError(GitHubClientError):
    def __init__(self) -> None:
        super().__init__("GitHub rejected the API request.")


class GitHubResponseError(GitHubClientError):
    def __init__(self) -> None:
        super().__init__("GitHub returned an invalid API response.")


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    github_repo_id: int
    name: str
    owner_login: str
    owner_type: str
    default_branch: str | None
    is_fork: bool
    is_archived: bool
    primary_language: str | None
    updated_at: datetime
    size: int


def list_repositories(
    access_token: str,
    *,
    transport: OAuthTransport | None = None,
) -> tuple[GitHubRepository, ...]:
    """Return public repositories visible to the token, following GitHub pages."""
    if (
        not isinstance(access_token, str)
        or not access_token
        or "\r" in access_token
        or "\n" in access_token
    ):
        raise GitHubConfigurationError()

    selected_transport = transport if transport is not None else UrllibTransport()
    repositories: list[GitHubRepository] = []
    page = 1
    seen_pages = {page}

    while True:
        request = HttpRequest(
            method="GET",
            url=_page_url(page),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
                "User-Agent": GITHUB_USER_AGENT,
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
        )
        response = _send(request, selected_transport)
        payload = _parse_json_response(response)
        if not isinstance(payload, list):
            raise GitHubResponseError()
        repositories.extend(_parse_repository(item) for item in payload)

        link_header = _header(response.headers, "link")
        next_page = _next_page(link_header, page)
        if next_page is None:
            return tuple(repositories)
        if next_page in seen_pages:
            raise GitHubResponseError()
        seen_pages.add(next_page)
        page = next_page


def _send(request: HttpRequest, transport: OAuthTransport) -> HttpResponse:
    try:
        response = transport.send(request, HTTP_TIMEOUT_SECONDS)
    except (OAuthTimeoutError, TimeoutError):
        raise GitHubTimeoutError() from None
    except OAuthRedirectError:
        raise GitHubRedirectError() from None
    except OAuthResponseError:
        raise GitHubResponseError() from None
    except OAuthTransportError:
        raise GitHubTransportError() from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise GitHubTimeoutError() from None
        raise GitHubTransportError() from None
    except Exception:
        raise GitHubTransportError() from None

    if (
        not isinstance(response, HttpResponse)
        or isinstance(response.status, bool)
        or not isinstance(response.status, int)
        or not isinstance(response.body, bytes)
        or not isinstance(response.headers, Mapping)
    ):
        raise GitHubTransportError()

    if 300 <= response.status < 400 and response.status != 304:
        raise GitHubRedirectError()
    if response.status == 401:
        raise GitHubAuthenticationError()
    if response.status == 403:
        if _is_rate_limited(response.headers):
            raise GitHubRateLimitError(
                _rate_limit_retry_after_seconds(response.headers)
            )
        raise GitHubForbiddenError()
    if response.status == 404:
        raise GitHubNotFoundError()
    if response.status == 429:
        raise GitHubRateLimitError(_rate_limit_retry_after_seconds(response.headers))
    if 500 <= response.status < 600:
        raise GitHubServerError()
    if not 200 <= response.status < 300:
        raise GitHubProviderError()
    if len(response.body) > MAX_RESPONSE_BYTES:
        raise GitHubResponseError()
    return response


def _parse_json_response(response: HttpResponse) -> object:
    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        raise GitHubResponseError() from None

    return payload


def _parse_repository(payload: object) -> GitHubRepository:
    if not isinstance(payload, dict):
        raise GitHubResponseError()
    owner = payload.get("owner")
    if not isinstance(owner, dict):
        raise GitHubResponseError()
    if not {
        "id",
        "name",
        "owner",
        "default_branch",
        "fork",
        "archived",
        "language",
        "updated_at",
        "size",
    }.issubset(payload) or not {"login", "type"}.issubset(owner):
        raise GitHubResponseError()

    repo_id = payload.get("id")
    name = payload.get("name")
    owner_login = owner.get("login")
    owner_type = owner.get("type")
    default_branch = payload.get("default_branch")
    is_fork = payload.get("fork")
    is_archived = payload.get("archived")
    primary_language = payload.get("language")
    updated_at = payload.get("updated_at")
    size = payload.get("size")

    if (
        isinstance(repo_id, bool)
        or not isinstance(repo_id, int)
        or repo_id <= 0
        or not _nonempty_string(name, 255)
        or not _nonempty_string(owner_login, 255)
        or not _nonempty_string(owner_type, 100)
        or (default_branch is not None and not _nonempty_string(default_branch, 255))
        or not isinstance(is_fork, bool)
        or not isinstance(is_archived, bool)
        or (
            primary_language is not None and not _nonempty_string(primary_language, 100)
        )
        or not isinstance(updated_at, str)
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
    ):
        raise GitHubResponseError()

    try:
        parsed_updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        raise GitHubResponseError() from None
    if parsed_updated_at.tzinfo is None:
        raise GitHubResponseError()

    return GitHubRepository(
        github_repo_id=repo_id,
        name=name,
        owner_login=owner_login,
        owner_type=owner_type,
        default_branch=default_branch,
        is_fork=is_fork,
        is_archived=is_archived,
        primary_language=primary_language,
        updated_at=parsed_updated_at,
        size=size,
    )


def _nonempty_string(value: object, max_length: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= max_length
        and "\r" not in value
        and "\n" not in value
    )


def _header(headers: object, name: str) -> str | None:
    if not isinstance(headers, Mapping):
        return None
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == name:
            return value if isinstance(value, str) else None
    return None


def _next_page(link_header: str | None, current_page: int) -> int | None:
    if link_header is None:
        return None

    next_urls: list[str] = []
    for link in link_header.split(","):
        match = re.fullmatch(r"\s*<([^<>]+)>\s*;(.*)", link)
        if match is None:
            continue
        if re.search(r'(?:^|;)\s*rel="?next"?\s*(?:;|$)', match.group(2)):
            next_urls.append(match.group(1))
    if not next_urls:
        return None
    if len(next_urls) != 1:
        raise GitHubResponseError()

    parsed = urllib.parse.urlsplit(next_urls[0])
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "api.github.com"
        or parsed.path != "/user/repos"
        or parsed.fragment
    ):
        raise GitHubResponseError()

    try:
        query = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
        pages = query.get("page", [])
        if len(pages) != 1 or not re.fullmatch(r"[1-9][0-9]*", pages[0]):
            raise GitHubResponseError()
        page = int(pages[0])
    except (ValueError, UnicodeError):
        raise GitHubResponseError() from None
    if page <= current_page:
        raise GitHubResponseError()
    return page


def _page_url(page: int) -> str:
    return f"{GITHUB_API_URL}?visibility=public&per_page={PAGE_SIZE}&page={page}"


def _retry_after_seconds(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if re.fullmatch(r"[0-9]{1,10}", value):
        return int(value)
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            return None
        return max(0, ceil((retry_at - datetime.now(UTC)).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None


def _is_rate_limited(headers: object) -> bool:
    retry_after = _header(headers, "retry-after")
    if retry_after is not None and retry_after.strip():
        return True
    return _header(headers, "x-ratelimit-remaining") == "0"


def _rate_limit_retry_after_seconds(headers: object) -> int | None:
    retry_after = _retry_after_seconds(_header(headers, "retry-after"))
    if retry_after is not None:
        return retry_after

    if _header(headers, "x-ratelimit-remaining") != "0":
        return None
    reset = _header(headers, "x-ratelimit-reset")
    if reset is None or not re.fullmatch(r"[0-9]{1,12}", reset.strip()):
        return None
    try:
        return max(0, int(reset) - int(datetime.now(UTC).timestamp()))
    except (TypeError, ValueError, OverflowError):
        return None
