"""AI-assisted keyword dedup — the on-demand "Deduplicate keywords" task.

Wraps the one-shot dedup over the whole shared vocabulary (`app.services.keyword_dedup`)
so it runs off the request thread. Triggered from the admin Tasks tab
(`POST /api/tasks/dedup-keywords`) and executed on the Celery worker.
"""

import logging

from app.db import SessionLocal
from app.services.keyword_dedup import DedupResult, deduplicate_keywords
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def enqueue_dedup_keywords() -> None:
    """Dispatch the dedup to the Celery worker — the single seam the admin Tasks
    trigger goes through (and tests stub), so it runs off the request thread."""
    dedup_keywords_task.delay()


def run_dedup() -> DedupResult:
    """Run one dedup pass in its own session and commit. A no-op when no AI provider is
    configured, so it's always safe to run."""
    with SessionLocal() as session:
        result = deduplicate_keywords(session)
        session.commit()
    return result


@celery_app.task(name="dedup_keywords")
def dedup_keywords_task() -> dict[str, int]:
    result = run_dedup()
    return {
        "keywords_in": result.keywords_in,
        "merges_applied": result.merges_applied,
        "keywords_removed": result.keywords_removed,
    }
