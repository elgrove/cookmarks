from sqlalchemy import JSON, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import AIProvider, enum_values


class Config(Base):
    """Singleton application configuration (row id=1). Intentionally minimal — it
    grows as later milestones add settings. The API key is write-only at the
    schema layer and never serialised back to the client."""

    __tablename__ = "config"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    ai_provider: Mapped[AIProvider | None] = mapped_column(
        Enum(AIProvider, values_callable=enum_values)
    )
    api_key: Mapped[str | None] = mapped_column(String(200))
    assistant_provider: Mapped[AIProvider | None] = mapped_column(
        Enum(AIProvider, values_callable=enum_values)
    )
    assistant_api_key: Mapped[str | None] = mapped_column(String(200))
    enrichment_stage1_provider: Mapped[AIProvider | None] = mapped_column(
        Enum(AIProvider, values_callable=enum_values)
    )
    enrichment_stage1_api_key: Mapped[str | None] = mapped_column(String(200))
    enrichment_stage2_provider: Mapped[AIProvider | None] = mapped_column(
        Enum(AIProvider, values_callable=enum_values)
    )
    enrichment_stage2_api_key: Mapped[str | None] = mapped_column(String(200))
    # Shared per-minute request budget for extraction across all worker threads.
    extraction_rate_limit_per_minute: Mapped[int] = mapped_column(default=256)
    # Optional per-role model overrides ({ModelRole value: model name}); a role left
    # out falls back to the provider's default. Lets each task use a different model.
    model_overrides: Mapped[dict[str, str] | None] = mapped_column(JSON, default=None)
