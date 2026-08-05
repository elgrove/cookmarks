import uuid
from collections import OrderedDict
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import String, cast, func, literal_column, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import CurrentUser
from app.api.lists import favourite_list_id
from app.covers import has_cover
from app.db import SessionDep
from app.epub import read_epub_image
from app.models.book import Book
from app.models.recipe import Keyword, Recipe, recipe_keywords
from app.models.recipe_list import RecipeListItem
from app.schemas.recipe import (
    KeywordSummary,
    RecipeDetail,
    RecipeNeighbour,
    RecipeSearchResults,
    RecipeSummary,
    RecipeViewState,
    SemanticResult,
    SemanticSearchResults,
    SimilarRecipes,
)
from app.services import embeddings
from app.services.views import as_utc, record_view
from app.services.vector_store import VectorStore

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


def _summary(recipe: Recipe, book: Book) -> RecipeSummary:
    """A recipe as a text-first list row (search results, similar-recipe lists)."""
    return RecipeSummary(
        id=recipe.id,
        name=recipe.name,
        book_id=book.id,
        book_title=book.title,
        book_author=book.author,
        keywords=sorted(k.name for k in recipe.keywords),
    )


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

    items = [_summary(recipe, book) for recipe, book in rows]

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


# Declared before GET /recipes/{recipe_id} so "semantic" isn't parsed as a recipe id.
@router.get("/recipes/semantic", response_model=SemanticSearchResults)
def semantic_search(
    session: SessionDep,
    q: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> SemanticSearchResults:
    # Empty query → the resting state: available, nothing asked for yet.
    query = q.strip()
    if not query:
        return SemanticSearchResults(available=True, query="", total=0, items=[])

    matches = embeddings.search(session, query, limit)
    if matches is None:
        # No embedding-capable provider configured — the UI prompts to set one up
        # rather than implying the library is empty.
        return SemanticSearchResults(available=False, query=query, total=0, items=[])

    ids = [recipe_id for recipe_id, _ in matches]
    rows = session.execute(
        select(Recipe, Book)
        .join(Book, Recipe.book_id == Book.id)
        .where(Recipe.id.in_(ids))
        .options(selectinload(Recipe.keywords))
    ).all()
    by_id = {recipe.id: (recipe, book) for recipe, book in rows}

    # Walk `matches` (already distance-ordered) so the response preserves relevance
    # order — the SELECT above returns rows in id order, not distance order.
    items: list[SemanticResult] = []
    for recipe_id, distance in matches:
        pair = by_id.get(recipe_id)
        if pair is None:
            continue
        recipe, book = pair
        items.append(
            SemanticResult(
                id=recipe.id,
                name=recipe.name,
                book_id=book.id,
                book_title=book.title,
                book_author=book.author,
                keywords=sorted(k.name for k in recipe.keywords),
                distance=distance,
            )
        )
    return SemanticSearchResults(available=True, query=query, total=len(items), items=items)


# The global most-used keywords are identical for every caller until the corpus
# changes (only the import script and, later, the extraction task write keywords),
# so compute them once per process and serve from memory: the grouped count over
# ~5k keywords against ~78k links is otherwise this endpoint's whole cost (~170ms).
# Cache the top _CAP and slice per request — the ordering is fixed, so any limit up
# to _CAP is a prefix of it. Module-global, so the test suite clears it (conftest)
# the way it does the search-order cache; the extraction task clears it on write.
_KEYWORD_CACHE_CAP = 500
_top_keywords: list[KeywordSummary] | None = None


def _clear_keyword_cache() -> None:
    global _top_keywords
    _top_keywords = None


@router.get("/keywords", response_model=list[KeywordSummary])
def list_keywords(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=_KEYWORD_CACHE_CAP)] = 50,
) -> list[KeywordSummary]:
    # Resting-state filter chips: the client renders only the most-used few. Served
    # from the per-process cache; `limit` is a prefix of the cached top-_CAP since
    # the ordering is fixed (count desc, then name).
    global _top_keywords
    if _top_keywords is None:
        # Inner join, not outer: these are recipe filter chips, so a keyword used
        # only on books (the shared vocabulary now spans both) must not appear here.
        rows = session.execute(
            select(Keyword.name, func.count(recipe_keywords.c.recipe_id))
            .join(recipe_keywords, recipe_keywords.c.keyword_id == Keyword.id)
            .group_by(Keyword.id)
            .order_by(func.count(recipe_keywords.c.recipe_id).desc(), Keyword.name)
            .limit(_KEYWORD_CACHE_CAP)
        ).all()
        _top_keywords = [KeywordSummary(name=name, recipe_count=count) for name, count in rows]
    return _top_keywords[:limit]


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


