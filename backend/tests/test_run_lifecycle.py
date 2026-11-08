"""Analysis-run lifecycle behavior against the PostgreSQL test database."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import (
    AnalysisRun,
    File,
    Finding,
    Repository,
    User,
)
from app.database.run_lifecycle import (
    INTERRUPTED_ERROR_CODE,
    INTERRUPTED_ERROR_MESSAGE,
    InvalidRunTransition,
    RunStateConflict,
    reconcile_interrupted_runs,
    set_run_stage,
    transition_run_status,
)


def _session_factory(connection: Connection) -> sessionmaker[Session]:
    return sessionmaker(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )


def _create_run(
    connection: Connection,
    identity: int,
    *,
    status: str = "queued",
    stage: str | None = None,
) -> tuple[int, int]:
    with _session_factory(connection)() as database_session:
        user = User(github_user_id=identity, username=f"user-{identity}")
        database_session.add(user)
        database_session.flush()
        repository = Repository(
            user_id=user.id,
            github_repo_id=identity + 10000,
            name=f"repo-{identity}",
            owner=f"user-{identity}",
        )
        run = AnalysisRun(repository=repository, status=status, stage=stage)
        database_session.add(run)
        database_session.flush()
        repository_id = repository.id
        run_id = run.id
        database_session.commit()
    return repository_id, run_id


def _create_file_tree(connection: Connection, identity: int) -> tuple[int, int, int]:
    with _session_factory(connection)() as database_session:
        user = User(github_user_id=identity, username=f"user-{identity}")
        database_session.add(user)
        database_session.flush()
        repository = Repository(
            user_id=user.id,
            github_repo_id=identity + 10000,
            name=f"repo-{identity}",
            owner=f"user-{identity}",
        )
        run = AnalysisRun(repository=repository)
        file = File(
            analysis=run,
            path="src/example.py",
            language="Python",
            file_kind="source",
            loc=5,
            functions=1,
            classes=0,
            imports=1,
            complexity=2,
        )
        finding = Finding(
            file=file,
            type="complexity",
            severity="LOW",
            line=2,
            message="Example finding",
        )
        database_session.add(finding)
        database_session.flush()
        repository_id, run_id, file_id = repository.id, run.id, file.id
        database_session.commit()
    return repository_id, run_id, file_id


def _assert_integrity_error(
    connection: Connection, statement: str, parameters: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(text(statement), parameters)


def test_database_constraints_reject_invalid_values_and_duplicate_paths(
    postgres_session: Connection,
) -> None:
    repository_id, run_id, _ = _create_file_tree(postgres_session, 701)
    _assert_integrity_error(
        postgres_session,
        "INSERT INTO analysis_runs (repository_id, status) "
        "VALUES (:repository_id, 'invalid')",
        {"repository_id": repository_id},
    )
    _assert_integrity_error(
        postgres_session,
        "INSERT INTO analysis_runs (repository_id, stage) "
        "VALUES (:repository_id, 'completed')",
        {"repository_id": repository_id},
    )
    _assert_integrity_error(
        postgres_session,
        "INSERT INTO analysis_runs (repository_id) VALUES (99999999)",
        {},
    )
    _assert_integrity_error(
        postgres_session,
        "INSERT INTO files "
        "(analysis_id, path, language, file_kind, loc, functions, classes, imports) "
        "VALUES (:analysis_id, 'bad.py', 'Python', 'other', 0, 0, 0, 0)",
        {"analysis_id": run_id},
    )
    _assert_integrity_error(
        postgres_session,
        "INSERT INTO files "
        "(analysis_id, path, language, file_kind, loc, functions, classes, imports) "
        "VALUES (:analysis_id, 'src/example.py', 'Python', 'source', 0, 0, 0, 0)",
        {"analysis_id": run_id},
    )
    _assert_integrity_error(
        postgres_session,
        "INSERT INTO findings (file_id, type, severity, message) "
        "VALUES (99999999, 'test', 'LOW', 'invalid file')",
        {},
    )
    _, _, file_id = _create_file_tree(postgres_session, 702)
    _assert_integrity_error(
        postgres_session,
        "INSERT INTO findings (file_id, type, severity, message) "
        "VALUES (:file_id, 'test', 'CRITICAL', 'invalid severity')",
        {"file_id": file_id},
    )


def test_repository_delete_cascades_through_runs_files_and_findings(
    postgres_session: Connection,
) -> None:
    orm_repository_id, orm_run_id, orm_file_id = _create_file_tree(
        postgres_session, 714
    )
    sql_repository_id, sql_run_id, sql_file_id = _create_file_tree(
        postgres_session, 715
    )

    with _session_factory(postgres_session)() as database_session:
        repository = database_session.get(Repository, orm_repository_id)
        assert repository is not None
        run = repository.analysis_runs[0]
        file = run.files[0]
        assert file.findings
        orm_finding_id = file.findings[0].id

        database_session.delete(repository)
        database_session.flush()
        for model, record_id in (
            (AnalysisRun, orm_run_id),
            (File, orm_file_id),
            (Finding, orm_finding_id),
        ):
            assert (
                database_session.scalar(
                    select(func.count()).select_from(model).where(model.id == record_id)
                )
                == 0
            )

    postgres_session.execute(
        delete(Repository).where(Repository.id == sql_repository_id)
    )
    for model, record_id in (
        (AnalysisRun, sql_run_id),
        (File, sql_file_id),
    ):
        assert (
            postgres_session.scalar(
                select(func.count()).select_from(model).where(model.id == record_id)
            )
            == 0
        )
    assert (
        postgres_session.scalar(
            select(func.count())
            .select_from(Finding)
            .where(Finding.file_id == sql_file_id)
        )
        == 0
    )


def test_active_run_index_is_repository_scoped_and_released_after_failure(
    postgres_session: Connection,
) -> None:
    repository_id, first_run_id = _create_run(postgres_session, 703)
    _create_run(postgres_session, 704)
    factory = _session_factory(postgres_session)

    with pytest.raises(IntegrityError):
        with factory.begin() as database_session:
            database_session.add(AnalysisRun(repository_id=repository_id))
            database_session.flush()

    transition_run_status(first_run_id, "queued", "failed", session_factory=factory)
    with factory.begin() as database_session:
        database_session.add(AnalysisRun(repository_id=repository_id))

    assert (
        postgres_session.scalar(
            text("SELECT status FROM analysis_runs WHERE id = :run_id"),
            {"run_id": first_run_id},
        )
        == "failed"
    )


def test_status_transition_validation_and_stale_update_rejection(
    postgres_session: Connection,
) -> None:
    _, run_id = _create_run(postgres_session, 705)
    factory = _session_factory(postgres_session)

    with pytest.raises(InvalidRunTransition):
        transition_run_status(run_id, "queued", "completed", session_factory=factory)

    transition_run_status(run_id, "queued", "running", session_factory=factory)
    with pytest.raises(RunStateConflict):
        transition_run_status(run_id, "queued", "failed", session_factory=factory)

    transition_run_status(
        run_id,
        "running",
        "failed",
        session_factory=factory,
        error_code="analysis_failed",
        error_message="Analysis failed.",
    )
    row = postgres_session.execute(
        text(
            "SELECT status, started_at, completed_at, error_code, error_message "
            "FROM analysis_runs WHERE id = :run_id"
        ),
        {"run_id": run_id},
    ).one()
    assert row.status == "failed"
    assert row.started_at is not None
    assert row.completed_at is not None
    assert row.error_code == "analysis_failed"
    assert row.error_message == "Analysis failed."
    with pytest.raises(InvalidRunTransition):
        transition_run_status(run_id, "failed", "running", session_factory=factory)

    _, completed_run_id = _create_run(postgres_session, 713)
    transition_run_status(
        completed_run_id, "queued", "running", session_factory=factory
    )
    transition_run_status(
        completed_run_id, "running", "completed", session_factory=factory
    )
    assert (
        postgres_session.scalar(
            text("SELECT completed_at FROM analysis_runs WHERE id = :run_id"),
            {"run_id": completed_run_id},
        )
        is not None
    )


def test_stage_updates_allow_repeats_and_skips_but_reject_regressions(
    postgres_session: Connection,
) -> None:
    _, run_id = _create_run(postgres_session, 706)
    factory = _session_factory(postgres_session)
    transition_run_status(run_id, "queued", "running", session_factory=factory)

    set_run_stage(run_id, "cloning", session_factory=factory)
    set_run_stage(run_id, "cloning", session_factory=factory)
    set_run_stage(run_id, "security", session_factory=factory)
    with pytest.raises(RunStateConflict):
        set_run_stage(run_id, "parsing", session_factory=factory)
    with pytest.raises(ValueError):
        set_run_stage(run_id, "completed", session_factory=factory)
    transition_run_status(run_id, "running", "failed", session_factory=factory)
    with pytest.raises(RunStateConflict):
        set_run_stage(run_id, "cleanup", session_factory=factory)

    assert (
        postgres_session.scalar(
            text("SELECT stage FROM analysis_runs WHERE id = :run_id"),
            {"run_id": run_id},
        )
        == "security"
    )


def test_reconciliation_fails_active_runs_once_and_preserves_terminal_runs(
    postgres_session: Connection,
) -> None:
    _, queued_id = _create_run(postgres_session, 707)
    _, running_id = _create_run(
        postgres_session, 708, status="running", stage="parsing"
    )
    _, completed_id = _create_run(
        postgres_session, 709, status="completed", stage="cleanup"
    )
    _, failed_id = _create_run(postgres_session, 710, status="failed", stage="security")
    factory = _session_factory(postgres_session)

    assert set(reconcile_interrupted_runs(factory)) == {queued_id, running_id}
    assert reconcile_interrupted_runs(factory) == ()

    rows = postgres_session.execute(
        text(
            "SELECT id, status, stage, error_code, error_message, completed_at "
            "FROM analysis_runs WHERE id IN "
            "(:queued_id, :running_id, :completed_id, :failed_id)"
        ),
        {
            "queued_id": queued_id,
            "running_id": running_id,
            "completed_id": completed_id,
            "failed_id": failed_id,
        },
    ).mappings()
    runs = {row["id"]: row for row in rows}
    for run_id in (queued_id, running_id):
        assert runs[run_id]["status"] == "failed"
        assert runs[run_id]["error_code"] == INTERRUPTED_ERROR_CODE
        assert runs[run_id]["error_message"] == INTERRUPTED_ERROR_MESSAGE
        assert runs[run_id]["completed_at"] is not None
    assert runs[queued_id]["stage"] is None
    assert runs[running_id]["stage"] == "parsing"
    assert runs[completed_id]["status"] == "completed"
    assert runs[failed_id]["status"] == "failed"
    assert runs[failed_id]["error_code"] is None


@pytest.fixture
def real_lifespan_reconciliation(
    postgres_session: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import main

    factory = _session_factory(postgres_session)
    monkeypatch.setattr(
        main,
        "reconcile_interrupted_runs",
        lambda: reconcile_interrupted_runs(factory),
    )


def test_real_app_lifespan_reconciles_using_test_database(
    postgres_session: Connection,
    real_lifespan_reconciliation: None,
) -> None:
    from app.main import app

    _, queued_id = _create_run(postgres_session, 711)
    _, running_id = _create_run(
        postgres_session, 712, status="running", stage="metrics"
    )

    with TestClient(app):
        pass

    statuses = postgres_session.execute(
        text("SELECT id, status FROM analysis_runs WHERE id IN (:queued, :running)"),
        {"queued": queued_id, "running": running_id},
    ).all()
    assert {row.status for row in statuses} == {"failed"}
