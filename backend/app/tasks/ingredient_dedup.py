"""Tracked worker tasks for canonical-ingredient deduplication."""

from sqlalchemy import select

from app.db import SessionLocal
from app.models.enums import TaskStatus, TaskType
from app.models.task_run import TaskRun
from app.services.ingredient_dedup import DedupResult, deduplicate_ingredients
from app.tasks.celery_app import celery_app
from app.tasks.runs import complete_run, create_task_run, fail_run, start_run

_CURSOR_LOOKBACK = 20


def enqueue_dedup_ingredients(run_id: str) -> None:
    """Send an already-recorded ingredient deduplication run to the worker."""
    dedup_ingredients_task.delay(run_id)


def _last_cursor() -> str | None:
    """Get the newest completed ingredient pass that recorded a candidate cursor."""
    with SessionLocal() as session:
        runs = session.scalars(
            select(TaskRun)
            .where(
                TaskRun.task_type == TaskType.INGREDIENT_DEDUP, TaskRun.status == TaskStatus.DONE
            )
            .order_by(TaskRun.completed_at.desc(), TaskRun.created_at.desc())
            .limit(_CURSOR_LOOKBACK)
        ).all()
        for run in runs:
            cursor = run.detail.get("cursor_to")
            if isinstance(cursor, str):
                return cursor
    return None


def run_dedup(cursor: str | None = None) -> DedupResult:
    """Run and commit one canonical-ingredient deduplication pass."""
    with SessionLocal() as session:
        result = deduplicate_ingredients(session, cursor)
        session.commit()
    return result


@celery_app.task(name="dedup_ingredients")
def dedup_ingredients_task(run_id: str) -> dict[str, object]:
    """Drive a run through RUNNING to DONE, retaining metrics and AI usage."""
    start_run(run_id)
    try:
        result = run_dedup(_last_cursor())
    except Exception as exc:
        fail_run(run_id, exc)
        raise
    detail: dict[str, object] = {
        "ingredients_in": result.ingredients_in,
        "merges_applied": result.merges_applied,
        "ingredients_removed": result.ingredients_removed,
        "pre_merges": result.pre_merges,
        "ai_merges": result.ai_merges,
        "ai_truncated": result.ai_truncated,
        "candidates": result.candidates,
        "cursor_from": result.cursor_from,
        "cursor_to": result.cursor_to,
    }
    complete_run(run_id, detail, usage=result.usage)
    return detail


@celery_app.task(name="scheduled_dedup_ingredients")
def scheduled_dedup_ingredients() -> None:
    """Record the weekly run before handing it to the ordinary worker task."""
    with SessionLocal() as session:
        run = create_task_run(session, TaskType.INGREDIENT_DEDUP, detail={"scheduled": True})
    dedup_ingredients_task.delay(str(run.id))
