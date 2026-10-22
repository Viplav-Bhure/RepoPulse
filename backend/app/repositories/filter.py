"""Ownership filter for GitHub repositories (task 1.9).

Pure function: no database access, no HTTP calls, no global state.
Implements SEC-2: only repositories owned by the authenticated user
(owner_login case-insensitively equals username, owner_type == "User").
User-owned forks are included [Decided].
Organization-owned and other-user repositories are excluded.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.github.client import GitHubRepository

# The GitHub API returns "User" or "Organization" for owner.type.
# Only "User" is accepted so that organization-owned repositories are excluded
# even when the login accidentally matches (SEC-2).
_OWNER_TYPE_USER: str = "User"


def filter_owned_repositories(
    repos: Sequence[GitHubRepository],
    username: str,
) -> tuple[GitHubRepository, ...]:
    """Return only the repositories whose owner is the authenticated user.

    Rules (all must be true to keep a repository):
    - ``owner_login`` equals ``username`` case-insensitively.
    - ``owner_type`` is exactly ``"User"`` (case-sensitive, as GitHub returns it).

    Forks owned by the user are kept (``is_fork`` is not a filter criterion).
    The input sequence is not mutated; a new tuple is returned.
    An empty input returns an empty tuple deterministically.

    Args:
        repos: Sequence of ``GitHubRepository`` objects returned by the client.
        username: The authenticated user's GitHub username (exact as returned
            by the GitHub ``/user`` endpoint).

    Returns:
        A tuple containing only the repositories that pass the ownership check.

    Raises:
        TypeError: If ``repos`` is not a ``Sequence`` or ``username`` is not
            a ``str``.
        ValueError: If ``username`` is empty or blank.
    """
    if not isinstance(username, str):
        raise TypeError("username must be a str")
    if not username or not username.strip():
        raise ValueError("username must not be empty or blank")

    username_lower = username.lower()

    return tuple(
        repo
        for repo in repos
        if repo.owner_login.lower() == username_lower
        and repo.owner_type == _OWNER_TYPE_USER
    )
