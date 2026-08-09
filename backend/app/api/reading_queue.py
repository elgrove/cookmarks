import uuid
from collections.abc import Iterable

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.covers import has_cover
from app.db import SessionDep
from app.models.book import Book
from app.models.book_reading import BookReading
from app.models.reading_queue import ReadingQueueItem
from app.models.recipe import Recipe
from app.schemas.reading_queue import QueuedBook, QueueState

router = APIRouter(tags=["reading-queue"])


def queued_books(
    session: Session,
    user_id: uuid.UUID,
    exclude: Iterable[uuid.UUID] = (),
    limit: int | None = None,
) -> list[QueuedBook]:
    """The caller's queue, newest-queued first. A book whose reading is finished has
    been read, not un-queued — it drops out here at read time rather than via any
    lifecycle hook, so marking it unread brings it straight back."""
    finished = exists().where(
        BookReading.book_id == Book.id,
        BookReading.user_id == user_id,
        BookReading.finished.is_(True),
    )
    query = (
        select(Book, func.count(Recipe.id))
        .join(ReadingQueueItem, ReadingQueueItem.book_id == Book.id)
        .outerjoin(Recipe, Recipe.book_id == Book.id)
        .where(ReadingQueueItem.user_id == user_id, ~finished)
        .group_by(Book.id)
        .order_by(ReadingQueueItem.created_at.desc())
    )
    if exclude:
        query = query.where(Book.id.not_in(list(exclude)))
    if limit is not None:
        query = query.limit(limit)
    return [
        QueuedBook(
            id=book.id,
            title=book.title,
            author=book.author,
            has_cover=has_cover(book),
            recipe_count=recipe_count,
        )
        for book, recipe_count in session.execute(query).all()
    ]


def is_queued(session: Session, user_id: uuid.UUID, book_id: uuid.UUID) -> bool:
    return (
        session.scalar(
            select(ReadingQueueItem.id).where(
                ReadingQueueItem.user_id == user_id, ReadingQueueItem.book_id == book_id
            )
        )
        is not None
    )


@router.get("/reading-queue", response_model=list[QueuedBook])
def list_queue(session: SessionDep, user: CurrentUser) -> list[QueuedBook]:
    return queued_books(session, user.id)


@router.put("/books/{book_id}/queue", response_model=QueueState)
def queue_book(book_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> QueueState:
    if session.get(Book, book_id) is None:
        raise HTTPException(status_code=404, detail="book not found")
    if not is_queued(session, user.id, book_id):
        session.add(ReadingQueueItem(user_id=user.id, book_id=book_id))
        session.commit()
    return QueueState(queued=True)


@router.delete("/books/{book_id}/queue", response_model=QueueState)
def unqueue_book(book_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> QueueState:
    if session.get(Book, book_id) is None:
        raise HTTPException(status_code=404, detail="book not found")
    session.execute(
        delete(ReadingQueueItem).where(
            ReadingQueueItem.user_id == user.id, ReadingQueueItem.book_id == book_id
        )
    )
    session.commit()
    return QueueState(queued=False)
