"""The stale-run reaper: a worker that dies mid-job leaves its run RUNNING forever, so
a fresh worker sweeps the abandoned ones on start."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import sqlite_vec
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings as app_settings
from app.models import Base, TaskRun
from app.models.enums import TaskStatus, TaskType
from app.tasks.runs import reap_stale_runs


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.sqlite3'}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _configure(dbapi_conn: Any, _record: Any) -> None:
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.tasks.runs.SessionLocal", factory)
    yield factory
    engine.dispose()


def _run(status: TaskStatus, age_hours: float) -> TaskRun:
    return TaskRun(
        task_type=TaskType.EXTRACTION,
        status=status,
        created_at=datetime.now(UTC) - timedelta(hours=age_hours),
    )


def test_reaps_only_abandoned_runs(db: sessionmaker[Session]) -> None:
    """Old QUEUED/RUNNING rows are abandoned and get failed. A run still inside the
    window is left alone (a big book legitimately runs for a while), and so is REVIEW —
    that one is waiting on a person, not on a dead worker."""
    stale_running = _run(TaskStatus.RUNNING, 48)
    stale_queued = _run(TaskStatus.QUEUED, 7)
    fresh_running = _run(TaskStatus.RUNNING, 1)
    old_review = _run(TaskStatus.REVIEW, 500)
    old_done = _run(TaskStatus.DONE, 500)

    with db() as s:
        s.add_all([stale_running, stale_queued, fresh_running, old_review, old_done])
        s.commit()
        ids = {
            "stale_running": stale_running.id,
            "stale_queued": stale_queued.id,
            "fresh_running": fresh_running.id,
            "old_review": old_review.id,
            "old_done": old_done.id,
        }

    assert reap_stale_runs() == 2

    with db() as s:
        rows = {name: s.get(TaskRun, run_id) for name, run_id in ids.items()}
        assert all(row is not None for row in rows.values())
        statuses = {name: row.status for name, row in rows.items() if row is not None}

    assert statuses == {
        "stale_running": TaskStatus.FAILED,
        "stale_queued": TaskStatus.FAILED,
        "fresh_running": TaskStatus.RUNNING,
        "old_review": TaskStatus.REVIEW,
        "old_done": TaskStatus.DONE,
    }


def test_reaped_run_records_why_and_when(db: sessionmaker[Session]) -> None:
    with db() as s:
        run = _run(TaskStatus.RUNNING, 48)
        s.add(run)
        s.commit()
        run_id = run.id

    reap_stale_runs()

    with db() as s:
        reaped = s.get(TaskRun, uuid.UUID(str(run_id)))
        assert reaped is not None
        assert reaped.completed_at is not None
        assert any("Abandoned" in e for e in reaped.errors)


def test_reaper_is_a_no_op_when_nothing_is_stale(db: sessionmaker[Session]) -> None:
    with db() as s:
        s.add(_run(TaskStatus.RUNNING, app_settings.stale_run_after_hours - 1))
        s.commit()

    assert reap_stale_runs() == 0
