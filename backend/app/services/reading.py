"""How far through a book a user is, and in which mode — the data behind the home
page's continue strip and the book page's resume actions.

Progress is measured in recipes whichever way the book is being read: the reader
reports the recipes its pages carry it past, and the recipe walk reports the one being
read. Both land in the same anchor, which only ever moves forwards."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.models.base import utcnow
from app.models.book_reading import BookReading
from app.models.enums import ReadingMode
from app.models.recipe import Recipe
from app.services.views import record_view


def get_reading(session: Session, user_id: uuid.UUID, book_id: uuid.UUID) -> BookReading | None:
    return session.scalar(
        select(BookReading).where(
            BookReading.user_id == user_id, BookReading.book_id == book_id
        )
    )


def recipe_count(session: Session, book_id: uuid.UUID) -> int:
    return session.scalar(select(func.count(Recipe.id)).where(Recipe.book_id == book_id)) or 0


def _order_of(session: Session, recipe_id: uuid.UUID | None) -> int | None:
    if recipe_id is None:
        return None
    return session.scalar(select(Recipe.order).where(Recipe.id == recipe_id))


def fraction(finished: bool, anchor_order: int | None, total: int) -> float:
    """How far through the book, as a fraction: the anchor recipe's place in book order
    out of the book's recipes. A finished book is all the way through whatever the
    anchor says; one opened but not yet carried past a recipe is at the start."""
    if finished:
        return 1.0
    if anchor_order is None or total == 0:
        return 0.0
    return min(1.0, (anchor_order + 1) / total)


def progress_of(session: Session, reading: BookReading | None, total: int) -> float:
    if reading is None:
        return 0.0
    return fraction(reading.finished, _order_of(session, reading.anchor_recipe_id), total)


def reading_positions(
    session: Session, user_id: uuid.UUID
) -> dict[uuid.UUID, tuple[bool, int | None]]:
    """Every book the caller has started, as book id → (finished, anchor order) — one
    query for the whole library, so the books index doesn't go per-book."""
    anchor = aliased(Recipe)
    rows = session.execute(
        select(BookReading.book_id, BookReading.finished, anchor.order)
        .outerjoin(anchor, anchor.id == BookReading.anchor_recipe_id)
        .where(BookReading.user_id == user_id)
    ).all()
    return {book_id: (finished, order) for book_id, finished, order in rows}


def is_complete(session: Session, reading: BookReading, total: int) -> bool:
    """Nothing left to continue: declared read, or anchored on the last recipe."""
    return reading.finished or (total > 0 and progress_of(session, reading, total) >= 1.0)


def touch_reading(
    session: Session,
    user_id: uuid.UUID,
    book_id: uuid.UUID,
    mode: ReadingMode,
    *,
    recipe_id: uuid.UUID | None = None,
    location: str | None = None,
) -> BookReading:
    """Record that the user is reading this book, now, in `mode`. A recipe reached moves
    the anchor forwards — never back, so revisiting an earlier one doesn't undo progress
    — and counts as a view of that recipe."""
    reading = get_reading(session, user_id, book_id)
    if reading is None:
        reading = BookReading(user_id=user_id, book_id=book_id)
        session.add(reading)
    reading.mode = mode
    if location is not None:
        reading.location = location
    if recipe_id is not None:
        record_view(session, user_id, recipe_id)
        reached = _order_of(session, recipe_id)
        current = _order_of(session, reading.anchor_recipe_id)
        if reached is not None and (current is None or reached > current):
            reading.anchor_recipe_id = recipe_id
    reading.last_read_at = utcnow()
    session.commit()
    return reading


def finish_reading(session: Session, user_id: uuid.UUID, book_id: uuid.UUID) -> None:
    """Declare the book read: however it was being read, it leaves the continue strip."""
    reading = get_reading(session, user_id, book_id)
    if reading is None:
        reading = BookReading(user_id=user_id, book_id=book_id)
        session.add(reading)
    reading.finished = True
    reading.last_read_at = utcnow()
    session.commit()


def forget_reading(session: Session, user_id: uuid.UUID, book_id: uuid.UUID) -> None:
    reading = get_reading(session, user_id, book_id)
    if reading is not None:
        session.delete(reading)
        session.commit()


def resume_recipe(session: Session, reading: BookReading | None, book_id: uuid.UUID) -> Recipe | None:
    """Where reading the recipes picks up: the furthest one reached, or the book's first
    if it has never been read."""
    if reading is not None and reading.anchor_recipe_id is not None:
        return session.get(Recipe, reading.anchor_recipe_id)
    return session.scalar(
        select(Recipe).where(Recipe.book_id == book_id).order_by(Recipe.order.asc()).limit(1)
    )
