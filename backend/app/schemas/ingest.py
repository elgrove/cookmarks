import uuid

from pydantic import BaseModel, Field


class StagedBookRead(BaseModel):
    """A book file accepted onto the server and inspected, waiting for confirmation.
    Title and author are a starting point read from the file (or its name), not a
    finding — the user corrects them before the ingest is submitted."""

    staging_id: str
    filename: str
    format: str
    title: str
    author: str


class StageUrlRequest(BaseModel):
    url: str


class IngestRequest(BaseModel):
    """The confirmed ingest. `replace_book_id` names an existing book to stand down in
    favour of this file: its recipes, favourites and list membership survive, and only
    the library entry behind it is swapped."""

    staging_id: str
    title: str = Field(min_length=1)
    author: str = Field(min_length=1)
    extract: bool = False
    replace_book_id: uuid.UUID | None = None
