import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UUIDAuditBase, utcnow


class RecipeView(UUIDAuditBase):
    """One row per (user, recipe): that a user has seen the recipe, and how often.

    Not an event log — the read percentage counts distinct rows, and a growing
    time-series of opens is not something anything reads. `created_at` is the
    first view; `last_viewed_at` moves on every open."""

    __tablename__ = "recipe_views"
    __table_args__ = (UniqueConstraint("user_id", "recipe_id"),)

    # No index on user_id: the (user_id, recipe_id) unique constraint already indexes
    # it as the leading column, which every lookup here goes through.
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    view_count: Mapped[int] = mapped_column(default=1)
    last_viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
