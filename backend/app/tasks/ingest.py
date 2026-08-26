"""Book ingestion as a tracked background job.

The confirm endpoint records a QUEUED `TaskRun` carrying every ingest parameter in its
`detail`, so the Celery payload stays a bare run id like every other task here. The
worker then drives it RUNNING → DONE (or FAILED), adding the book to the Calibre
library, syncing it into the app, and optionally queueing extraction on the result.

A duplicate is a failure with a difference: the run records which book it clashed with,
which is what lets the UI offer "delete existing and replace" instead of a dead end.
"""

import logging
import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.models.book import Book
from app.models.task_run import TaskRun
from app.services.ingest import DuplicateBookError, run_ingest
from app.tasks.calibre_sync import run_calibre_sync
from app.tasks.celery_app import celery_app
from app.tasks.extraction import NotExtractableError, queue_extraction
from app.tasks.runs import complete_run, fail_run, start_run

logger = logging.getLogger(__name__)


def enqueue_ingest_book(run_id: str) -> None:
    """Dispatch an ingest to the Celery worker — the seam the confirm endpoint goes
    through (and tests stub), so the upload never rides the request thread."""
    ingest_book_task.delay(run_id)


def _run_detail(run_id: str) -> dict:
    with SessionLocal() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        return dict(run.detail) if run is not None else {}


def _fail_duplicate(run_id: str, exc: DuplicateBookError) -> None:
    """Fail the run naming the book already in the library. The Cookmarks book id goes
    into `detail` so the UI can offer replace; without a resolvable book (an entry the
    app has never synced) the message stands alone and no offer is made."""
    with SessionLocal() as session:
        book = session.scalars(select(Book).where(Book.calibre_id == exc.calibre_id)).first()
        book_id = str(book.id) if book is not None else None
    if book_id is not None:
        with SessionLocal() as session:
            run = session.get(TaskRun, uuid.UUID(run_id))
            if run is not None:
                run.detail = {**run.detail, "duplicate_of_book_id": book_id}
                session.commit()
    fail_run(run_id, exc)


@celery_app.task(name="ingest_book")
def ingest_book_task(run_id: str) -> dict:
    """Add the staged book to the library, sync it in, and queue extraction if asked."""
    start_run(run_id)
    params = _run_detail(run_id)
    try:
        replace_book_id = params.get("replace_book_id")
        outcome = run_ingest(
            params["staging_id"],
            params["title"],
            params["author"],
            replace_book_id=uuid.UUID(replace_book_id) if replace_book_id else None,
        )
        sync = run_calibre_sync()
    except DuplicateBookError as exc:
        _fail_duplicate(run_id, exc)
        raise
    except Exception as exc:
        fail_run(run_id, exc)
        raise

    extraction_queued = False
    skipped: str | None = None
    if params.get("extract"):
        extraction_queued, skipped = _queue_extraction(outcome.calibre_id)

    detail = {
        "title": outcome.title,
        "author": outcome.author,
        "format": outcome.format,
        "converted": outcome.converted,
        "calibre_id": outcome.calibre_id,
        "cover": outcome.cover,
        "replaced_calibre_id": outcome.replaced_calibre_id,
        "sync": {key: len(value) for key, value in sync.items()},
        "extraction_queued": extraction_queued,
        "extraction_skipped": skipped,
    }
    complete_run(run_id, detail)
    return detail


def _queue_extraction(calibre_id: int) -> tuple[bool, str | None]:
    """Queue extraction on the book the sync just produced, returning whether it was
    queued and, if not, why. Best-effort: the book is in the library either way, and a
    failure here must not fail an ingest that worked."""
    try:
        with SessionLocal() as session:
            book = session.scalars(select(Book).where(Book.calibre_id == calibre_id)).first()
            if book is None:
                logger.warning("Ingested book %d did not sync; extraction not queued", calibre_id)
                return False, "the book did not sync into the app"
            queue_extraction(session, book)
            return True, None
    except NotExtractableError as exc:
        return False, str(exc)
    except Exception:
        logger.exception("Could not queue extraction after ingesting %d", calibre_id)
        return False, "the extraction run could not be queued"
