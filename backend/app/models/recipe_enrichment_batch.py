import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDAuditBase
from app.models.enums import EnrichmentBatchItemStatus, EnrichmentBatchStatus, enum_values

if TYPE_CHECKING:
    from app.models.recipe import Recipe
    from app.models.task_run import TaskRun


class RecipeEnrichmentBatch(UUIDAuditBase):
    """One durable chunk of the Gemini Batch backfill (MY-175).

    A parent backfill TaskRun owns many batch rows — one per local chunk per
    enrichment stage wave. The row persists local intent *before* any remote
    create, so a crash between remote create and local save reconciles by the
    deterministic display name instead of submitting a duplicate job.

    Never stores API keys, full prompts or full model responses — only the
    version snapshot, provider IDs, counts, errors and usage needed to audit
    and resume.
    """

    __tablename__ = "recipe_enrichment_batches"

    task_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), index=True
    )
    # Local intent key, unique per run: f"{run_uuid}:c{chunk:03d}:{stage}:a{attempt}".
    job_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    # Remote display name, unique and deterministic: contains the parent run
    # UUID, chunk number and attempt so an ambiguous submission reconciles by
    # exact-match query instead of creating a second remote job.
    display_name: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    provider_batch_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    status: Mapped[EnrichmentBatchStatus] = mapped_column(
        Enum(EnrichmentBatchStatus, values_callable=enum_values),
        default=EnrichmentBatchStatus.PREPARING,
    )
    # Which enrichment wave this chunk belongs to: "stage1" (ingredient
    # structuring) or "stage2" (facet/keyword assignment). Stage 2 contexts
    # need stage 1 AI ingredient names, so the two waves run sequentially.
    stage: Mapped[str] = mapped_column(String(20), default="stage1")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    input_file_id: Mapped[str | None] = mapped_column(String(200))
    result_file_id: Mapped[str | None] = mapped_column(String(200))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    # Exact request keys uploaded for this submission — ingest correlates only
    # these, never output order, so a provider row outside this set is rejected.
    submitted_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Version snapshot for audit/resume and pilot-version gating.
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    schema_version: Mapped[str | None] = mapped_column(String(40))
    taxonomy_version: Mapped[str | None] = mapped_column(String(40))
    provider: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(200))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    # Remote batch IDs seen as duplicates of this intent (adopt-one, record rest).
    duplicate_ids: Mapped[list[str]] = mapped_column(JSON, default=list)

    task_run: Mapped["TaskRun"] = relationship()
    items: Mapped[list["RecipeEnrichmentBatchItem"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class RecipeEnrichmentBatchItem(UUIDAuditBase):
    """One recipe inside a batch chunk, keyed by recipe UUID + source fingerprint."""

    __tablename__ = "recipe_enrichment_batch_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "request_key", name="uq_batch_item_request_key"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipe_enrichment_batches.id", ondelete="CASCADE"), index=True
    )
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    # f"{recipe_uuid}:{fingerprint[:12]}" — the JSONL "key" correlating rows.
    request_key: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[EnrichmentBatchItemStatus] = mapped_column(
        Enum(EnrichmentBatchItemStatus, values_callable=enum_values),
        default=EnrichmentBatchItemStatus.PENDING,
    )
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    provider_error: Mapped[str | None] = mapped_column(Text)
    provider_code: Mapped[str | None] = mapped_column(String(100))
    # Per-request usage as reported by the provider (input/output/cached tokens).
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Stage 1 AI ingredient names, captured at ingest so stage 2 contexts can be
    # built without re-reading provider output.
    stage1_ingredients: Mapped[list[str]] = mapped_column(JSON, default=list)
    # The full stage 1 response payload, persisted so the stage 2 apply step can
    # rebuild EnrichmentResponse.from_stages without another provider call.
    stage1_response: Mapped[dict] = mapped_column(JSON, default=dict)

    batch: Mapped["RecipeEnrichmentBatch"] = relationship(back_populates="items")
    recipe: Mapped["Recipe"] = relationship()
