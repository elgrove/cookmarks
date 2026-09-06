"""Shared task-run lifecycle helpers.

A `TaskRun` records every background job — not just extraction. The trigger endpoint
creates a QUEUED row (`create_task_run`); the worker then drives it RUNNING → DONE
(`start_run` / `complete_run`) or FAILED (`fail_run`), writing the job's metrics into
`detail`. Extraction has its own richer path in `app.tasks.extraction`; this is the seam
the simpler maintenance tasks (book-keywords, dedup, Calibre sync) go through.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.enums import TaskStatus, TaskType
from app.models.task_run import TaskRun
from app.services.ai import Usage

logger = logging.getLogger(__name__)


def create_task_run(
    session: Session, task_type: TaskType, *, detail: dict | None = None
) -> TaskRun:
    """Record a freshly-queued run on the caller's session and commit it, so a trigger is
    visible in the history even before a worker picks it up. Returns the persisted row."""
    run = TaskRun(task_type=task_type, status=TaskStatus.QUEUED, detail=detail or {})
    session.add(run)
    session.commit()
    return run


def start_run(run_id: str) -> None:
    """Mark a run RUNNING and stamp `started_at` as the worker begins it."""
    with SessionLocal() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        if run is None:
            return
        run.status = TaskStatus.RUNNING
        run.started_at = datetime.now(UTC)
        session.commit()


def set_waiting(run_id: str, detail: dict | None = None) -> None:
    """Mark a run WAITING: locally healthy, blocked on remote work (Gemini Batch).

    Merges `detail` so progress/next-poll/last-error stay visible while waiting."""
    with SessionLocal() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        if run is None:
            return
        run.status = TaskStatus.WAITING
        if detail:
            run.detail = {**run.detail, **detail}
        session.commit()


def set_running(run_id: str, detail: dict | None = None) -> None:
    """Move a WAITING run back to RUNNING while the worker downloads/applies results."""
    with SessionLocal() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        if run is None:
            return
        run.status = TaskStatus.RUNNING
        if detail:
            run.detail = {**run.detail, **detail}
        session.commit()


def merge_detail(run_id: str, detail: dict) -> None:
    """Merge progress metrics into a run's `detail` without changing its status."""
    with SessionLocal() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        if run is None:
            return
        run.detail = {**run.detail, **detail}
        session.commit()


def complete_run(run_id: str, detail: dict | None = None, usage: Usage | None = None) -> None:
    """Mark a run DONE, stamp `completed_at`, and merge in the job's result metrics —
    plus its token/cost accounting when the job made AI calls."""
    with SessionLocal() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        if run is None:
            return
        run.status = TaskStatus.DONE
        run.completed_at = datetime.now(UTC)
        if detail:
            run.detail = {**run.detail, **detail}
        if usage is not None:
            run.cost_usd = usage.cost_usd
            run.input_tokens = usage.input_tokens
            run.output_tokens = usage.output_tokens
        session.commit()


def reap_stale_runs() -> int:
    """Fail runs left QUEUED or RUNNING by a worker that died or restarted mid-job, so
    the history stops showing long-dead jobs as in-flight. Age is measured from
    `created_at` — a run that never started has no `started_at` — and the threshold is
    deliberately generous, since a big book legitimately runs for a while. REVIEW and
    WAITING are left alone: they're waiting on a person or a remote batch job, not
    abandoned. Returns how many were reaped."""
    cutoff = datetime.now(UTC) - timedelta(hours=settings.stale_run_after_hours)
    with SessionLocal() as session:
        stale = session.scalars(
            select(TaskRun).where(
                TaskRun.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]),
                TaskRun.created_at < cutoff,
            )
        ).all()
        for run in stale:
            run.status = TaskStatus.FAILED
            run.errors = [*run.errors, "Abandoned: no worker finished this run"]
            run.completed_at = datetime.now(UTC)
        session.commit()

    if stale:
        logger.info(f"Reaped {len(stale)} stale task runs")
    return len(stale)


def fail_run(run_id: str, exc: Exception) -> None:
    """Record a crashed run: status FAILED, the error appended, completed stamped — so a
    worker exception leaves an honest record instead of a run wedged in RUNNING forever.
    Best-effort: a failure here must not mask the original exception."""
    try:
        with SessionLocal() as session:
            run = session.get(TaskRun, uuid.UUID(run_id))
            if run is None:
                return
            run.status = TaskStatus.FAILED
            run.errors = [*run.errors, str(exc)]
            run.completed_at = datetime.now(UTC)
            session.commit()
    except Exception:
        logger.exception(f"Failed to mark task run {run_id} as failed")


def fail_with_detail(run_id: str, detail: dict, exc: Exception) -> None:
    """Finish a run FAILED in one session: merge the final metrics, record the
    error and stamp completion — for jobs whose partial results must survive
    alongside the terminal state (the backfill keeps applied recipes)."""
    with SessionLocal() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        if run is None:
            return
        run.status = TaskStatus.FAILED
        run.errors = [*run.errors, str(exc)]
        run.completed_at = datetime.now(UTC)
        run.detail = {**run.detail, **detail}
        session.commit()
