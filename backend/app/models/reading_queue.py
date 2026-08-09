import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UUIDAuditBase


class ReadingQueueItem(UUIDAuditBase):
    """One row per (user, book): the caller has queued the book to read next. No
    position column — the queue reads newest-first by `created_at`."""

    __tablename__ = "reading_queue_items"
    __table_args__ = (UniqueConstraint("user_id", "book_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    book_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