def _is_favourite(session: Session, recipe_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Whether the recipe sits in the caller's Favourites list. A pure read — it
    never creates the list, so an unstarred recipe on a fresh account reads False."""
    fav_id = favourite_list_id(session, user_id)
    if fav_id is None:
        return False
    return (
        session.scalar(
            select(RecipeListItem.id).where(
                RecipeListItem.recipe_list_id == fav_id,
                RecipeListItem.recipe_id == recipe_id,
            )
        )
        is not None
    )


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
    user: CurrentUser,
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
        is_favourite=_is_favourite(session, recipe.id, user.id),
        context=resolved_context,
        previous=previous,
        next=next_,
    )


@router.post("/recipes/{recipe_id}/seen", response_model=RecipeViewState)
def mark_recipe_seen(
    recipe_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> RecipeViewState:
    """Record that the caller has opened this recipe — the input to a book's read
    percentage. Explicit rather than a side effect of GET /recipes/{id}, so reading
    a recipe stays a read."""
    if session.get(Recipe, recipe_id) is None:
        raise HTTPException(status_code=404, detail="recipe not found")
    view = record_view(session, user.id, recipe_id)
    return RecipeViewState(
        view_count=view.view_count,
        first_viewed_at=as_utc(view.created_at),
        last_viewed_at=as_utc(view.last_viewed_at),
    )


@router.get("/recipes/{recipe_id}/image")
def recipe_image(recipe_id: uuid.UUID, session: SessionDep) -> Response:
    """Stream a recipe's image out of its book's EPUB. 404 when the recipe carries no
    recorded image, its EPUB is missing, or the recorded member isn't in the archive
    — the client only asks when `has_image` is true and otherwise keeps the no-image
    reading view."""
    recipe = session.scalar(
        select(Recipe).where(Recipe.id == recipe_id).options(joinedload(Recipe.book))
    )
    if recipe is None or recipe.image is None:
        raise HTTPException(status_code=404, detail="recipe image not found")
    result = read_epub_image(recipe.book, recipe.image)
    if result is None:
        raise HTTPException(status_code=404, detail="recipe image not found")
    data, media_type = result
    return Response(content=data, media_type=media_type)


# Similar recipes: nearest by embedding, with a shared-keyword fallback for the ~1%
# of recipes that carry no vector. Computed on demand — no AI call, the recipe's own
# stored embedding drives the KNN — and fetched lazily by the page, off its critical path.
# The default fills the "Similar to <recipe>" browse page; the recipe-detail footer asks
# for a small slice (limit=5) explicitly.
SIMILAR_LIMIT_DEFAULT = 30


def _load_ordered(session: Session, ids: list[uuid.UUID]) -> list[RecipeSummary]:
    """Recipe summaries for `ids`, in that order — the KNN ranking is the order."""
    if not ids:
        return []
    rows = session.execute(
        select(Recipe, Book)
        .join(Book, Recipe.book_id == Book.id)
        .where(Recipe.id.in_(ids))
        .options(selectinload(Recipe.keywords))
    ).all()
    by_id = {recipe.id: (recipe, book) for recipe, book in rows}
    out: list[RecipeSummary] = []
    for rid in ids:
        pair = by_id.get(rid)
        if pair is not None:
            out.append(_summary(pair[0], pair[1]))
    return out


def _keyword_neighbours(session: Session, recipe: Recipe, limit: int) -> list[RecipeSummary]:
    """Recipes sharing the most keywords with `recipe` (itself excluded) — the fallback
    when there's no embedding. Empty when the recipe carries no keywords to match on."""
    keyword_ids = [k.id for k in recipe.keywords]
    if not keyword_ids:
        return []
    shared = func.count(recipe_keywords.c.keyword_id)
    rows = session.execute(
        select(Recipe, Book)
        .join(Book, Recipe.book_id == Book.id)
        .join(recipe_keywords, recipe_keywords.c.recipe_id == Recipe.id)
        .where(recipe_keywords.c.keyword_id.in_(keyword_ids), Recipe.id != recipe.id)
        .group_by(Recipe.id)
        .order_by(shared.desc(), func.lower(Recipe.name))
        .limit(limit)
        .options(selectinload(Recipe.keywords))
    ).all()
    return [_summary(recipe, book) for recipe, book in rows]


@router.get("/recipes/{recipe_id}/similar", response_model=SimilarRecipes)
def similar_recipes(
    recipe_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = SIMILAR_LIMIT_DEFAULT,
) -> SimilarRecipes:
    recipe = session.scalar(
        select(Recipe).where(Recipe.id == recipe_id).options(selectinload(Recipe.keywords))
    )
    if recipe is None:
        raise HTTPException(status_code=404, detail="recipe not found")

    store = VectorStore(session)
    embedding = store.get_embedding(recipe_id)
    if embedding is not None:
        neighbours = store.search_excluding(embedding, recipe_id, limit=limit)
        return SimilarRecipes(
            basis="vector",
            items=_load_ordered(session, [nid for nid, _ in neighbours]),
        )
    return SimilarRecipes(basis="keyword", items=_keyword_neighbours(session, recipe, limit))
