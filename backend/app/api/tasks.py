from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.db import SessionDep
from app.models.book import Book
from app.models.enums import TaskType
from app.models.recipe import Keyword
from app.schemas.tasks import BookKeywordTaskRequest, TaskRunAck
from app.services.ai import get_config
from app.tasks.book_keywords import enqueue_backfill_book_keywords
from app.tasks.calibre_sync import enqueue_calibre_sync
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
