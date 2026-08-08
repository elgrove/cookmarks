"""Recording which recipes a user has seen, and counting them per book — the
data behind a book's read percentage."""

import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.base import as_utc, utcnow
from app.models.recipe import Recipe
from app.models.recipe_view import RecipeView

# Re-opening a recipe within this window is the same sitting: only the timestamp
# moves. Otherwise scrubbing prev/next through a book inflates counts that mean
# nothing. The percentage counts distinct rows, so it is unaffected either way.
VIEW_WINDOW = timedelta(minutes=30)


def record_view(session: Session, user_id: uuid.UUID, recipe_id: uuid.UUID) -> RecipeView:
    """Record that the user has opened the recipe, creating the row on first sight."""
    view = session.scalar(
        select(RecipeView).where(
            RecipeView.user_id == user_id, RecipeView.recipe_id == recipe_id
        )
    )
    now = utcnow()
    if view is None:
        view = RecipeView(user_id=user_id, recipe_id=recipe_id, last_viewed_at=now)
        session.add(view)
    else:
        if as_utc(view.last_viewed_at) < now - VIEW_WINDOW:
            view.view_count += 1
        view.last_viewed_at = now
    session.commit()
    return view


def forget_view(session: Session, user_id: uuid.UUID, recipe_id: uuid.UUID) -> None:
    """Drop the user's view of a recipe — the undo for one opened by accident. The
    sitting count goes with it: an unread recipe has never been read."""
    session.execute(
        delete(RecipeView).where(
            RecipeView.user_id == user_id, RecipeView.recipe_id == recipe_id
        )
    )
    session.commit()


def seen_recipe_ids(
    session: Session, user_id: uuid.UUID, recipe_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    """Which of these recipes the user has seen — one query for a whole page of rows,
    so a list can mark its read entries without an N+1."""
    if not recipe_ids:
        return set()
    return set(
        session.scalars(
            select(RecipeView.recipe_id).where(
                RecipeView.user_id == user_id, RecipeView.recipe_id.in_(recipe_ids)
            )
        ).all()
    )


def mark_book_seen(session: Session, user_id: uuid.UUID, book_id: uuid.UUID) -> None:
    """Record every recipe in the book as seen. Recipes already seen keep their
    existing sitting count and timestamp — marking the book read is not a re-read."""
    already_seen = select(RecipeView.recipe_id).where(RecipeView.user_id == user_id)
    unseen = session.scalars(
        select(Recipe.id).where(Recipe.book_id == book_id, Recipe.id.notin_(already_seen))
    ).all()
    session.add_all([RecipeView(user_id=user_id, recipe_id=rid) for rid in unseen])
    session.commit()


def clear_book_views(session: Session, user_id: uuid.UUID, book_id: uuid.UUID) -> None:
    """Forget the user's reading of a whole book, returning it to 0%."""
    session.execute(
        delete(RecipeView).where(
            RecipeView.user_id == user_id,
            RecipeView.recipe_id.in_(select(Recipe.id).where(Recipe.book_id == book_id)),
        )
    )
    session.commit()


def seen_counts(
    session: Session, user_id: uuid.UUID, book_ids: Sequence[uuid.UUID] | None = None
) -> dict[uuid.UUID, int]:
    """How many of each book's recipes the user has seen, keyed by book id (books with
    none are absent). One grouped query for the whole library, so the books list stays
    a fixed number of queries rather than N+1."""
    query = (
        select(Recipe.book_id, func.count(RecipeView.id))
        .join(RecipeView, RecipeView.recipe_id == Recipe.id)
        .where(RecipeView.user_id == user_id)
        .group_by(Recipe.book_id)
    )
    if book_ids is not None:
        query = query.where(Recipe.book_id.in_(book_ids))
    return dict(session.execute(query).tuples().all())


def seen_count(session: Session, user_id: uuid.UUID, book_id: uuid.UUID) -> int:
    """How many of one book's recipes the user has seen."""
    return seen_counts(session, user_id, [book_id]).get(book_id, 0)
