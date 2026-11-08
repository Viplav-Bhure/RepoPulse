"""Add analysis runs, files, and findings."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_analysis"
down_revision = "0002_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_analysis_runs_status",
        ),
        sa.CheckConstraint(
            "stage IS NULL OR stage IN "
            "('cloning', 'discovery', 'parsing', 'metrics', 'static_analysis', "
            "'security', 'dependencies', 'git_history', 'coverage', 'ml', 'risk', "
            "'persisting', 'cleanup')",
            name="ck_analysis_runs_stage",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="fk_analysis_runs_repository_id_repositories",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_runs_repository_id", "analysis_runs", ["repository_id"]
    )
    op.create_index(
        "uq_analysis_runs_active_repository",
        "analysis_runs",
        ["repository_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("analysis_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("file_kind", sa.String(), nullable=False),
        sa.Column("loc", sa.Integer(), nullable=False),
        sa.Column("functions", sa.Integer(), nullable=False),
        sa.Column("classes", sa.Integer(), nullable=False),
        sa.Column("imports", sa.Integer(), nullable=False),
        sa.Column("complexity", sa.Integer(), nullable=True),
        sa.Column("coverage", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "file_kind IN ('source', 'test')", name="ck_files_file_kind"
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analysis_runs.id"],
            name="fk_files_analysis_id_analysis_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", "path", name="uq_files_analysis_id_path"),
    )
    op.create_table(
        "findings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("measured_value", sa.Integer(), nullable=True),
        sa.Column("threshold", sa.Integer(), nullable=True),
        sa.Column("masked_excerpt", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "severity IN ('LOW', 'MEDIUM', 'HIGH')",
            name="ck_findings_severity",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name="fk_findings_file_id_files",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_findings_file_id", "findings", ["file_id"])


def downgrade() -> None:
    op.drop_index("ix_findings_file_id", table_name="findings")
    op.drop_table("findings")
    op.drop_table("files")
    op.drop_index("uq_analysis_runs_active_repository", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_repository_id", table_name="analysis_runs")
    op.drop_table("analysis_runs")
