"""Tests for the ownership filter (task 1.9).

Covers all required cases:
- matching owner included
- case-insensitive owner match
- user-owned fork included
- organization-owned repository excluded
- another user excluded
- mixed input preserves only allowed repositories
- empty input
- input is not mutated

No real network or credentials used.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.github.client import GitHubRepository
from app.repositories.filter import filter_owned_repositories

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_UPDATED_AT = datetime(2024, 1, 1, tzinfo=UTC)


def _make_repo(
    *,
    owner_login: str = "alice",
    owner_type: str = "User",
    is_fork: bool = False,
    github_repo_id: int = 1,
    name: str = "myrepo",
) -> GitHubRepository:
    """Build a minimal GitHubRepository for testing."""
    return GitHubRepository(
        github_repo_id=github_repo_id,
        name=name,
        owner_login=owner_login,
        owner_type=owner_type,
        default_branch="main",
        is_fork=is_fork,
        is_archived=False,
        primary_language="Python",
        updated_at=_UPDATED_AT,
        size=100,
    )


# ---------------------------------------------------------------------------
# Inclusion tests
# ---------------------------------------------------------------------------


def test_matching_owner_included() -> None:
    """A repository whose owner matches the username is kept."""
    repo = _make_repo(owner_login="alice", owner_type="User")
    result = filter_owned_repositories([repo], "alice")
    assert result == (repo,)


def test_case_insensitive_owner_match() -> None:
    """Username comparison is case-insensitive (SEC-2, task 1.9)."""
    repo = _make_repo(owner_login="Alice", owner_type="User")
    result = filter_owned_repositories([repo], "alice")
    assert result == (repo,)

    # Also test upper-case username against lower-case login
    repo2 = _make_repo(owner_login="alice", owner_type="User", github_repo_id=2)
    result2 = filter_owned_repositories([repo2], "ALICE")
    assert result2 == (repo2,)


def test_user_owned_fork_included() -> None:
    """User-owned forks are included [Decided]."""
    fork = _make_repo(owner_login="alice", owner_type="User", is_fork=True)
    result = filter_owned_repositories([fork], "alice")
    assert result == (fork,)


# ---------------------------------------------------------------------------
# Exclusion tests
# ---------------------------------------------------------------------------


def test_organization_owned_excluded() -> None:
    """Repositories owned by an Organization are excluded (SEC-2)."""
    org_repo = _make_repo(owner_login="alice", owner_type="Organization")
    result = filter_owned_repositories([org_repo], "alice")
    assert result == ()


def test_another_user_excluded() -> None:
    """Repositories owned by a different user are excluded (SEC-2)."""
    other_repo = _make_repo(owner_login="bob", owner_type="User")
    result = filter_owned_repositories([other_repo], "alice")
    assert result == ()


# ---------------------------------------------------------------------------
# Mixed-input test
# ---------------------------------------------------------------------------


def test_mixed_input_preserves_only_allowed_repositories() -> None:
    """Only repositories passing all ownership rules survive the filter."""
    own_repo = _make_repo(
        owner_login="alice", owner_type="User", github_repo_id=1, name="mine"
    )
    own_fork = _make_repo(
        owner_login="Alice",  # different case
        owner_type="User",
        is_fork=True,
        github_repo_id=2,
        name="my-fork",
    )
    org_repo = _make_repo(
        owner_login="alice", owner_type="Organization", github_repo_id=3, name="org"
    )
    other_user_repo = _make_repo(
        owner_login="charlie", owner_type="User", github_repo_id=4, name="theirs"
    )
    other_org_repo = _make_repo(
        owner_login="bigcorp", owner_type="Organization", github_repo_id=5, name="corp"
    )

    all_repos = [own_repo, org_repo, own_fork, other_user_repo, other_org_repo]
    result = filter_owned_repositories(all_repos, "alice")

    # Only own_repo and own_fork should survive
    assert set(result) == {own_repo, own_fork}
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Empty-input test
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_tuple() -> None:
    """An empty input produces an empty tuple deterministically."""
    result = filter_owned_repositories([], "alice")
    assert result == ()
    assert isinstance(result, tuple)


# ---------------------------------------------------------------------------
# Immutability / no-mutation test
# ---------------------------------------------------------------------------


def test_input_is_not_mutated() -> None:
    """The function must not mutate the input sequence (returns new tuple)."""
    repo_a = _make_repo(owner_login="alice", owner_type="User", github_repo_id=1)
    repo_b = _make_repo(owner_login="bob", owner_type="User", github_repo_id=2)
    original_list = [repo_a, repo_b]
    original_ids = [id(r) for r in original_list]

    result = filter_owned_repositories(original_list, "alice")

    # Input list length and identity of elements unchanged
    assert len(original_list) == 2
    assert [id(r) for r in original_list] == original_ids
    # Result is a new tuple, not the same object as the input
    assert result is not original_list
    # The kept repository is the same object (no copy), proving no mutation
    assert result[0] is repo_a


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


def test_empty_username_raises_value_error() -> None:
    """An empty or blank username is rejected immediately."""
    with pytest.raises(ValueError):
        filter_owned_repositories([], "")

    with pytest.raises(ValueError):
        filter_owned_repositories([], "   ")


def test_non_string_username_raises_type_error() -> None:
    """A non-string username raises TypeError."""
    with pytest.raises(TypeError):
        filter_owned_repositories([], None)  # type: ignore[arg-type]
