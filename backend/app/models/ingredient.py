import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import UUIDAuditBase
from app.models.enums import (
    IngredientLineKind,
    IngredientParseMethod,
    IngredientResolutionMethod,
    enum_values,
)
from app.text import fold

if TYPE_CHECKING:
    from app.models.recipe import Recipe


class Ingredient(UUIDAuditBase):
    """A canonical, library-wide ingredient identity."""

    __tablename__ = "ingredients"

    name: Mapped[str] = mapped_column(String(300), unique=True)
    name_folded: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    aliases: Mapped[list["IngredientAlias"]] = relationship(
        back_populates="ingredient", cascade="all, delete-orphan"
    )
    occurrences: Mapped[list["IngredientOccurrence"]] = relationship(back_populates="ingredient")

    @validates("name")
    def _fold_name(self, key: str, value: str) -> str:
        self.name_folded = fold(value)
        return value


class IngredientAlias(UUIDAuditBase):
    """An accepted linguistic equivalent of an Ingredient's canonical name."""

    __tablename__ = "ingredient_aliases"

    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(300), unique=True)
    name_folded: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    ingredient: Mapped["Ingredient"] = relationship(back_populates="aliases")

    @validates("name")
    def _fold_name(self, key: str, value: str) -> str:
        self.name_folded = fold(value)
        return value


class IngredientLine(UUIDAuditBase):
    """One ordered, verbatim source line from a recipe's ingredients section."""

    __tablename__ = "ingredient_lines"
    __table_args__ = (UniqueConstraint("recipe_id", "position"),)

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[IngredientLineKind | None] = mapped_column(
        Enum(IngredientLineKind, values_callable=enum_values), nullable=True
    )
    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients_verbatim")
    occurrences: Mapped[list["IngredientOccurrence"]] = relationship(
        back_populates="line",
        cascade="all, delete-orphan",
        order_by="IngredientOccurrence.position",
    )


class IngredientOccurrence(UUIDAuditBase):
    """A parsed ingredient use from one source line."""

    __tablename__ = "ingredient_occurrences"
    __table_args__ = (UniqueConstraint("line_id", "position"),)

    line_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredient_lines.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    preparation: Mapped[str | None] = mapped_column(Text)
    optional: Mapped[bool] = mapped_column(Boolean, default=False)
    alternative_group: Mapped[int | None] = mapped_column(Integer)
    is_key: Mapped[bool] = mapped_column(Boolean, default=False)
    parse_method: Mapped[IngredientParseMethod] = mapped_column(
        Enum(IngredientParseMethod, values_callable=enum_values)
    )
    resolution_method: Mapped[IngredientResolutionMethod] = mapped_column(
        Enum(IngredientResolutionMethod, values_callable=enum_values)
    )
    line: Mapped["IngredientLine"] = relationship(back_populates="occurrences")
    ingredient: Mapped["Ingredient"] = relationship(back_populates="occurrences")
