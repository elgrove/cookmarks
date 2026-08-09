import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RecipeRow(BaseModel):
    """A recipe as it appears in a book's recipe index: name + its keywords."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    keywords: list[str]
    # Whether the caller has read this one — the per-row detail behind the book's


class RecipeSummary(BaseModel):
    """One result row of the recipe search: a text-first list row (DESIGN §5)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    book_id: uuid.UUID
    book_title: str
    book_author: str
    keywords: list[str]


class KeywordSummary(BaseModel):
    """A keyword and how many recipes carry it — drives the filter chips.

    On the global endpoint ``recipe_count`` is the keyword's total reach; in a
    search's ``facets`` it's the count *within the current result set* — how
    often the keyword co-occurs with the active criteria.
    """

    name: str
    recipe_count: int


class RecipeSearchResults(BaseModel):
    """A page of search results, the unpaged total, and the co-occurrence facets.

    ``facets`` are the keywords most common among the recipes matching the
    current criteria (selected keywords excluded), so the chip list can re-rank
    to what narrows the search further. Empty on the resting state.
    """

    total: int
    items: list[RecipeSummary]
    facets: list[KeywordSummary] = []


class SimilarRecipes(BaseModel):
    """Recipes related to a given one, as text-first list rows (same shape as a
    search result). ``basis`` records *how* they were found: ``vector`` = nearest by
    embedding (cosine over the imported Gemini vectors); ``keyword`` = the fallback
    by shared keywords, used when the recipe has no embedding. The distinction is for
    honesty/verification — the list reads the same either way.
    """

    basis: Literal["vector", "keyword"]
    items: list[RecipeSummary]


class SemanticResult(RecipeSummary):
    """A semantic-search result row: a recipe summary plus its cosine distance from
    the query (smaller is closer). Same shape as a keyword result, so the frontend
    renders both as the same text-first row."""

    distance: float


class SemanticSearchResults(BaseModel):
    """Recipes ranked by meaning for a natural-language query, closest first.

    ``available`` is False when semantic search can't run (no embedding-capable AI
    provider configured) — distinct from an available search that simply matched
    nothing (``available`` True, ``total`` 0), so the UI can prompt to configure a
    provider rather than say "no matches".
    """

    available: bool
    query: str
    total: int
    items: list[SemanticResult] = []


class RecipeViewState(BaseModel):
    """The caller's view record for a recipe, after recording an open: how many
    sittings it has been read in, and when it was first and last seen."""

    view_count: int
    first_viewed_at: datetime
    last_viewed_at: datetime


class RecipeNeighbour(BaseModel):
    """The adjacent recipe in the current navigation context (for prev/next)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class RecipeDetail(BaseModel):
    """A single recipe's reading view, with the book provenance it links back to.

    `has_image` reports whether the source carried an image; serving the image
    itself is a later slice, so the page renders the no-image plate (DESIGN §7)
    while keeping the metadata line honest.

    `context` is the navigation ordering the page was reached through; `previous`/
    `next` are the adjacent recipes in that ordering (null at the ends). Only the
    `book` context is wired today — search/list orderings arrive with those pages.

    `in_book` is what the reader last found when it looked for this recipe in the
    book's own text: null = never looked, true = found, false = the book doesn't
    spell it that way anywhere, so opening the book at it can't land."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    book_id: uuid.UUID
    book_title: str
    book_author: str
    book_has_cover: bool
    name: str
    description: str | None
    ingredients: list[str]
    instructions: list[str]
    yields: str | None
    keywords: list[str]
    has_image: bool
    is_favourite: bool
    context: str
    in_book: bool | None
    previous: RecipeNeighbour | None
    next: RecipeNeighbour | None


class EpubLocation(BaseModel):
    """What the reader resolved for a recipe in its book's EPUB — a foliate CFI, or
    null when the scan found nothing. Either way the recipe is recorded as checked."""

    cfi: str | None = None
