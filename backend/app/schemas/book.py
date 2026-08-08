import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.recipe import RecipeNeighbour, RecipeRow


class BookFilter(BaseModel):
    """Minimal book row for the recipes-search filter controls: id/title/author
    only — no recipe count or cover stat, so the query stays a plain, cheap select."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    author: str


class BookSummary(BaseModel):
    """One row of the books library: enough to render a book card."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    author: str
    recipe_count: int
    # How many of those recipes the caller has opened — the numerator of the read
    # percentage, which the client derives so rounding lives in one place.
    seen_count: int
    has_cover: bool
    pubdate: date | None
    keywords: list[str]


class BookDetail(BaseModel):
    """A single book's detail view: metadata, cover state, and a sample of its recipes."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    author: str
    isbn: str | None
    pubdate: date | None
    description: str
    recipe_count: int
    seen_count: int
    has_cover: bool
    has_epub: bool
    added: datetime | None
    keywords: list[str]
    recipes: list[RecipeRow]
    # The first recipe in book order the caller hasn't read, so picking a book back up
    # is one click rather than a hunt through the index. None once the book is finished.
    next_unread: RecipeNeighbour | None


class BookReadState(BaseModel):
    """A book's reading progress after marking it read or resetting it — the two
    numbers the percentage is derived from, so the client re-derives rather than
    guessing what the bulk change did."""

    recipe_count: int
    seen_count: int


class RecipeIndexEntry(BaseModel):
    """A book's recipe reduced to what the in-book reader matcher needs: id, name,
    favourite state. The full set (uncapped), so headings can be matched to recipes."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_favourite: bool
