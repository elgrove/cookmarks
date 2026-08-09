import uuid

from pydantic import BaseModel


class QueuedBook(BaseModel):
    """A book on the caller's reading queue, newest-queued first. Also the shape of the
    home page's "Up next" strip."""

    id: uuid.UUID
    title: str
    author: str
    has_cover: bool
    recipe_count: int


class QueueState(BaseModel):
    """Whether the book is on the caller's queue, after an add or remove."""

    queued: bool
