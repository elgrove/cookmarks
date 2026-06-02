import uuid
from collections import OrderedDict
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

Sort = Literal["random", "name", "recent", "book"]

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

# Navigation orderings the recipe page can be reached through; "list" arrives with
# that page, so unknown contexts resolve to book.
SUPPORTED_CONTEXTS = {"book", "search"}


def _search_order(sort: Sort, seed: int) -> list:
    """The ORDER BY clauses for a search, shared by the result page and prev/next
    so a recipe's neighbours match exactly what the search showed."""
    if sort == "name":
        return [func.lower(Recipe.name).asc()]
    if sort == "recent":
        return [Recipe.created_at.desc()]
    if sort == "book":
        # The book's own sequence. Filtered to one book this is exactly its stored
        # order; across books (unfiltered) it groups by book, title-ordered.
        return [Book.title.asc(), Recipe.order.asc()]
    # Seeded shuffle: a fixed permutation of the rows for a given seed, so the
    # ordering is stable across pagination but varies between searches. The
    # multiplier is coprime to the prime modulus, making it a bijection.
    multiplier = 1 + (seed * _SHUFFLE_HASH) % (_SHUFFLE_MODULUS - 1)
    return [((literal_column("recipes.rowid") * multiplier) % _SHUFFLE_MODULUS).asc()]


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

    rows = session.execute(
        select(Recipe, Book)
        .join(Book, Recipe.book_id == Book.id)
        .where(*conditions)
        .order_by(*_search_order(sort, seed), Recipe.id)
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
def list_keywords(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[KeywordSummary]:
    # The client shows only the most-used keywords as resting-state chips, so cap
    # the result — the corpus has thousands, and shipping them all is the bulk of
    # this endpoint's cost (serialising every row) for keywords nobody renders.
    rows = session.execute(
        select(Keyword.name, func.count(recipe_keywords.c.recipe_id))
        .outerjoin(recipe_keywords, recipe_keywords.c.keyword_id == Keyword.id)
        .group_by(Keyword.id)
        .order_by(func.count(recipe_keywords.c.recipe_id).desc(), Keyword.name)
        .limit(limit)
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


def _neighbour(session: Session, recipe_id: uuid.UUID | None) -> RecipeNeighbour | None:
    if recipe_id is None:
        return None
    row = session.execute(select(Recipe.id, Recipe.name).where(Recipe.id == recipe_id)).first()
    return RecipeNeighbour(id=row.id, name=row.name) if row else None


# Cache of ordered result ids per search, so stepping prev/next through a search
# doesn't re-run the (relatively costly) query on every press. Keyed by the exact
# criteria + seed, which the client holds stable across one search; a small LRU is
# plenty for a single user. Re-extraction can leave an entry stale until it's
# evicted or the seed changes — acceptable for now.
_SEARCH_ORDER_CACHE: OrderedDict[tuple, list[uuid.UUID]] = OrderedDict()
_SEARCH_ORDER_CACHE_MAX = 32


def _clear_search_order_cache() -> None:
    _SEARCH_ORDER_CACHE.clear()


def _ordered_search_ids(
    session: Session,
    q: str,
    keywords: list[str],
    book_id: uuid.UUID | None,
    author: str | None,
    sort: Sort,
    seed: int,
) -> list[uuid.UUID]:
    key = (q, tuple(keywords), str(book_id) if book_id else None, author, sort, seed)
    cached = _SEARCH_ORDER_CACHE.get(key)
    if cached is not None:
        _SEARCH_ORDER_CACHE.move_to_end(key)
        return cached
    conditions = _search_conditions(q, keywords, book_id, author)
    ids = list(
        session.scalars(
            select(Recipe.id)
            .join(Book, Recipe.book_id == Book.id)
            .where(*conditions)
            .order_by(*_search_order(sort, seed), Recipe.id)
        ).all()
    )
    _SEARCH_ORDER_CACHE[key] = ids
    _SEARCH_ORDER_CACHE.move_to_end(key)
    while len(_SEARCH_ORDER_CACHE) > _SEARCH_ORDER_CACHE_MAX:
        _SEARCH_ORDER_CACHE.popitem(last=False)
    return ids


def _search_neighbours(
    session: Session,
    recipe: Recipe,
    q: str,
    keywords: list[str],
    book_id: uuid.UUID | None,
    author: str | None,
    sort: Sort,
    seed: int,
) -> tuple[RecipeNeighbour | None, RecipeNeighbour | None]:
    """Previous/next in the *search* ordering — the ordered ids (cached per search)
    indexed to this recipe. Returns (None, None) if it isn't in the result set."""
    ids = _ordered_search_ids(session, q, keywords, book_id, author, sort, seed)
    try:
        idx = ids.index(recipe.id)
    except ValueError:
        return None, None
    prev_id = ids[idx - 1] if idx > 0 else None
    next_id = ids[idx + 1] if idx + 1 < len(ids) else None
    return _neighbour(session, prev_id), _neighbour(session, next_id)


@router.get("/recipes/{recipe_id}", response_model=RecipeDetail)
def get_recipe(
    recipe_id: uuid.UUID,
    session: SessionDep,
    context: str = "book",
    q: Annotated[str, Query()] = "",
    keyword: Annotated[list[str] | None, Query()] = None,
    book_id: uuid.UUID | None = None,
    author: Annotated[str | None, Query()] = None,
    sort: Sort = "random",
    seed: Annotated[int, Query(ge=0)] = 0,
) -> RecipeDetail:
    recipe = session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.keywords), joinedload(Recipe.book))
    )
    if recipe is None:
        raise HTTPException(status_code=404, detail="recipe not found")
    book = recipe.book
    resolved_context = context if context in SUPPORTED_CONTEXTS else "book"
    if resolved_context == "search":
        previous, next_ = _search_neighbours(
            session, recipe, q.strip(), keyword or [], book_id, author, sort, seed
        )
    else:
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
