import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import UUIDAuditBase
from app.text import fold

if TYPE_CHECKING:
    from app.models.recipe import Recipe


class Ingredient(UUIDAuditBase):
    """A canonical, library-wide ingredient identity."""

    __tablename__ = "ingredients"

    name: Mapped[str] = mapped_column(String(300), unique=True)
    name_folded: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    recipe_associations: Mapped[list["RecipeCanonicalIngredient"]] = relationship(
        back_populates="ingredient", cascade="all, delete-orphan"
    )

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
    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients_verbatim")


class RecipeCanonicalIngredient(UUIDAuditBase):
    """A canonical ingredient associated with a recipe, with an optional key flag."""

    __tablename__ = "recipe_canonical_ingredients"
    __table_args__ = (UniqueConstraint("recipe_id", "ingredient_id"),)

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), index=True
    )
    is_key: Mapped[bool] = mapped_column(Boolean, default=False)

    recipe: Mapped["Recipe"] = relationship(back_populates="canonical_ingredients")
    ingredient: Mapped["Ingredient"] = relationship(back_populates="recipe_associations")

    @property
    def name(self) -> str:
        return self.ingredient.name

