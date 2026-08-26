import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import Base, UUIDAuditBase
from app.text import fold

if TYPE_CHECKING:
    from app.models.book import Book
    from app.models.recipe_list import RecipeListItem
    from app.models.task_run import TaskRun

# The book↔keyword association table lives in app.models.book; Keyword.books
# references it by name so the two modules stay free of a runtime import cycle.


recipe_keywords = Table(
    "recipe_keywords",
    Base.metadata,
    Column("recipe_id", ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True),
    # Indexed independently of the (recipe_id, keyword_id) PK: the keyword facets and
    # the /api/keywords global list group by keyword_id, which the PK (led by recipe_id)
    # can't serve — without this SQLite rebuilds a transient index on every call.
    Column(
        "keyword_id",
        ForeignKey("keywords.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)


class Keyword(UUIDAuditBase):
    """A free-form tag (AI-generated), shared across recipes and books."""

    __tablename__ = "keywords"

    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)

    recipes: Mapped[list["Recipe"]] = relationship(
        secondary=recipe_keywords, back_populates="keywords"
    )
    books: Mapped[list["Book"]] = relationship(secondary="book_keywords", back_populates="keywords")


class Recipe(UUIDAuditBase):
    """An extracted recipe. Identity is stable across re-extraction so favourites
    and list membership survive; the extraction task reconciles by matching on the
    normalised name within a book rather than wiping and recreating rows."""

    __tablename__ = "recipes"

    book_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    extraction_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task_runs.id", ondelete="SET NULL")
    )
    order: Mapped[int]
    name: Mapped[str] = mapped_column(String(500))
    # Accent-stripped, lower-cased name. Stored because folding 21k rows per query
    # costs ~300ms against ~55ms for a plain scan of a stored column.
    name_folded: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str | None] = mapped_column(Text)
    ingredients: Mapped[list[str]] = mapped_column(JSON, default=list)
    instructions: Mapped[list[str]] = mapped_column(JSON, default=list)
    yields: Mapped[str | None] = mapped_column(String(200))
    image: Mapped[str | None] = mapped_column(Text)
    # Where the recipe sits in its book's EPUB, as resolved by the reader (a foliate
    # CFI). The pair is a tri-state: never checked (`epub_checked_at` null) · found
    # (both set) · checked and genuinely absent from the book's text (checked, no CFI).
    epub_cfi: Mapped[str | None] = mapped_column(Text)
    epub_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @validates("name")
    def _fold_name(self, key: str, value: str) -> str:
        self.name_folded = fold(value)
        return value

    book: Mapped["Book"] = relationship(back_populates="recipes")
    extraction_run: Mapped["TaskRun | None"] = relationship(back_populates="recipes")
    keywords: Mapped[list["Keyword"]] = relationship(
        secondary=recipe_keywords, back_populates="recipes"
    )
    list_items: Mapped[list["RecipeListItem"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
