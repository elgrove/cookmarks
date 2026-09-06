import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import UUIDAuditBase
from app.text import fold

if TYPE_CHECKING:
    from app.models.recipe import Recipe


class CanonicalIngredient(UUIDAuditBase):
    """A canonical, library-wide ingredient identity."""

    __tablename__ = "canonical_ingredients"

    name: Mapped[str] = mapped_column(String(300), unique=True)
    name_folded: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    recipe_ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="canonical_ingredient"
    )

    @validates("name")
    def _fold_name(self, key: str, value: str) -> str:
        self.name_folded = fold(value)
        return value


class RecipeIngredient(UUIDAuditBase):
    """One ordered verbatim ingredient line for a recipe, linked to a canonical ingredient."""

    __tablename__ = "recipe_ingredients"
    __table_args__ = (UniqueConstraint("recipe_id", "position"),)

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    canonical_ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("canonical_ingredients.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    is_key: Mapped[bool] = mapped_column(Boolean, default=False)

    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients")
    canonical_ingredient: Mapped[CanonicalIngredient | None] = relationship(
        back_populates="recipe_ingredients"
    )

    @property
    def canonical_name(self) -> str | None:
        return self.canonical_ingredient.name if self.canonical_ingredient else None
