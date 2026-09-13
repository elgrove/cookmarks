from sqlalchemy import JSON, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import AIProvider, ModelRole, enum_values


class AIProviderConfig(Base):
    """One row per AI provider: its write-only API key, its saved display order, and
    the model IDs the administrator allows tasks to use.

    A provider with no key is not configured and is never eligible for task
    resolution. `model_ids` starts seeded from the provider's recommendations and
    grows only through free-text additions in the AI Configuration tab."""

    __tablename__ = "ai_provider_configs"

    provider: Mapped[AIProvider] = mapped_column(
        Enum(AIProvider, values_callable=enum_values), primary_key=True
    )
    api_key: Mapped[str | None] = mapped_column(String(200))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    model_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class AITaskAssignment(Base):
    """Which provider-and-model pair handles an AI task. A standard role has at most
    one row (position 0); the recipe-ingredient role holds an ordered sequence whose
    first entry is primary and each later entry is tried in order as a fallback."""

    __tablename__ = "ai_task_assignments"

    role: Mapped[ModelRole] = mapped_column(
        Enum(ModelRole, values_callable=enum_values), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    provider: Mapped[AIProvider] = mapped_column(
        Enum(AIProvider, values_callable=enum_values)
    )
    model_id: Mapped[str] = mapped_column(String(200))
