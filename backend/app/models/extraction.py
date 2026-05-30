import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDAuditBase
from app.models.enums import ExtractionMethod, ExtractionStatus, enum_values

if TYPE_CHECKING:
    from app.models.book import Book
    from app.models.recipe import Recipe


class ExtractionRun(UUIDAuditBase):
    """One extraction job for a book: lifecycle, strategy, progress, cost and
    outcome. Mirrors v1's ExtractionReport — recipe extraction is the proven area
    we carry over largely unchanged."""

    __tablename__ = "extraction_runs"

    book_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    provider_name: Mapped[str | None] = mapped_column(String(50))
    model_name: Mapped[str | None] = mapped_column(String(200))
    extraction_method: Mapped[ExtractionMethod | None] = mapped_column(
        Enum(ExtractionMethod, values_callable=enum_values)
    )
    status: Mapped[ExtractionStatus] = mapped_column(
        Enum(ExtractionStatus, values_callable=enum_values),
        default=ExtractionStatus.QUEUED,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_chapters: Mapped[int] = mapped_column(default=0)
    chapters_processed: Mapped[list[str]] = mapped_column(JSON, default=list)
    recipes_found: Mapped[int] = mapped_column(default=0)
    images_in_separate_chapters: Mapped[bool | None]
    images_can_be_matched: Mapped[bool | None]
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    errors: Mapped[list[str]] = mapped_column(JSON, default=list)

    book: Mapped["Book"] = relationship(back_populates="extraction_runs")
    recipes: Mapped[list["Recipe"]] = relationship(back_populates="extraction_run")
