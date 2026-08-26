from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import Base, UUIDAuditBase
from app.text import fold

if TYPE_CHECKING:
    from app.models.recipe import Keyword, Recipe
    from app.models.task_run import TaskRun


book_keywords = Table(
    "book_keywords",
    Base.metadata,
    Column("book_id", ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    # Indexed like recipe_keywords.keyword_id: the shared-keyword joins and any
    # group-by on keyword_id can't be served by the (book_id, keyword_id) PK.
    Column(
        "keyword_id",
        ForeignKey("keywords.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)


class Book(UUIDAuditBase):
    """A cookbook mirrored from the Calibre library; the anchor for its recipes."""

    __tablename__ = "books"

    calibre_id: Mapped[int] = mapped_column(unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(500), index=True)
    # Accent-stripped, lower-cased copies for search — see Recipe.name_folded.
    title_folded: Mapped[str] = mapped_column(String(500), default="")
    author_folded: Mapped[str] = mapped_column(String(500), default="")
    isbn: Mapped[str | None] = mapped_column(String(50))
    pubdate: Mapped[date | None]
    description: Mapped[str] = mapped_column(Text, default="")
    # Book directory relative to settings.calibre_library_path (e.g.
    # "Neelam Batra/1,000 Indian Recipes (141)") — never an absolute path.
    path: Mapped[str] = mapped_column(String(1000))
    calibre_added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @validates("title", "author")
    def _fold_text(self, key: str, value: str) -> str:
        setattr(self, f"{key}_folded", fold(value))
        return value

    recipes: Mapped[list["Recipe"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    # Only extraction task runs carry a book_id, so this lists this book's extractions.
    extraction_runs: Mapped[list["TaskRun"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    # AI-generated book-level tags (cuisine/theme/style), drawn from the same shared
    # Keyword vocabulary as recipes — unlinking a book leaves the keyword in place.
    keywords: Mapped[list["Keyword"]] = relationship(
        secondary=book_keywords, back_populates="books"
    )
