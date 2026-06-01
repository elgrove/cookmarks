import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import String, cast, func, literal_column, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.covers import has_cover
from app.db import SessionDep
from app.models.book import Book
from app.models.recipe import Keyword, Recipe, recipe_keywords
from app.schemas.recipe import (
    KeywordSummary,
    RecipeDetail,
    RecipeNeighbour,
    RecipeSearchResults,
    RecipeSummary,
)

router = APIRouter(tags=["recipes"])

Sort = Literal["random", "name", "recent"]

# How many co-occurrence facets to return. The client renders these (plus any
# pinned selected chips) and clamps the block to a few lines by measurement, so
# we hand over a generous pool and let layout decide how many actually show.
FACET_LIMIT = 50

# Seeded-shuffle constants. A prime modulus below 2**31 keeps `rowid * multiplier`
# inside SQLite's signed-64-bit range; the multiplier is derived from the seed via
# Knuth's multiplicative hash so it lands large (forcing modular wraparound, hence
# real mixing) and well-spread even for small, adjacent seeds.
_SHUFFLE_MODULUS = 2147483647
_SHUFFLE_HASH = 2654435761

# Navigation orderings the recipe page can be reached through. Only "book" is wired
# today; "search" / "list" arrive with those pages, so unknown contexts resolve to book.
SUPPORTED_CONTEXTS = {"book"}


def _search_conditions(
    q: str, keywords: list[str], book_id: uuid.UUID | None, author: str | None
) -> list:
    """The AND-narrowing filter shared by the result rows, total and facets."""
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
    return conditions


@router.get("/recipes", response_model=RecipeSearchResults)
def search_recipes(
    session: SessionDep,
    q: Annotated[str, Query()] = "",
    keyword: Annotated[list[str] | None, Query()] = None,
    book_id: uuid.UUID | None = None,
    author: Annotated[str | None, Query()] = None,
    sort: Sort = "random",
    seed: Annotated[int, Query(ge=0)] = 0,
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

    conditions = _search_conditions(q, keywords, book_id, author)

    filtered = select(Recipe.id).join(Book, Recipe.book_id == Book.id).where(*conditions)
    total = session.scalar(select(func.count()).select_from(filtered.subquery())) or 0

    if sort == "name":
        order = func.lower(Recipe.name).asc()
    elif sort == "recent":
        order = Recipe.created_at.desc()
    else:
        # Seeded shuffle: a fixed permutation of the rows for a given seed, so the
        # ordering is stable across pagination but varies between searches. The
        # multiplier is coprime to the prime modulus, making it a bijection.
        multiplier = 1 + (seed * _SHUFFLE_HASH) % (_SHUFFLE_MODULUS - 1)
        order = ((literal_column("recipes.rowid") * multiplier) % _SHUFFLE_MODULUS).asc()

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

    # Facets: the keywords most common among the matching recipes, so the chips
    # can re-rank to what narrows further. Already-selected keywords are dropped
    # (every match carries them) — the frontend pins those separately.
    facet_count = func.count(recipe_keywords.c.recipe_id)
    facet_query = (
        select(Keyword.name, facet_count)
        .select_from(recipe_keywords)
        .join(Keyword, Keyword.id == recipe_keywords.c.keyword_id)
        .where(recipe_keywords.c.recipe_id.in_(filtered.scalar_subquery()))
        .group_by(Keyword.id)
        .order_by(facet_count.desc(), Keyword.name)
        .limit(FACET_LIMIT)
    )
    if keywords:
        facet_query = facet_query.where(Keyword.name.notin_(keywords))
    facets = [
        KeywordSummary(name=name, recipe_count=count)
        for name, count in session.execute(facet_query).all()
    ]

    return RecipeSearchResults(total=total, items=items, facets=facets)


@router.get("/keywords", response_model=list[KeywordSummary])
def list_keywords(session: SessionDep) -> list[KeywordSummary]:
    rows = session.execute(
        select(Keyword.name, func.count(recipe_keywords.c.recipe_id))
        .outerjoin(recipe_keywords, recipe_keywords.c.keyword_id == Keyword.id)
        .group_by(Keyword.id)
        .order_by(func.count(recipe_keywords.c.recipe_id).desc(), Keyword.name)
    ).all()
    return [KeywordSummary(name=name, recipe_count=count) for name, count in rows]


def _book_neighbours(
    session: Session, recipe: Recipe
) -> tuple[RecipeNeighbour | None, RecipeNeighbour | None]:
    """The previous/next recipe in the owning book's stored order (Recipe.order)."""
    prev = session.execute(
        select(Recipe.id, Recipe.name)
        .where(Recipe.book_id == recipe.book_id, Recipe.order < recipe.order)
        .order_by(Recipe.order.desc())
        .limit(1)
    ).first()
    nxt = session.execute(
        select(Recipe.id, Recipe.name)
        .where(Recipe.book_id == recipe.book_id, Recipe.order > recipe.order)
        .order_by(Recipe.order.asc())
        .limit(1)
    ).first()
    return (
        RecipeNeighbour(id=prev.id, name=prev.name) if prev else None,
        RecipeNeighbour(id=nxt.id, name=nxt.name) if nxt else None,
    )


@router.get("/recipes/{recipe_id}", response_model=RecipeDetail)
def get_recipe(recipe_id: uuid.UUID, session: SessionDep, context: str = "book") -> RecipeDetail:
    recipe = session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.keywords), joinedload(Recipe.book))
    )
    if recipe is None:
        raise HTTPException(status_code=404, detail="recipe not found")
    book = recipe.book
    resolved_context = context if context in SUPPORTED_CONTEXTS else "book"
    previous, next_ = _book_neighbours(session, recipe)
    return RecipeDetail(
        id=recipe.id,
        book_id=book.id,
        book_title=book.title,
        book_author=book.author,
        book_has_cover=has_cover(book),
        name=recipe.name,
        description=recipe.description,
        ingredients=recipe.ingredients,
        instructions=recipe.instructions,
        yields=recipe.yields,
        keywords=sorted(k.name for k in recipe.keywords),
        has_image=recipe.image is not None,
        context=resolved_context,
        previous=previous,
        next=next_,
    )
