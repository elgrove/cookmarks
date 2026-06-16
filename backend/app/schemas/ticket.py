from pydantic import BaseModel, Field


class TicketCreate(BaseModel):
    """A user-submitted ticket, filed as an issue in the Cookmarks Linear project.
    `page_url` records where the user was when they reported it."""

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    page_url: str | None = Field(default=None, max_length=2000)


class TicketResult(BaseModel):
    """The filed Linear issue: its human identifier (e.g. "MY-42") and url."""

    identifier: str
    url: str
