"""Phase 1 model metadata tests."""

from sqlalchemy import CHAR, BigInteger, Integer, UniqueConstraint

from app.database.models import Base


def _unique_columns(table_name: str) -> set[frozenset[str]]:
    table = Base.metadata.tables[table_name]
    return {
        frozenset(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_identity_primary_keys_and_external_ids_use_expected_types() -> None:
    for table_name in ("users", "repositories", "sessions"):
        assert isinstance(Base.metadata.tables[table_name].c.id.type, Integer)

    assert isinstance(Base.metadata.tables["users"].c.github_user_id.type, BigInteger)
    assert isinstance(
        Base.metadata.tables["repositories"].c.github_repo_id.type, BigInteger
    )


def test_identity_constraints_and_nullable_fields() -> None:
    users = Base.metadata.tables["users"]
    repositories = Base.metadata.tables["repositories"]

    assert frozenset({"github_user_id"}) in _unique_columns("users")
    assert frozenset({"user_id", "github_repo_id"}) in _unique_columns("repositories")
    assert frozenset({"token_hash"}) in _unique_columns("sessions")
    assert users.c.email.nullable
    assert repositories.c.default_branch.nullable
    assert repositories.c.primary_language.nullable
    assert repositories.c.github_updated_at.nullable
    assert not repositories.c.is_available.nullable
    assert str(repositories.c.is_available.server_default.arg) == "true"


def test_foreign_keys_preserve_repository_history_and_revoke_sessions() -> None:
    repositories = Base.metadata.tables["repositories"]
    sessions = Base.metadata.tables["sessions"]

    repository_fk = next(iter(repositories.c.user_id.foreign_keys))
    session_fk = next(iter(sessions.c.user_id.foreign_keys))

    assert repository_fk.target_fullname == "users.id"
    assert repository_fk.ondelete == "RESTRICT"
    assert session_fk.target_fullname == "users.id"
    assert session_fk.ondelete == "CASCADE"


def test_session_stores_only_fixed_hash_and_indexes_expiry() -> None:
    sessions = Base.metadata.tables["sessions"]

    assert isinstance(sessions.c.token_hash.type, CHAR)
    assert sessions.c.token_hash.type.length == 64
    assert "token" not in sessions.c
    assert {index.name for index in sessions.indexes} == {"ix_sessions_expires_at"}


def test_repository_owner_lookup_uses_composite_unique_index() -> None:
    repositories = Base.metadata.tables["repositories"]
    owner_lookup_constraint = next(
        constraint
        for constraint in repositories.constraints
        if isinstance(constraint, UniqueConstraint)
        and tuple(constraint.columns.keys()) == ("user_id", "github_repo_id")
    )

    assert owner_lookup_constraint.name == "uq_repositories_user_github_repo"
