from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Config(Base):
    """Singleton application configuration (row id=1). AI provider keys, model lists
    and task assignments live in `ai_provider_configs` / `ai_task_assignments`; this
    table keeps only the non-AI settings. API keys stay write-only and are never
    serialised back to the client."""

    __tablename__ = "config"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    # Shared per-minute request budget for extraction across all worker threads.
    extraction_rate_limit_per_minute: Mapped[int] = mapped_column(default=256)
