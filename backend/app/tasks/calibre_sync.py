"""Calibre library import — the on-demand "Import new books" task.

Reads the configured Calibre library read-only and imports unseen cookbooks into the
v2 DB (`app.services.calibre`), tracked as a TaskRun so a misconfigured library leaves
a FAILED record with the error rather than failing silently. Triggered from the admin
Tasks tab (`POST /api/tasks/calibre-sync`) and executed on the Celery worker; the CLI
(`scripts/sync_calibre.py`) still calls the services directly.
"""

import logging

from app.config import settings
from app.db import SessionLocal
from app.services.calibre import read_calibre_books, sync_calibre
from app.tasks.celery_app import celery_app
from app.tasks.runs import complete_run, fail_run, start_run

logger = logging.getLogger(__name__)


def enqueue_calibre_sync(run_id: str) -> None:
    """Dispatch the Calibre sync to the Celery worker — the seam the admin Tasks trigger
    goes through (and tests stub), so it runs off the request thread."""
    calibre_sync_task.delay(run_id)


def run_calibre_sync() -> dict:
    """Read the configured Calibre library and import unseen books, returning the
    created/skipped/excluded titles. Raises (FileNotFoundError) if the library's
    metadata.db is absent — recorded as a FAILED run by the task wrapper."""
    books = read_calibre_books(
        settings.calibre_library_path,
        tag=settings.calibre_sync_tag,
        book_formats=settings.calibre_sync_formats,
    )
    with SessionLocal() as session:
        result = sync_calibre(session, books)
    return {
        "created": result.created,
        "skipped": result.skipped,
        "excluded": result.excluded,
    }


@celery_app.task(name="sync_calibre_library")
def calibre_sync_task(run_id: str) -> dict:
    """Run the import as a tracked TaskRun: RUNNING → DONE with the import result
    in `detail`, or FAILED (with the error) if the library can't be read."""
    start_run(run_id)
    try:
        detail = run_calibre_sync()
    except Exception as exc:
        fail_run(run_id, exc)
        raise
    complete_run(run_id, detail)
    return detail
