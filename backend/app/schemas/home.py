import uuid

from pydantic import BaseModel, ConfigDict


class Stats(BaseModel):
    """Library totals for the home ledger."""

    books: int
    recipes: int
    keywords: int


class BookFeature(BaseModel):
    """A book highlighted on the home page (carries its description for the feature)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    author: str
    description: str
    recipe_count: int
    has_cover: bool


class HomeData(BaseModel):
    stats: Stats
    book_of_the_day: BookFeature | None
