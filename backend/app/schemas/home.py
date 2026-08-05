import uuid

from pydantic import BaseModel, ConfigDict


class Stats(BaseModel):
    """Library totals for the home ledger. `recipes_seen` is the caller's own — how
    many distinct recipes they have opened, against `recipes` for the whole library."""

    books: int
    recipes: int
    keywords: int
    recipes_seen: int


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
    """A book the caller is part-way through: started, not finished, most recently
    read first."""

    id: uuid.UUID
    title: str
    author: str
    recipe_count: int
    seen_count: int
    has_cover: bool


class HomeData(BaseModel):
    stats: Stats
    book_of_the_day: BookFeature | None
    continue_reading: list[ContinueBook]
