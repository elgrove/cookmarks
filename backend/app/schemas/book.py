import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class BookSummary(BaseModel):
    """One row of the books library: enough to render a book card."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    author: str
    recipe_count: int
    has_cover: bool
    pubdate: date | None
