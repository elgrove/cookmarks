import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDAuditBase

if TYPE_CHECKING:
    from app.models.recipe import Recipe


class RecipeList(UUIDAuditBase):
    """A user collection of recipes. The favourites list is the single default."""

    __tablename__ = "recipe_lists"
    # One Favourites list per user, enforced by the database — the API creates it
    # lazily from several endpoints, which can otherwise race.
    __table_args__ = (
        Index(
            "uq_recipe_lists_default_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("is_default = 1"),
        ),
    )

    name: Mapped[str] = mapped_column(String(200))
    is_default: Mapped[bool] = mapped_column(default=False)
    # Nullable only for the pre-accounts rows: the first user created adopts every
    # orphan list. The application always sets it.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, default=None
    )

    items: Mapped[list["RecipeListItem"]] = relationship(
        back_populates="recipe_list",
        cascade="all, delete-orphan",
        order_by="RecipeListItem.position",
    )


class RecipeListItem(UUIDAuditBase):
    __tablename__ = "recipe_list_items"
    __table_args__ = (UniqueConstraint("recipe_list_id", "recipe_id"),)

    recipe_list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipe_lists.id", ondelete="CASCADE"), index=True
    )
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(default=0)

    recipe_list: Mapped["RecipeList"] = relationship(back_populates="items")
    recipe: Mapped["Recipe"] = relationship(back_populates="list_items")
