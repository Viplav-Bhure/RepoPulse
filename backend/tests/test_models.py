"""Phase 1 model metadata tests."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Float,
    Integer,
    Text,
    UniqueConstraint,
    inspect,
    text,
)

from app.database.models import AnalysisRun, Base, File


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


def test_analysis_model_fields_constraints_and_indexes() -> None:
    runs = Base.metadata.tables["analysis_runs"]
    files = Base.metadata.tables["files"]
    findings = Base.metadata.tables["findings"]

    assert set(runs.c.keys()) >= {
        "id",
        "repository_id",
        "commit_sha",
        "status",
        "stage",
        "error_code",
        "error_message",
        "warnings",
        "created_at",
        "started_at",
        "completed_at",
    }
    assert runs.c.commit_sha.type.length == 64
    assert runs.c.commit_sha.nullable
    assert not runs.c.created_at.nullable
    assert not runs.c.warnings.nullable
    assert str(runs.c.status.server_default.arg) == "'queued'"
    assert str(runs.c.warnings.server_default.arg) == "'[]'::jsonb"
    assert {"ck_analysis_runs_status", "ck_analysis_runs_stage"} <= {
        constraint.name
        for constraint in runs.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {index.name for index in runs.indexes} == {
        "ix_analysis_runs_repository_id",
        "uq_analysis_runs_active_repository",
    }
    assert "status IN ('queued', 'running')" in str(
        next(
            index
            for index in runs.indexes
            if index.name == "uq_analysis_runs_active_repository"
        ).dialect_options["postgresql"]["where"]
    )

    assert isinstance(files.c.path.type, Text)
    assert files.c.complexity.nullable
    assert isinstance(files.c.coverage.type, Float)
    assert files.c.coverage.nullable
    assert {constraint.name for constraint in files.constraints} >= {
        "ck_files_file_kind",
        "uq_files_analysis_id_path",
    }
    assert {index.name for index in files.indexes} == set()

    assert findings.c.line.nullable
    assert findings.c.measured_value.nullable
    assert findings.c.threshold.nullable
    assert findings.c.masked_excerpt.nullable
    assert isinstance(findings.c.masked_excerpt.type, Text)
    assert {index.name for index in findings.indexes} == {"ix_findings_file_id"}
    assert not {"predictions", "functions"} & set(Base.metadata.tables)

    assert AnalysisRun.__mapper__.relationships["files"].passive_deletes
    assert File.__mapper__.relationships["findings"].passive_deletes


def test_analysis_foreign_keys_cascade() -> None:
    for table_name, column_name, target in (
        ("analysis_runs", "repository_id", "repositories.id"),
        ("files", "analysis_id", "analysis_runs.id"),
        ("findings", "file_id", "files.id"),
    ):
        foreign_key = next(
            iter(Base.metadata.tables[table_name].c[column_name].foreign_keys)
        )
        assert foreign_key.target_fullname == target
        assert foreign_key.ondelete == "CASCADE"


def test_migrations_match_metadata_on_empty_database(
    test_database_engine, monkeypatch
) -> None:
    from app import config

    with test_database_engine.begin() as connection:
        Base.metadata.drop_all(connection)
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    test_url = test_database_engine.url.render_as_string(hide_password=False)
    monkeypatch.setattr(
        config,
        "settings",
        config.settings.model_copy(update={"DATABASE_URL": test_url}),
    )
    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("script_location", "app/database/migrations")
    command.upgrade(alembic_config, "head")

    def include_object(object_, name, type_, reflected, compare_to) -> bool:
        return type_ != "table" or name != "alembic_version"

    with test_database_engine.connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={"include_object": include_object},
        )
        assert compare_metadata(context, Base.metadata) == []

    command.downgrade(alembic_config, "0002_identity")
    with test_database_engine.connect() as connection:
        assert not {
            "analysis_runs",
            "files",
            "findings",
        } & set(inspect(connection).get_table_names())

    command.upgrade(alembic_config, "head")
