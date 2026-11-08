"""Short-transaction operations for analysis-run lifecycle state."""

import logging
from collections.abc import Sequence

from sqlalchemy import func, or_, update
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import AnalysisRun
from app.database.run_states import (
    ALLOWED_STATUS_TRANSITIONS,
    RUN_STAGE_VALUES,
    RUN_STATUS_FAILED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_VALUES,
)
from app.database.session import SessionLocal

logger = logging.getLogger(__name__)
INTERRUPTED_ERROR_CODE = "interrupted"
INTERRUPTED_ERROR_MESSAGE = "Analysis was interrupted. Please run it again."


class InvalidRunTransition(ValueError):
    """Raised when a requested run-state transition is not allowed."""


class RunStateConflict(RuntimeError):
    """Raised when a conditional lifecycle update matches no current run."""


def transition_run_status(
    run_id: int,
    expected_status: str,
    new_status: str,
    *,
    session_factory: sessionmaker[Session] = SessionLocal,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Apply one allowed status transition if the run is still in expected_status."""
    if expected_status not in RUN_STATUS_VALUES or new_status not in RUN_STATUS_VALUES:
        raise InvalidRunTransition(
            f"Unsupported run status transition: {expected_status} -> {new_status}"
        )
    if new_status not in ALLOWED_STATUS_TRANSITIONS[expected_status]:
        raise InvalidRunTransition(
            f"Disallowed run status transition: {expected_status} -> {new_status}"
        )

    values: dict[str, object] = {
        "status": new_status,
        "error_code": error_code,
        "error_message": error_message,
    }
    if new_status == RUN_STATUS_RUNNING:
        values["started_at"] = func.now()
    else:
        values["completed_at"] = func.now()

    with session_factory.begin() as database_session:
        result = database_session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id, AnalysisRun.status == expected_status)
            .values(**values)
        )
        if result.rowcount != 1:
            raise RunStateConflict(f"Analysis run {run_id} changed before transition.")


def set_run_stage(
    run_id: int,
    stage: str,
    *,
    session_factory: sessionmaker[Session] = SessionLocal,
) -> None:
    """Advance a running run to a stage, allowing repeats and forward skips."""
    if stage not in RUN_STAGE_VALUES:
        raise ValueError(f"Unsupported analysis stage: {stage}")

    allowed_current_stages: Sequence[str] = RUN_STAGE_VALUES[
        : RUN_STAGE_VALUES.index(stage) + 1
    ]
    with session_factory.begin() as database_session:
        result = database_session.execute(
            update(AnalysisRun)
            .where(
                AnalysisRun.id == run_id,
                AnalysisRun.status == RUN_STATUS_RUNNING,
                or_(
                    AnalysisRun.stage.is_(None),
                    AnalysisRun.stage.in_(allowed_current_stages),
                ),
            )
            .values(stage=stage)
        )
        if result.rowcount != 1:
            raise RunStateConflict(f"Analysis run {run_id} cannot advance to {stage}.")


def reconcile_interrupted_runs(
    session_factory: sessionmaker[Session] = SessionLocal,
) -> tuple[int, ...]:
    """Fail queued/running runs left behind by a process that has exited."""
    with session_factory.begin() as database_session:
        result = database_session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.status.in_((RUN_STATUS_QUEUED, RUN_STATUS_RUNNING)))
            .values(
                status=RUN_STATUS_FAILED,
                error_code=INTERRUPTED_ERROR_CODE,
                error_message=INTERRUPTED_ERROR_MESSAGE,
                completed_at=func.now(),
            )
            .returning(AnalysisRun.id)
        )
        run_ids = tuple(result.scalars())

    logger.info(
        "Reconciled interrupted analysis runs",
        extra={"run_count": len(run_ids), "run_ids": run_ids},
    )
    return run_ids
