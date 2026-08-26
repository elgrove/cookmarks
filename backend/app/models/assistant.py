import uuid
from decimal import Decimal

from sqlalchemy import JSON, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDAuditBase


class AssistantConversation(UUIDAuditBase):
    """One chat with the assistant. Server-side history is authoritative: the browser
    sends only its newest message, so this row and its turns are the whole record."""

    __tablename__ = "assistant_conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str | None] = mapped_column(String(200))

    turns: Mapped[list["AssistantTurn"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AssistantTurn.created_at",
    )


class AssistantTurn(UUIDAuditBase):
    """One agent run: the messages it produced (a Pydantic AI `new_messages_json()`
    payload, tool calls and returns included) plus what it cost."""

    __tablename__ = "assistant_turns"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"), index=True
    )
    messages: Mapped[list] = mapped_column(JSON, default=list)
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))

    conversation: Mapped["AssistantConversation"] = relationship(back_populates="turns")
