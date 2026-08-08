import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UUIDAuditBase, utcnow
from app.models.enums import ReadingMode, enum_values


class BookReading(UUIDAuditBase):
    """One row per (user, book): that the caller is reading the book, which way, and how
    far they have got.

    Progress is **recipe-anchored in both modes** — `anchor_recipe_id` is the furthest
    recipe reached, whether they walked to it through the app or turned pages past it in
    the reader — so the two modes share one position and either can resume where the
    other stopped. `location` is the reader's own page, kept only so returning to the
    pages lands exactly where they were left rather than at the anchor."""

    __tablename__ = "book_readings"
    __table_args__ = (UniqueConstraint("user_id", "book_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    book_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[ReadingMode] = mapped_column(
        Enum(ReadingMode, values_callable=enum_values), default=ReadingMode.BOOK
    )
    anchor_recipe_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"), default=None
    )
    location: Mapped[str | None] = mapped_column(default=None)
    finished: Mapped[bool] = mapped_column(default=False)
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
