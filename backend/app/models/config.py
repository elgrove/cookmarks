from sqlalchemy import Enum, String
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
