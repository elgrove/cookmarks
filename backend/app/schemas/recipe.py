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


class RecipeSearchResults(BaseModel):
    """A page of search results plus the unpaged total (for the result count)."""

    total: int
    items: list[RecipeSummary]


class KeywordSummary(BaseModel):
    """A keyword and how many recipes carry it — drives the filter chips."""

    name: str
    recipe_count: int
