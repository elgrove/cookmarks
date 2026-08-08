import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ReadingMode
from app.schemas.recipe import RecipeNeighbour, RecipeRow


class ReadingState(BaseModel):
    """How far through a book the caller is, and which way they were reading it. The
    two modes share one position: `fraction` and `anchor` are measured in recipes
    whichever way the book was read, while `location` is the reader's own page, so
    returning to the pages lands where they were left."""

    mode: ReadingMode
    fraction: float
    anchor: RecipeNeighbour | None
    location: str | None
    finished: bool


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
    # How far through the book the caller has read, 0 to 1, whichever way they read it.
    # None for a book never opened, which shows no progress rather than 0%.
    progress: float | None
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
    has_cover: bool
    has_epub: bool
    added: datetime | None
    keywords: list[str]
    recipes: list[RecipeRow]
    reading: ReadingState | None
    # Where reading the recipes picks up: the furthest one reached, or the first in book
    # order for a book not yet read. None for a book with nothing extracted.
    resume_recipe: RecipeNeighbour | None


class ReadingUpdate(BaseModel):
    """A reader reporting where it has got to: the recipe it has reached, and (from the
    EPUB reader) the page it is on."""

    mode: ReadingMode = ReadingMode.BOOK
    recipe_id: uuid.UUID | None = None
    location: str | None = None


class BookReadState(BaseModel):
    """A book's reading after marking it read or resetting it, so the client takes the
    new state from the server rather than guessing what the bulk change did."""

    recipe_count: int
    reading: ReadingState | None


class RecipeIndexEntry(BaseModel):
    """A book's recipe reduced to what the in-book reader matcher needs: id, name,
    favourite state. The full set (uncapped), so headings can be matched to recipes."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_favourite: bool
