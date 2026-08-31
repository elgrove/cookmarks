import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDAuditBase
from app.models.enums import RecipeEnrichmentStatus, enum_values

if TYPE_CHECKING:
    from app.models.recipe import Recipe
    from app.models.task_run import TaskRun


class RecipeEnrichmentState(UUIDAuditBase):
    __tablename__ = "recipe_enrichment_states"

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[RecipeEnrichmentStatus] = mapped_column(
        Enum(RecipeEnrichmentStatus, values_callable=enum_values),
        default=RecipeEnrichmentStatus.PENDING,
    )
    source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    schema_version: Mapped[str | None] = mapped_column(String(40))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    taxonomy_version: Mapped[str | None] = mapped_column(String(40))
    provider: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(200))
    last_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    task_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task_runs.id", ondelete="SET NULL")
    )
    recipe: Mapped["Recipe"] = relationship(back_populates="enrichment_state")
    task_run: Mapped["TaskRun | None"] = relationship()
