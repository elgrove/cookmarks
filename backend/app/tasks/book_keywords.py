"""Library-wide book-keyword backfill — the on-demand "Generate book keywords" task.

Wraps the per-book generation (`app.services.book_keywords`) in a sweep over the
library: tag every extracted book that's missing keywords, or `regenerate` to re-tag
all of them. Exposed three ways through one code path — the admin Tasks tab
(`POST /api/tasks/book-keywords`), the CLI (`scripts/backfill_book_keywords.py`), and
the Celery worker.
"""

import logging

from sqlalchemy import select

from app.db import SessionLocal
from app.models.book import Book
from app.services.book_keywords import generate_book_keywords
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def enqueue_backfill_book_keywords(regenerate: bool) -> None:
    """Dispatch the backfill to the Celery worker — the single seam the admin Tasks
    trigger goes through (and tests stub), so it runs off the request thread."""
    backfill_book_keywords_task.delay(regenerate)


def backfill_book_keywords(regenerate: bool = False) -> int:
    """Generate keywords for extracted books, returning how many were tagged. By
    default only books that have recipes but no keywords yet; `regenerate` re-tags
    every book that has recipes. A no-op per book when no AI provider is configured,
    so it's always safe to run."""
    stmt = select(Book).where(Book.recipes.any())
    if not regenerate:
        stmt = stmt.where(~Book.keywords.any())

    tagged = 0
    with SessionLocal() as session:
        for book in session.scalars(stmt).all():
            if generate_book_keywords(session, book):
                tagged += 1
        session.commit()

    logger.info(f"Book-keyword backfill tagged {tagged} book(s) (regenerate={regenerate})")
    return tagged


@celery_app.task(name="backfill_book_keywords")
def backfill_book_keywords_task(regenerate: bool = False) -> int:
    return backfill_book_keywords(regenerate)
