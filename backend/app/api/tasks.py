import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.db import SessionDep
from app.models.book import Book
from app.models.enums import TaskStatus, TaskType
from app.models.recipe import Keyword
from app.models.task_run import TaskRun
from app.schemas.tasks import (
    BookKeywordTaskRequest,
    EnrichmentBackfillRequest,
    EnrichmentBackfillResumeRequest,
    TaskRunAck,
)
from app.services.ai import get_ai_provider, get_config, get_recipe_enrichment_providers
from app.services.ai.base import ModelRole
from app.services.recipe_enrichment.batch import BATCH_DEFAULT_MAX_ACTIVE_JOBS
from app.services.recipe_enrichment.schema import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    TAXONOMY_VERSION,
)
from app.tasks.book_keywords import enqueue_backfill_book_keywords
from app.tasks.calibre_sync import enqueue_calibre_sync
from app.tasks.enrichment_backfill import enqueue_enrichment_backfill, select_backfill_recipe_ids
from app.tasks.keyword_dedup import enqueue_dedup_keywords
from app.tasks.recipe_enrichment import choose_pilot_sample, enqueue_recipe_enrichment_pilot
from app.tasks.runs import create_task_run

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "/book-keywords",
    response_model=TaskRunAck,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_book_keywords(body: BookKeywordTaskRequest, session: SessionDep) -> TaskRunAck:
    """Queue AI generation of book-level keywords across the library. By default tags
    only extracted books that have none yet; `regenerate` re-tags every extracted book.
    Records a queued TaskRun and dispatches to the worker; returns how many books are
    eligible (the count the task will work through), not a live progress handle."""
    stmt = select(func.count()).select_from(Book).where(Book.recipes.any())
    if not body.regenerate:
        stmt = stmt.where(~Book.keywords.any())
    eligible = session.scalar(stmt) or 0

    run = create_task_run(session, TaskType.BOOK_KEYWORDS, detail={"regenerate": body.regenerate})
    enqueue_backfill_book_keywords(str(run.id), body.regenerate)
    return TaskRunAck(task="book_keywords", status="queued", queued=eligible)


