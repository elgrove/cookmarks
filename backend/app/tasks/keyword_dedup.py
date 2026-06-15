"""AI-assisted keyword dedup — the on-demand "Deduplicate keywords" task.

Wraps the one-shot dedup over the whole shared vocabulary (`app.services.keyword_dedup`)
so it runs off the request thread. Triggered from the admin Tasks tab
(`POST /api/tasks/dedup-keywords`) and executed on the Celery worker.
"""

import logging

from app.db import SessionLocal
from app.services.keyword_dedup import DedupResult, deduplicate_keywords
from app.tasks.celery_app import celery_app
from app.tasks.runs import complete_run, fail_run, start_run

logger = logging.getLogger(__name__)


def enqueue_dedup_keywords(run_id: str) -> None:
    """Dispatch the dedup to the Celery worker — the single seam the admin Tasks
    trigger goes through (and tests stub), so it runs off the request thread. `run_id`
    is the queued TaskRun the worker transitions as it runs."""
    dedup_keywords_task.delay(run_id)


def run_dedup() -> DedupResult:
    """Run one dedup pass in its own session and commit. A no-op when no AI provider is
    configured, so it's always safe to run."""
    with SessionLocal() as session:
        result = deduplicate_keywords(session)
        session.commit()
    return result


@celery_app.task(name="dedup_keywords")
def dedup_keywords_task(run_id: str) -> dict[str, int]:
    """Run the dedup as a tracked TaskRun: RUNNING → DONE with the merge counts in
    `detail`, or FAILED (with the error) if the pass raises."""
    start_run(run_id)
    try:
        result = run_dedup()
    except Exception as exc:
        fail_run(run_id, exc)
        raise
    detail = {
        "keywords_in": result.keywords_in,
        "merges_applied": result.merges_applied,
        "keywords_removed": result.keywords_removed,
    }
    complete_run(run_id, detail)
    return detail
