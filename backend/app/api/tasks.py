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
from app.services.ai import get_config
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


def _require_gemini(session: SessionDep) -> None:
    """The backfill runs on Gemini Batch only — any other provider is a 422."""
    if get_config(session).ai_provider != "GEMINI":
        raise HTTPException(
            status_code=422,
            detail="Recipe-enrichment backfill requires the Gemini provider",
        )


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
        "provider": "GEMINI",
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
    }
    mismatched = [
        key for key, value in expected.items() if pilot.detail.get(key) != value
    ]
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
    run ID and approval land on the parent run's detail for audit.
    """
    _require_gemini(session)
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
    session.commit()
    eligible = len(select_backfill_recipe_ids(session))
    enqueue_enrichment_backfill(str(run.id))
    return TaskRunAck(task="recipe_enrichment_backfill", status="queued", queued=eligible)


@router.post(
    "/recipe-enrichment-backfill/resume",
    response_model=TaskRunAck,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_recipe_enrichment_backfill(
    body: EnrichmentBackfillResumeRequest, session: SessionDep
) -> TaskRunAck:
    """Resume idempotently: a fresh parent run selects only outstanding recipes."""
    _require_gemini(session)
    _require_no_active_backfill(session)
    max_active = body.max_active_jobs or BATCH_DEFAULT_MAX_ACTIVE_JOBS
    run = create_task_run(
        session,
        TaskType.RECIPE_ENRICHMENT_BACKFILL,
        detail={"resumed": True, "max_active_jobs": max_active},
    )
    run.provider_name = "GEMINI"
    session.commit()
    eligible = len(select_backfill_recipe_ids(session))
    enqueue_enrichment_backfill(str(run.id))
    return TaskRunAck(task="recipe_enrichment_backfill", status="queued", queued=eligible)
