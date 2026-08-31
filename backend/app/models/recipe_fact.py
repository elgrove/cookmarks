import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDAuditBase
from app.models.enums import RecipeFacetKind, RecipeFactSource, enum_values

if TYPE_CHECKING:
    from app.models.recipe import Recipe


class RecipeFacetValue(UUIDAuditBase):
    __tablename__ = "recipe_facet_values"
    __table_args__ = (UniqueConstraint("kind", "value_id"),)

    kind: Mapped[RecipeFacetKind] = mapped_column(
        Enum(RecipeFacetKind, values_callable=enum_values)
    )
    value_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100), unique=True)
    vocabulary_version: Mapped[str] = mapped_column(String(40))
    facts: Mapped[list["RecipeFacet"]] = relationship(back_populates="facet_value")


class RecipeFacet(UUIDAuditBase):
    __tablename__ = "recipe_facets"
    __table_args__ = (UniqueConstraint("recipe_id", "facet_value_id"),)

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    facet_value_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipe_facet_values.id", ondelete="RESTRICT"), index=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[RecipeFactSource] = mapped_column(
        Enum(RecipeFactSource, values_callable=enum_values)
    )
    evidence: Mapped[str | None] = mapped_column(Text)
    recipe: Mapped["Recipe"] = relationship(back_populates="facets")
    facet_value: Mapped["RecipeFacetValue"] = relationship(back_populates="facts")


class RecipeCuisine(UUIDAuditBase):
    """A direct accepted-cuisine ID from the MY-170 hierarchy asset."""

    __tablename__ = "recipe_cuisines"
    __table_args__ = (UniqueConstraint("recipe_id", "cuisine_id"),)

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    cuisine_id: Mapped[str] = mapped_column(String(200), index=True)
    source: Mapped[RecipeFactSource] = mapped_column(
        Enum(RecipeFactSource, values_callable=enum_values)
    )
    evidence: Mapped[str | None] = mapped_column(Text)
    recipe: Mapped["Recipe"] = relationship(back_populates="cuisines")
