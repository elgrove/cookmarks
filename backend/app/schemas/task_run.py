import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from app.models.enums import TaskStatus, TaskType
from app.schemas.extraction import ReviewQuestion

if TYPE_CHECKING:
    from app.models.task_run import TaskRun


class TaskRunRead(BaseModel):
    """The wire view of one task run, whatever its type: lifecycle, cost and the
    type-specific metrics in `detail`. Returned by the task-runs index (with an optional
    type filter), the extraction trigger/latest/resume endpoints, and the admin reporting
    view. `book_id`/`book_title` are populated only for extraction runs; `pending_question`
    only while an extraction is paused at REVIEW. `detail` carries each type's own metrics
    (extraction: method/chapters/recipes/images; book-keywords: tagged/eligible; dedup:
    keywords in/merges/removed; calibre: created/updated/orphaned)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_type: TaskType
    status: TaskStatus
    book_id: uuid.UUID | None
    book_title: str | None
    provider_name: str | None
    model_name: str | None
    cost_usd: Decimal | None
    input_tokens: int | None
    output_tokens: int | None
    errors: list[str]
    detail: dict
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    pending_question: ReviewQuestion | None

    @classmethod
    def from_run(cls, run: "TaskRun") -> "TaskRunRead":
        """Build from an ORM row. Extraction's typed columns are folded into `detail`
        (chapters_processed collapsed to its count); other task types report through the
        row's stored `detail`. The pending review question rides along only while an
        extraction is paused at REVIEW."""
        if run.task_type == TaskType.EXTRACTION:
            detail: dict = {
                **run.detail,
                "extraction_method": run.extraction_method,
                "total_chapters": run.total_chapters,
                "chapters_processed": len(run.chapters_processed),
                "recipes_found": run.recipes_found,
                "images_in_separate_chapters": run.images_in_separate_chapters,
                "images_can_be_matched": run.images_can_be_matched,
            }
        else:
            detail = dict(run.detail)

        return cls(
            id=run.id,
            task_type=run.task_type,
            status=run.status,
            book_id=run.book_id,
            book_title=run.book.title if run.book is not None else None,
            provider_name=run.provider_name,
            model_name=run.model_name,
            cost_usd=run.cost_usd,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            errors=list(run.errors),
            detail=detail,
            created_at=run.created_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            pending_question=(
                ReviewQuestion.current() if run.status == TaskStatus.REVIEW else None
            ),
        )
