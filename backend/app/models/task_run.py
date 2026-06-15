import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDAuditBase
from app.models.enums import ExtractionMethod, TaskStatus, TaskType, enum_values

if TYPE_CHECKING:
    from app.models.book import Book
    from app.models.recipe import Recipe


class TaskRun(UUIDAuditBase):
    """One run of a background job: lifecycle, cost and outcome, with task-specific
    metrics in `detail`. Extraction is one `task_type` among several (book-keyword
    tagging, keyword dedup, Calibre sync) — it keeps its proven typed columns (method,
    chapter progress, image flags, recipes found) since it is carried over unchanged;
    the other task types leave those null and report through `detail` instead."""

    __tablename__ = "task_runs"

    task_type: Mapped[TaskType] = mapped_column(
        Enum(TaskType, values_callable=enum_values), index=True
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, values_callable=enum_values),
        default=TaskStatus.QUEUED,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    errors: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Task-specific metrics for non-extraction types (extraction uses its typed columns).
    detail: Mapped[dict] = mapped_column(JSON, default=dict)

    # Generic across AI-backed tasks (extraction, book-keywords, dedup); null for Calibre.
    provider_name: Mapped[str | None] = mapped_column(String(50))
    model_name: Mapped[str | None] = mapped_column(String(200))
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]

    # Extraction-specific: set only on extraction runs.
    book_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    extraction_method: Mapped[ExtractionMethod | None] = mapped_column(
        Enum(ExtractionMethod, values_callable=enum_values)
    )
    total_chapters: Mapped[int] = mapped_column(default=0)
    chapters_processed: Mapped[list[str]] = mapped_column(JSON, default=list)
    recipes_found: Mapped[int] = mapped_column(default=0)
    images_in_separate_chapters: Mapped[bool | None]
    images_can_be_matched: Mapped[bool | None]

    book: Mapped["Book | None"] = relationship(back_populates="extraction_runs")
    recipes: Mapped[list["Recipe"]] = relationship(back_populates="extraction_run")
