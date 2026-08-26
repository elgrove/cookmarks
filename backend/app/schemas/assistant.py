import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationSummary(BaseModel):
    """One chat in the history list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    """A chat with its stored turns replayed as Vercel AI UI messages — the shape the
    frontend's `Chat` is seeded with. The parts are library-owned, so they stay an
    opaque list of objects here rather than being re-modelled field by field."""

    messages: list[dict]
