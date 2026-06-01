import uuid

from pydantic import BaseModel, ConfigDict


class RecipeRow(BaseModel):
    """A recipe as it appears in a book's recipe index: name + its keywords."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    keywords: list[str]


class RecipeDetail(BaseModel):
    """A single recipe's reading view, with the book provenance it links back to.

    `has_image` reports whether the source carried an image; serving the image
    itself is a later slice, so the page renders the no-image plate (DESIGN §7)
    while keeping the metadata line honest."""

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
