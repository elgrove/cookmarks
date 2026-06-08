from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.db import SessionDep
from app.models.book import Book
from app.models.recipe import Keyword
from app.schemas.tasks import BookKeywordTaskRequest, TaskRunAck
from app.tasks.book_keywords import enqueue_backfill_book_keywords
from app.tasks.keyword_dedup import enqueue_dedup_keywords

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "/book-keywords",
    response_model=TaskRunAck,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_book_keywords(body: BookKeywordTaskRequest, session: SessionDep) -> TaskRunAck:
    """Queue AI generation of book-level keywords across the library. By default tags
    only extracted books that have none yet; `regenerate` re-tags every extracted book.
    Fire-and-forget: dispatches to the worker and returns how many books are eligible
    (the count the task will work through), not a live progress handle."""
    stmt = select(func.count()).select_from(Book).where(Book.recipes.any())
    if not body.regenerate:
        stmt = stmt.where(~Book.keywords.any())
    eligible = session.scalar(stmt) or 0

    enqueue_backfill_book_keywords(body.regenerate)
    return TaskRunAck(task="book_keywords", status="queued", queued=eligible)


@router.post(
    "/dedup-keywords",
    response_model=TaskRunAck,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_dedup_keywords(session: SessionDep) -> TaskRunAck:
    """Queue an AI-assisted dedup of the whole keyword vocabulary, merging near-duplicate
    tags ("Veggie" -> "Vegetarian") across recipes and books. Fire-and-forget: dispatches
    to the worker and returns the vocabulary size it will analyse, not a live handle."""
    vocabulary = session.scalar(select(func.count()).select_from(Keyword)) or 0
    enqueue_dedup_keywords()
    return TaskRunAck(task="keyword_dedup", status="queued", queued=vocabulary)
