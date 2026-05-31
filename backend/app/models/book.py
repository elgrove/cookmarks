from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDAuditBase

if TYPE_CHECKING:
    from app.models.extraction import ExtractionRun
    from app.models.recipe import Recipe


class Book(UUIDAuditBase):
    """A cookbook mirrored from the Calibre library; the anchor for its recipes."""

    __tablename__ = "books"

    calibre_id: Mapped[int] = mapped_column(unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(500), index=True)
    isbn: Mapped[str | None] = mapped_column(String(50))
    pubdate: Mapped[date | None]
    description: Mapped[str] = mapped_column(Text, default="")
    # Book directory relative to settings.calibre_library_path (e.g.
    # "Neelam Batra/1,000 Indian Recipes (141)") — never an absolute path.
    path: Mapped[str] = mapped_column(String(1000))
    calibre_added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recipes: Mapped[list["Recipe"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    extraction_runs: Mapped[list["ExtractionRun"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
