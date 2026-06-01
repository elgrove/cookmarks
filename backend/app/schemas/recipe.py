import uuid

from pydantic import BaseModel, ConfigDict


class RecipeRow(BaseModel):
    """A recipe as it appears in a book's recipe index: name + its keywords."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    keywords: list[str]


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
