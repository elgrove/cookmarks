import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite drops the offset on the way back out, so a freshly-written row reads as
    aware and a re-read one as naive. Everything here is written as UTC — say so, or
    the wire emits two different timestamp formats for the same field."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class UUIDAuditBase(Base):
    """Mixin base: UUID primary key plus created/updated audit timestamps."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
