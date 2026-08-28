"""AI-assisted keyword dedup — the on-demand "Deduplicate keywords" task.

Wraps a dedup pass over the shared vocabulary (`app.services.keyword_dedup`) so it runs
off the request thread. Triggered from the admin Tasks tab (`POST /api/tasks/dedup-keywords`),
weekly by Celery beat, and executed on the Celery worker. The AI stage only proposes merges
for a rotating window of the vocabulary, so successive runs sweep the whole of it: the
window's end is carried on the run's `detail` and picked up by the next run.
"""

import logging

from sqlalchemy import select

from app.db import SessionLocal
from app.models.enums import TaskStatus, TaskType
from app.models.task_run import TaskRun
from app.services.keyword_dedup import DedupResult, deduplicate_keywords
from app.tasks.celery_app import celery_app
from app.tasks.runs import complete_run, create_task_run, fail_run, start_run

logger = logging.getLogger(__name__)

# How far back to look for a run that recorded a cursor before starting the sweep over.
_CURSOR_LOOKBACK = 20


def enqueue_dedup_keywords(run_id: str) -> None:
    """Dispatch the dedup to the Celery worker — the single seam the admin Tasks
    trigger goes through (and tests stub), so it runs off the request thread. `run_id`
    is the queued TaskRun the worker transitions as it runs."""
    dedup_keywords_task.delay(run_id)


def _last_cursor() -> str | None:
    """Where the most recent finished run's candidate window ended, so this run takes the
    next one. The newest run that *recorded* a cursor wins, not simply the newest run: a
    pass with no provider or an empty vocabulary records none, and letting that reset the
    sweep to the start of the vocabulary would leave its tail never deduplicated. None
    (start of the vocabulary) when no run has recorded a cursor yet."""
    with SessionLocal() as session:
        runs = session.scalars(
            select(TaskRun)
            .where(TaskRun.task_type == TaskType.KEYWORD_DEDUP, TaskRun.status == TaskStatus.DONE)
            .order_by(TaskRun.completed_at.desc(), TaskRun.created_at.desc())
            .limit(_CURSOR_LOOKBACK)
        ).all()
        for run in runs:
            cursor = run.detail.get("cursor_to")
            if isinstance(cursor, str):
                return cursor
    return None


def run_dedup(cursor: str | None = None) -> DedupResult:
    """Run one dedup pass in its own session and commit. A no-op when no AI provider is
    configured, so it's always safe to run."""
    with SessionLocal() as session:
        result = deduplicate_keywords(session, cursor)
        session.commit()
    return result


@celery_app.task(name="dedup_keywords")
def dedup_keywords_task(run_id: str) -> dict[str, object]:
    """Run the dedup as a tracked TaskRun: RUNNING → DONE with the merge counts in
    `detail`, or FAILED (with the error) if the pass raises."""
    start_run(run_id)
    try:
        result = run_dedup(_last_cursor())
    except Exception as exc:
        fail_run(run_id, exc)
        raise
    detail: dict[str, object] = {
        "keywords_in": result.keywords_in,
        "merges_applied": result.merges_applied,
        "keywords_removed": result.keywords_removed,
        "pre_merges": result.pre_merges,
        "ai_merges": result.ai_merges,
        "ai_truncated": result.ai_truncated,
        "candidates": result.candidates,
        "cursor_from": result.cursor_from,
        "cursor_to": result.cursor_to,
    }
    complete_run(run_id, detail, usage=result.usage)
    return detail


@celery_app.task(name="scheduled_dedup_keywords")
def scheduled_dedup_keywords() -> None:
    """The weekly beat entry point: record its own run, then hand it to the ordinary
    task, so a scheduled dedup shows up in the admin history like any other."""
    with SessionLocal() as session:
        run = create_task_run(session, TaskType.KEYWORD_DEDUP, detail={"scheduled": True})
    dedup_keywords_task.delay(str(run.id))
