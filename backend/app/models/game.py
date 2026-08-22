import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UUIDAuditBase


class GameDismissal(UUIDAuditBase):
    """One row per (user, recipe): the user swiped the recipe away in the discover
    game. Permanent by design — there is no undo and no reset — so the game feed
    never serves the recipe to that user again."""

    __tablename__ = "game_dismissals"
    __table_args__ = (UniqueConstraint("user_id", "recipe_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
