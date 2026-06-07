import string
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ExtractionMethod, ExtractionStatus
from app.services.extraction.review import REVIEW_CHOICES, REVIEW_QUESTION

if TYPE_CHECKING:
    from app.models.extraction import ExtractionRun


class ReviewChoice(BaseModel):
    """One answer the operator can give to a paused run's question: the resume token
    (`value`) and the label shown on the choice."""

    value: str
    label: str


class ReviewQuestion(BaseModel):
    """The pending human-in-the-loop question on a run paused at REVIEW — what to ask
    and the choices to offer. Built from the extraction review constants so the graph
    (which raises the interrupt) and the UI (which answers it) never drift."""

    question: str
    choices: list[ReviewChoice]

    @classmethod
    def current(cls) -> "ReviewQuestion":
        return cls(
            question=REVIEW_QUESTION,
            choices=[ReviewChoice(value=value, label=label) for value, label in REVIEW_CHOICES],
        )


class ResumeRequest(BaseModel):
    """The operator's answer to a paused run's review question. `response` must be one
    of the choices the graph offers (validated in the endpoint)."""

    response: str


class ExtractionRunRead(BaseModel):
    """The wire view of one extraction run: lifecycle, strategy, progress, and cost.
    Returned by the trigger endpoint (a freshly-queued run), the latest-run endpoint,
    and the honest record the history/reports view (MY-11) reads. `chapters_processed`
    is the count of the underlying progress list, not the list itself. `pending_question`
    is populated only when the run is paused at REVIEW awaiting a human decision."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    book_id: uuid.UUID
    status: ExtractionStatus
    provider_name: str | None
    model_name: str | None
    extraction_method: ExtractionMethod | None
    total_chapters: int
    chapters_processed: int
    recipes_found: int
    cost_usd: Decimal | None
    input_tokens: int | None
    output_tokens: int | None
    errors: list[str]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    pending_question: ReviewQuestion | None

    @classmethod
    def from_run(cls, run: "ExtractionRun") -> "ExtractionRunRead":
        """Build from an ORM row, collapsing the chapters_processed JSON list to its
        count (the wire field is a number, not the list of processed file paths) and
        attaching the pending review question only while the run is paused at REVIEW."""
        return cls(
            id=run.id,
            book_id=run.book_id,
            status=run.status,
            provider_name=run.provider_name,
            model_name=run.model_name,
            extraction_method=run.extraction_method,
            total_chapters=run.total_chapters,
            chapters_processed=len(run.chapters_processed),
            recipes_found=run.recipes_found,
            cost_usd=run.cost_usd,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            errors=list(run.errors),
            created_at=run.created_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            pending_question=(
                ReviewQuestion.current() if run.status == ExtractionStatus.REVIEW else None
            ),
        )


class RecipeData(BaseModel):
    """A single AI-extracted recipe: validated against the schema.org-style keys the
    model returns (hence the field aliases) and lightly normalised. The pipeline
    injects author/bookTitle/bookOrder before the recipe is persisted."""

    name: str
    description: str | None = None
    ingredients: list[str] = Field(min_length=1, alias="recipeIngredients")
    instructions: list[str] = Field(min_length=1, alias="recipeInstructions")
    yields: str | None = Field(None, alias="recipeYield")
    image: str | None = None
    keywords: list[str] = Field(default_factory=list)
    author: str | None = None
    book_title: str | None = Field(None, alias="bookTitle")
    book_order: int | None = Field(None, alias="bookOrder")

    model_config = ConfigDict(populate_by_name=True)

    def model_post_init(self, _context: object) -> None:
        self.name = string.capwords(self.name)
        if self.yields:
            self.yields = (
                self.yields.capitalize() if self.yields[0].isalpha() else self.yields.lower()
            )