@router.post(
    "/dedup-keywords",
    response_model=TaskRunAck,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_dedup_keywords(session: SessionDep) -> TaskRunAck:
    """Queue an AI-assisted dedup of the whole keyword vocabulary, merging near-duplicate
    tags ("Veggie" -> "Vegetarian") across recipes and books. Records a queued TaskRun and
    dispatches to the worker; returns the vocabulary size it will analyse."""
    vocabulary = session.scalar(select(func.count()).select_from(Keyword)) or 0
    run = create_task_run(session, TaskType.KEYWORD_DEDUP)
    enqueue_dedup_keywords(str(run.id))
    return TaskRunAck(task="keyword_dedup", status="queued", queued=vocabulary)


@router.post(
    "/calibre-sync",
    response_model=TaskRunAck,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_calibre_sync(session: SessionDep) -> TaskRunAck:
    """Queue a sync of the Calibre library into the v2 DB, upserting books by calibre_id.
    Records a queued TaskRun and dispatches to the worker; the count of books reconciled
    isn't known until the worker reads the library, so `queued` is 0 — the run's `detail`
    carries the created/updated/orphaned/deleted result once it completes."""
    run = create_task_run(session, TaskType.CALIBRE_SYNC)
    enqueue_calibre_sync(str(run.id))
    return TaskRunAck(task="calibre_sync", status="queued", queued=0)


@router.post(
    "/recipe-enrichment-pilot",
    response_model=TaskRunAck,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_recipe_enrichment_pilot(session: SessionDep) -> TaskRunAck:
    """Queue the reviewed 100-recipe live-provider enrichment pilot, never Batch."""
    sample = choose_pilot_sample(session)
    run = create_task_run(session, TaskType.RECIPE_ENRICHMENT_PILOT, detail=sample)
    run.provider_name = get_config(session).ai_provider
    session.commit()
    enqueue_recipe_enrichment_pilot(str(run.id))
    return TaskRunAck(task="recipe_enrichment_pilot", status="queued", queued=len(sample["recipe_ids"]))


def _stage_models(session: SessionDep) -> tuple[str | None, str | None, str | None]:
    """Effective enrichment provider name and stage model names.

    Explicit per-stage config wins; unconfigured stages fall back to the
    default provider, mirroring the worker's resolution.
    """
    default = get_ai_provider(session)
    stage1, stage2 = get_recipe_enrichment_providers(session)
    stage1 = stage1 or default
    stage2 = stage2 or default
    if stage1 is None or stage2 is None:
        return None, None, None
    return (
        f"{stage1.name}->{stage2.name}",
        stage1.model_for(ModelRole.RECIPE_INGREDIENTS),
        stage2.model_for(ModelRole.RECIPE_SEMANTICS),
    )


def _require_gemini(session: SessionDep) -> tuple[str, str]:
    """The backfill runs on Gemini Batch only — any other provider is a 422.

    Both enrichment stages must resolve to Gemini, since both waves submit.
    Returns the stage model names for the run row.
    """
    provider, stage1_model, stage2_model = _stage_models(session)
    if provider != "GEMINI->GEMINI" or not stage1_model or not stage2_model:
        raise HTTPException(
            status_code=422,
            detail="Recipe-enrichment backfill requires the Gemini provider",
        )
    return stage1_model, stage2_model


def _require_no_active_backfill(session: SessionDep) -> None:
    active = session.scalar(
        select(func.count())
        .select_from(TaskRun)
        .where(
            TaskRun.task_type == TaskType.RECIPE_ENRICHMENT_BACKFILL,
            TaskRun.status.in_(
                [TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.WAITING]
            ),
        )
    ) or 0
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A recipe-enrichment backfill is already active",
        )


def _check_pilot(session: SessionDep, pilot_run_id: uuid.UUID, confirmed: bool) -> TaskRun:
    """Gate the backfill on a reviewed, version-matching done pilot run."""
    if not confirmed:
        raise HTTPException(
            status_code=422,
            detail="Confirm the pilot output was reviewed before launching the backfill",
        )
    pilot = session.get(TaskRun, pilot_run_id)
    if (
        pilot is None
        or pilot.task_type != TaskType.RECIPE_ENRICHMENT_PILOT
        or pilot.status != TaskStatus.DONE
    ):
        raise HTTPException(
            status_code=422,
            detail="pilot_run_id must be a done recipe-enrichment pilot run",
        )
    expected = {
        "provider": "GEMINI->GEMINI",
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
    }
    mismatched = [
        key for key, value in expected.items() if pilot.detail.get(key) != value
    ]
    _provider, stage1_model, stage2_model = _stage_models(session)
    for key, value in (("stage1_model", stage1_model), ("stage2_model", stage2_model)):
        if value is None or pilot.detail.get(key) != value:
            mismatched.append(key)
    if mismatched:
        raise HTTPException(
            status_code=422,
            detail=f"Pilot contract mismatch on: {', '.join(mismatched)}",
        )
    return pilot


@router.post(
    "/recipe-enrichment-backfill",
    response_model=TaskRunAck,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_recipe_enrichment_backfill(
    body: EnrichmentBackfillRequest, session: SessionDep
) -> TaskRunAck:
    """Queue the durable Gemini Batch backfill over recipes not yet current.

    Launches only with a done, version-matching MY-174 pilot run and an explicit
    reviewed confirmation, and only when no other backfill is active. The pilot
    run ID and approval land on the parent run's detail for audit. The queued
    count is advisory: the worker recounts outstanding recipes at start.
    """
    stage1_model, stage2_model = _require_gemini(session)
    _require_no_active_backfill(session)
    pilot = _check_pilot(session, body.pilot_run_id, body.confirm_pilot_reviewed)
    max_active = body.max_active_jobs or BATCH_DEFAULT_MAX_ACTIVE_JOBS
    run = create_task_run(
        session,
        TaskType.RECIPE_ENRICHMENT_BACKFILL,
        detail={
            "pilot_run_id": str(pilot.id),
            "pilot_reviewed": True,
            "max_active_jobs": max_active,
        },
    )
    run.provider_name = "GEMINI"
    run.model_name = f"{stage1_model} -> {stage2_model}"
    session.commit()
    eligible = len(select_backfill_recipe_ids(session))
    enqueue_enrichment_backfill(str(run.id))
    return TaskRunAck(task="recipe_enrichment_backfill", status="queued", queued=eligible)


def _prior_backfill(session: SessionDep) -> TaskRun | None:
    return session.scalars(
        select(TaskRun)
        .where(TaskRun.task_type == TaskType.RECIPE_ENRICHMENT_BACKFILL)
        .order_by(TaskRun.created_at.desc())
        .limit(1)
    ).first()


@router.post(
    "/recipe-enrichment-backfill/resume",
    response_model=TaskRunAck,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_recipe_enrichment_backfill(
    body: EnrichmentBackfillResumeRequest, session: SessionDep
) -> TaskRunAck:
    """Resume idempotently: a fresh parent run selects only outstanding recipes.

    Resuming a previous backfill needs no new approval — it continues reviewed
    work. A first-ever launch through this endpoint requires the same reviewed
    pilot approval as the trigger, so the gate cannot be bypassed.
    """
    stage1_model, stage2_model = _require_gemini(session)
    _require_no_active_backfill(session)
    prior = _prior_backfill(session)
    max_active = body.max_active_jobs or BATCH_DEFAULT_MAX_ACTIVE_JOBS
    detail: dict = {"resumed": True, "max_active_jobs": max_active}
    if prior is None:
        if body.pilot_run_id is None:
            raise HTTPException(
                status_code=422,
                detail="No previous backfill exists: supply a reviewed pilot_run_id",
            )
        pilot = _check_pilot(session, body.pilot_run_id, body.confirm_pilot_reviewed)
        detail["pilot_run_id"] = str(pilot.id)
        detail["pilot_reviewed"] = True
    else:
        detail["resume_of"] = str(prior.id)
        if prior.status not in (TaskStatus.DONE, TaskStatus.FAILED):
            raise HTTPException(
                status_code=422,
                detail="A previous backfill run exists but is not terminal",
            )
    run = create_task_run(
        session,
        TaskType.RECIPE_ENRICHMENT_BACKFILL,
        detail=detail,
    )
    run.provider_name = "GEMINI"
    run.model_name = f"{stage1_model} -> {stage2_model}"
    session.commit()
    eligible = len(select_backfill_recipe_ids(session))
    enqueue_enrichment_backfill(str(run.id))
    return TaskRunAck(task="recipe_enrichment_backfill", status="queued", queued=eligible)
