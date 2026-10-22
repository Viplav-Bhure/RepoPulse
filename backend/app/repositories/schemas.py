"""Pydantic schemas for the repository resource (task 1.11)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RepositoryResponse(BaseModel):
    """Repository item returned by GET /repositories."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="RepoPulse internal repository ID")
    name: str = Field(description="Repository name")
    owner: str = Field(description="Repository owner username")
    primary_language: str | None = Field(
        default=None, description="Primary programming language"
    )
    github_updated_at: datetime | None = Field(
        default=None, description="Last update timestamp reported by GitHub"
    )
    default_branch: str | None = Field(
        default=None, description="Default branch name (null when empty)"
    )
    is_fork: bool = Field(default=False, description="Whether the repository is a fork")
    is_archived: bool = Field(
        default=False, description="Whether the repository is archived on GitHub"
    )
    is_available: bool = Field(
        default=True, description="Whether the repository is available"
    )
    is_empty: bool = Field(
        default=False,
        description="Whether the repository has no default branch / is empty",
    )
    status: str = Field(
        description="Repository status: 'active', 'archived', or 'empty'"
    )
    display_status: str = Field(
        description="User-facing status: 'Active', 'Archived', or 'Empty'"
    )
    status_message: str | None = Field(
        default=None,
        description="Explanatory status message for archived or empty repositories",
    )
    can_analyze: bool = Field(
        description="Whether analysis is supported/enabled for this repository"
    )
    analyze_enabled: bool = Field(
        description="Alias for can_analyze: whether Analyze is supported/enabled"
    )
    github_repo_id: int | None = Field(default=None, description="GitHub repository ID")
    created_at: datetime | None = Field(
        default=None, description="RepoPulse creation timestamp"
    )
    updated_at: datetime | None = Field(
        default=None, description="RepoPulse last update timestamp"
    )
