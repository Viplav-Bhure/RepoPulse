"""Canonical analysis-run state values and transition rules."""

from typing import Final

RUN_STATUS_QUEUED: Final = "queued"
RUN_STATUS_RUNNING: Final = "running"
RUN_STATUS_COMPLETED: Final = "completed"
RUN_STATUS_FAILED: Final = "failed"

RUN_STATUS_VALUES: Final = (
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
)

RUN_STAGE_VALUES: Final = (
    "cloning",
    "discovery",
    "parsing",
    "metrics",
    "static_analysis",
    "security",
    "dependencies",
    "git_history",
    "coverage",
    "ml",
    "risk",
    "persisting",
    "cleanup",
)

FILE_KIND_VALUES: Final = ("source", "test")
FINDING_SEVERITY_VALUES: Final = ("LOW", "MEDIUM", "HIGH")

ALLOWED_STATUS_TRANSITIONS: Final = {
    RUN_STATUS_QUEUED: frozenset({RUN_STATUS_RUNNING, RUN_STATUS_FAILED}),
    RUN_STATUS_RUNNING: frozenset({RUN_STATUS_COMPLETED, RUN_STATUS_FAILED}),
    RUN_STATUS_COMPLETED: frozenset(),
    RUN_STATUS_FAILED: frozenset(),
}


def sql_values(values: tuple[str, ...]) -> str:
    """Render the fixed, source-controlled values used by model CHECK constraints."""
    return ", ".join(f"'{value}'" for value in values)
