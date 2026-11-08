"""Alembic revision metadata tests that do not load the migration environment."""

from pathlib import Path

from alembic.script import ScriptDirectory


def test_local_migration_revisions_fit_version_column_limit() -> None:
    """Every local revision fits alembic_version.version_num VARCHAR(32)."""
    migrations_path = (
        Path(__file__).resolve().parents[1] / "app" / "database" / "migrations"
    )
    script_directory = ScriptDirectory(str(migrations_path))
    revisions = list(script_directory.walk_revisions())

    assert revisions
    assert all(revision.revision is not None for revision in revisions)
    assert all(len(revision.revision) <= 32 for revision in revisions)
    assert "0002_identity" in {revision.revision for revision in revisions}
    assert "0003_analysis" in {revision.revision for revision in revisions}


def test_analysis_revision_follows_identity_revision() -> None:
    migrations_path = (
        Path(__file__).resolve().parents[1] / "app" / "database" / "migrations"
    )
    script_directory = ScriptDirectory(str(migrations_path))

    assert (
        script_directory.get_revision("0003_analysis").down_revision == "0002_identity"
    )
