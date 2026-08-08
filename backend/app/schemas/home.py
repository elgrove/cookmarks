import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import ReadingMode


class Stats(BaseModel):
    """Library totals for the home ledger. `books_read` is the caller's own — how many
    books they have read through, against `books` for the whole library."""

    books: int
    recipes: int
    keywords: int
    books_read: int


class BookFeature(BaseModel):
    """A book highlighted on the home page (carries its description for the feature)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    author: str
    description: str
    recipe_count: int
    has_cover: bool


class ContinueBook(BaseModel):
    """A book the caller is part-way through, in the mode they last read it in.
    `fraction` is how far through — measured in recipes either way — and
    `resume_recipe_id` is the recipe both modes pick back up at."""

    id: uuid.UUID
    title: str
    author: str
    mode: ReadingMode
    fraction: float
    resume_recipe_id: uuid.UUID | None
    has_cover: bool


class RecentRecipe(BaseModel):
    """A recipe the caller read recently, most recent first — where they left off,
    at recipe rather than book granularity."""

    id: uuid.UUID
    name: str
    book_id: uuid.UUID
    book_title: str


class HomeData(BaseModel):
    stats: Stats
    book_of_the_day: BookFeature | None
    continue_reading: list[ContinueBook]
    recently_read: list[RecentRecipe]
