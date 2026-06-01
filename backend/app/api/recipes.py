import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import selectinload

from app.db import SessionDep
from app.models.book import Book
from app.models.recipe import Keyword, Recipe, recipe_keywords
from app.schemas.recipe import KeywordSummary, RecipeSearchResults, RecipeSummary

router = APIRouter(tags=["recipes"])

Sort = Literal["name", "recent"]


@router.get("/recipes", response_model=RecipeSearchResults)
def search_recipes(
    session: SessionDep,
    q: Annotated[str, Query()] = "",
    keyword: Annotated[list[str] | None, Query()] = None,
    book_id: uuid.UUID | None = None,
    author: Annotated[str | None, Query()] = None,
    sort: Sort = "name",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RecipeSearchResults:
    # The page is empty until *something* is asked for: a typed query or any
    # filter. Filters count as a query, so a keyword/book/author alone returns
    # results; nothing set returns the resting (empty) state.
    keywords = keyword or []
    q = q.strip()
    if not (q or keywords or book_id or author):
        return RecipeSearchResults(total=0, items=[])

    conditions = []
    if q:
        like = f"%{q}%"
        conditions.append(
            or_(
                Recipe.name.ilike(like),
                Book.title.ilike(like),
                Book.author.ilike(like),
                cast(Recipe.ingredients, String).ilike(like),
                Recipe.keywords.any(Keyword.name.ilike(like)),
            )
        )
    # Each chosen chip must be present (AND-narrowing).
    for kw in keywords:
        conditions.append(Recipe.keywords.any(Keyword.name == kw))
    if book_id is not None:
        conditions.append(Recipe.book_id == book_id)
    if author is not None:
        conditions.append(Book.author == author)

    filtered = select(Recipe.id).join(Book, Recipe.book_id == Book.id).where(*conditions)
    total = session.scalar(select(func.count()).select_from(filtered.subquery())) or 0

    order = func.lower(Recipe.name).asc() if sort == "name" else Recipe.created_at.desc()
    rows = session.execute(
        select(Recipe, Book)
        .join(Book, Recipe.book_id == Book.id)
        .where(*conditions)
        .order_by(order, Recipe.id)
        .offset(offset)
        .limit(limit)
        .options(selectinload(Recipe.keywords))
    ).all()

    items = [
        RecipeSummary(
            id=recipe.id,
            name=recipe.name,
            book_id=book.id,
            book_title=book.title,
            book_author=book.author,
            keywords=sorted(k.name for k in recipe.keywords),
        )
        for recipe, book in rows
    ]
    return RecipeSearchResults(total=total, items=items)


@router.get("/keywords", response_model=list[KeywordSummary])
def list_keywords(session: SessionDep) -> list[KeywordSummary]:
    rows = session.execute(
        select(Keyword.name, func.count(recipe_keywords.c.recipe_id))
        .outerjoin(recipe_keywords, recipe_keywords.c.keyword_id == Keyword.id)
        .group_by(Keyword.id)
        .order_by(func.count(recipe_keywords.c.recipe_id).desc(), Keyword.name)
    ).all()
    return [KeywordSummary(name=name, recipe_count=count) for name, count in rows]
