import uuid
from datetime import date

from fastapi import APIRouter
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.covers import has_cover
from app.db import SessionDep
from app.models.book import Book
from app.models.recipe import Keyword, Recipe
from app.models.recipe_view import RecipeView
from app.schemas.home import BookFeature, ContinueBook, HomeData, RecentRecipe, Stats

CONTINUE_LIMIT = 4
RECENT_LIMIT = 6


def _book_of_the_day(session: Session) -> BookFeature | None:
    # Feature a book that actually has recipes; rotate once per calendar day.
    has_recipes = exists().where(Recipe.book_id == Book.id)
    total = session.scalar(select(func.count()).select_from(Book).where(has_recipes)) or 0
    if not total:
        return None
    idx = date.today().toordinal() % total
    chosen = session.scalar(
        select(Book).where(has_recipes).order_by(Book.calibre_id).offset(idx).limit(1)
    )
    if chosen is None:
        return None
    recipe_count = (
        session.scalar(select(func.count(Recipe.id)).where(Recipe.book_id == chosen.id)) or 0
    )
    return BookFeature(
        id=chosen.id,
        title=chosen.title,
        author=chosen.author,
        description=chosen.description,
        recipe_count=recipe_count,
        has_cover=has_cover(chosen),
    )


def _continue_reading(session: Session, user_id: uuid.UUID) -> list[ContinueBook]:
    """The books the caller has started but not finished, most recently read first.
    A finished book has nothing left to continue, so it drops out of the strip."""
    seen = func.count(RecipeView.id)
    total = (
        select(func.count(Recipe.id))
        .where(Recipe.book_id == Book.id)
        .correlate(Book)
        .scalar_subquery()
    )
    rows = session.execute(
        select(Book, seen, total)
        .join(Recipe, Recipe.book_id == Book.id)
        .join(
            RecipeView,
            (RecipeView.recipe_id == Recipe.id) & (RecipeView.user_id == user_id),
        )
        .group_by(Book.id)
        .having(seen < total)
        .order_by(func.max(RecipeView.last_viewed_at).desc())
        .limit(CONTINUE_LIMIT)
    ).all()
    return [
        ContinueBook(
            id=book.id,
            title=book.title,
            author=book.author,
            recipe_count=recipe_count,
            seen_count=seen_count,
            has_cover=has_cover(book),
        )
        for book, seen_count, recipe_count in rows
    ]


def _recently_read(session: Session, user_id: uuid.UUID) -> list[RecentRecipe]:
    """The recipes the caller opened most recently — the trail back to whatever they
    were in the middle of, which the per-book strip alone can't point at."""
    rows = session.execute(
        select(Recipe.id, Recipe.name, Book.id, Book.title)
        .join(RecipeView, RecipeView.recipe_id == Recipe.id)
        .join(Book, Book.id == Recipe.book_id)
        .where(RecipeView.user_id == user_id)
        .order_by(RecipeView.last_viewed_at.desc())
        .limit(RECENT_LIMIT)
    ).all()
    return [
        RecentRecipe(id=rid, name=name, book_id=book_id, book_title=book_title)
        for rid, name, book_id, book_title in rows
    ]


router = APIRouter(tags=["home"])


@router.get("/home", response_model=HomeData)
def home(session: SessionDep, user: CurrentUser) -> HomeData:
    stats = Stats(
        books=session.scalar(select(func.count()).select_from(Book)) or 0,
        recipes=session.scalar(select(func.count()).select_from(Recipe)) or 0,
        keywords=session.scalar(select(func.count()).select_from(Keyword)) or 0,
        recipes_seen=session.scalar(
            select(func.count())
            .select_from(RecipeView)
            .where(RecipeView.user_id == user.id)
        )
        or 0,
    )
    return HomeData(
        stats=stats,
        book_of_the_day=_book_of_the_day(session),
        continue_reading=_continue_reading(session, user.id),
        recently_read=_recently_read(session, user.id),
    )
