"""Recording which recipes a user has seen, and counting them per book — the
data behind a book's read percentage."""

import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import func, select
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
