from datetime import date

from fastapi import APIRouter
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.covers import has_cover
from app.db import SessionDep
from app.models.book import Book
from app.models.recipe import Keyword, Recipe
from app.schemas.home import BookFeature, HomeData, Stats


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


router = APIRouter(tags=["home"])


@router.get("/home", response_model=HomeData)
def home(session: SessionDep) -> HomeData:
    stats = Stats(
        books=session.scalar(select(func.count()).select_from(Book)) or 0,
        recipes=session.scalar(select(func.count()).select_from(Recipe)) or 0,
        keywords=session.scalar(select(func.count()).select_from(Keyword)) or 0,
    )
    return HomeData(stats=stats, book_of_the_day=_book_of_the_day(session))
