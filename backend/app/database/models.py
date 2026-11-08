"""Declarative base and Phase 1 identity models."""

from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.database.run_states import (
    FILE_KIND_VALUES,
    FINDING_SEVERITY_VALUES,
    RUN_STAGE_VALUES,
    RUN_STATUS_VALUES,
    sql_values,
)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("github_user_id", name="uq_users_github_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    github_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "github_repo_id", name="uq_repositories_user_github_repo"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    github_repo_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(255))
    is_fork: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    primary_language: Mapped[str | None] = mapped_column(String(100))
    github_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({sql_values(RUN_STATUS_VALUES)})",
            name="ck_analysis_runs_status",
        ),
        CheckConstraint(
            f"stage IS NULL OR stage IN ({sql_values(RUN_STAGE_VALUES)})",
            name="ck_analysis_runs_stage",
        ),
        Index("ix_analysis_runs_repository_id", "repository_id"),
        Index(
            "uq_analysis_runs_active_repository",
            "repository_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey(
            "repositories.id",
            ondelete="CASCADE",
            name="fk_analysis_runs_repository_id_repositories",
        ),
        nullable=False,
    )
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'queued'")
    )
    stage: Mapped[str | None] = mapped_column(String)
    error_code: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    repository: Mapped[Repository] = relationship(back_populates="analysis_runs")
    files: Mapped[list["File"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("analysis_id", "path", name="uq_files_analysis_id_path"),
        CheckConstraint(
            f"file_kind IN ({sql_values(FILE_KIND_VALUES)})",
            name="ck_files_file_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey(
            "analysis_runs.id",
            ondelete="CASCADE",
            name="fk_files_analysis_id_analysis_runs",
        ),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False)
    file_kind: Mapped[str] = mapped_column(String, nullable=False)
    loc: Mapped[int] = mapped_column(Integer, nullable=False)
    functions: Mapped[int] = mapped_column(Integer, nullable=False)
    classes: Mapped[int] = mapped_column(Integer, nullable=False)
    imports: Mapped[int] = mapped_column(Integer, nullable=False)
    complexity: Mapped[int | None] = mapped_column(Integer)
    coverage: Mapped[float | None] = mapped_column(Float)
    analysis: Mapped[AnalysisRun] = relationship(back_populates="files")
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="file",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint(
            f"severity IN ({sql_values(FINDING_SEVERITY_VALUES)})",
            name="ck_findings_severity",
        ),
        Index("ix_findings_file_id", "file_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE", name="fk_findings_file_id_files"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    line: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    measured_value: Mapped[int | None] = mapped_column(Integer)
    threshold: Mapped[int | None] = mapped_column(Integer)
    masked_excerpt: Mapped[str | None] = mapped_column(Text)
    file: Mapped[File] = relationship(back_populates="findings")
