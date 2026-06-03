import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.recipe import RecipeRow


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
    has_cover: bool
    pubdate: date | None


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
    recipes: list[RecipeRow]
