import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.base import as_utc


class ConversationSummary(BaseModel):
    """One chat in the history list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime

    # SQLite hands back a naive datetime on a re-read and an aware one on a row just
    # written, which would emit two timestamp formats for the same field.
    @field_validator("created_at", "updated_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return as_utc(value)


class ConversationDetail(ConversationSummary):
    """A chat with its stored turns replayed as Vercel AI UI messages — the shape the
    frontend's `Chat` is seeded with. The parts are library-owned, so they stay an
    opaque list of objects here rather than being re-modelled field by field."""

    messages: list[dict]
