import json
import logging
import uuid
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.epub import epub_path, has_epub, has_pdf, pdf_path
from app.models.book import Book
from app.models.enums import RecipeEnrichmentStatus, TaskStatus, TaskType
from app.models.ingredient import IngredientLine
from app.models.recipe import Recipe
from app.models.recipe_enrichment import RecipeEnrichmentState
from app.models.task_run import TaskRun
from app.schemas.extraction import RecipeData
from app.services.ai import get_config
from app.services.book_keywords import generate_book_keywords
from app.services.embeddings import embed_recipes
from app.services.extraction.graph import get_extraction_graph
from app.services.extraction.review import VALID_HUMAN_RESPONSES
from app.services.keywords import get_or_create_keyword
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def enqueue_extract_recipes(book_id: str, run_id: str) -> None:
    """Dispatch the extraction task to the Celery worker. The single seam the trigger
    endpoint goes through (and tests stub) so a queued run never blocks the request
    thread and the dispatch stays out of the API and contract layers."""
    extract_recipes_from_book_task.delay(book_id, run_id)


EXTRACTION_NEEDS_BOOK_FILE = "recipe extraction needs an EPUB or PDF"


class NotExtractableError(Exception):
    """The book holds nothing the pipeline can read."""


def queue_extraction(session: Session, book: Book) -> TaskRun:
    """Record a QUEUED extraction run for a book and dispatch it. Shared by the manual
    trigger and the ingest task's extract-after-add, so both leave the same record.

    Raises NotExtractableError for a book with no supported file."""
    if not has_epub(book) and not has_pdf(book):
        raise NotExtractableError(EXTRACTION_NEEDS_BOOK_FILE)
    run = TaskRun(
        task_type=TaskType.EXTRACTION,
        book_id=book.id,
        provider_name=get_config(session).ai_provider,
        status=TaskStatus.QUEUED,
    )
    session.add(run)
    session.commit()
    enqueue_extract_recipes(str(book.id), str(run.id))
    return run


def enqueue_resume_extraction(run_id: str, human_response: str) -> None:
    """Dispatch the resume of a paused run to the worker — the seam the resume endpoint
    goes through (and tests stub) so answering the review question drives the graph to
    completion off the request thread, mirroring the trigger dispatch."""
    resume_extraction_task.delay(run_id, human_response)


def _mark_run_failed(extraction_id: str, exc: Exception) -> None:
    """Record a crashed run on its row: status FAILED, the error appended, completed
    stamped — so a worker exception leaves an honest record instead of a run wedged
    in RUNNING forever. Best-effort: a failure here must not mask the original."""
    try:
        with SessionLocal() as session:
            run = session.get(TaskRun, uuid.UUID(extraction_id))
            if run is None:
                return
            run.status = TaskStatus.FAILED
            run.errors = [*run.errors, str(exc)]
            run.completed_at = datetime.now(UTC)
            session.commit()
    except Exception:
        logger.exception(f"Failed to mark run {extraction_id} as failed")


def _thread_id(run_id: str) -> str:
    """Deterministic LangGraph checkpoint thread id for a run, so a later resume
    finds the saved state without persisting the id on the row."""
    return f"run_{run_id}"


def generate_recipe_embeddings(session: Session, recipes: list[Recipe]) -> None:
    """Embed the just-saved recipes so they're semantically searchable. Best-effort:
    a no-op when no embedding-capable provider is configured, so extraction always
    completes. Writes ride the caller's transaction (committed by save_recipes...)."""
    embed_recipes(session, recipes)


def _generate_book_keywords(session: Session, book: Book) -> None:
    """Tag the book from its freshly-saved recipes. Best-effort, like embeddings: a
    no-op without an AI provider, and never allowed to fail the extraction."""
    try:
        generate_book_keywords(session, book)
    except Exception:
        logger.exception(f"Book-keyword generation failed for {book.title}")


def _upsert_recipe(session: Session, book: Book, run: TaskRun, data: RecipeData) -> Recipe:
    """Reconcile by normalised name within the book: update the existing recipe in
    place if one matches, else create it. Identity is stable across re-extraction so
    favourites and list membership survive a re-run."""
    recipe = session.scalar(
        select(Recipe).where(Recipe.book_id == book.id, Recipe.name == data.name)
    )
    if recipe is None:
        recipe = Recipe(book_id=book.id, name=data.name, order=data.book_order or 0)
        session.add(recipe)

    source_text = [line.text for line in data.ingredients]
    fingerprint = _source_fingerprint(data, source_text)
    previous_fingerprint = (
        recipe.enrichment_state.source_fingerprint if recipe.enrichment_state else None
    )

    recipe.extraction_run_id = run.id
    recipe.order = data.book_order or 0
    recipe.description = data.description
    recipe.instructions = data.instructions
    recipe.yields = data.yields
    recipe.image = data.image or None
    recipe.keywords = [get_or_create_keyword(session, name) for name in data.keywords]
    if fingerprint != previous_fingerprint:
        # SQLite checks the (recipe_id, position) uniqueness while it flushes. Delete
        # the old rows first, before inserting replacement lines at the same positions.
        if recipe.ingredients_verbatim:
            recipe.ingredients_verbatim.clear()
            session.flush()
        recipe.ingredients_verbatim = [
            IngredientLine(position=position, text=text)
            for position, text in enumerate(source_text)
        ]
        recipe.facets.clear()
        recipe.cuisines.clear()
        if recipe.enrichment_state is None:
            recipe.enrichment_state = RecipeEnrichmentState(recipe_id=recipe.id)
        state = recipe.enrichment_state
        assert state is not None
        state.status = RecipeEnrichmentStatus.PENDING
        state.source_fingerprint = fingerprint
        state.last_error = None
        state.started_at = None
        state.completed_at = None
    elif recipe.enrichment_state is None:
        recipe.enrichment_state = RecipeEnrichmentState(
            recipe_id=recipe.id,
            status=RecipeEnrichmentStatus.PENDING,
            source_fingerprint=fingerprint,
        )
    session.flush()
    return recipe


def _source_fingerprint(data: RecipeData, ingredient_text: list[str]) -> str:
    """Only source material is hashed: unchanged re-extraction keeps derived facts."""
    source = {
        "name": data.name,
        "description": data.description,
        "instructions": data.instructions,
        "ingredients": ingredient_text,
    }
    return sha256(
        json.dumps(source, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def save_recipes_from_graph_state(
    session: Session, book: Book, run: TaskRun, raw_recipes: list[dict]
) -> int:
    logger.info(f"Saving {len(raw_recipes)} recipes for {book.title}")

    saved: list[Recipe] = []
    for recipe_dict in raw_recipes:
        try:
            recipe_data = RecipeData(**recipe_dict)
        except Exception as e:
            logger.error(f"Invalid recipe data: {e}")
            continue
        saved.append(_upsert_recipe(session, book, run, recipe_data))

    generate_recipe_embeddings(session, saved)
    _generate_book_keywords(session, book)
    session.commit()

    logger.info(f"Saved {len(saved)} recipes for {book.title}")
    return len(saved)


def _finalise_result(run_id: str, result: dict | None) -> str:
    """Inspect the run after a graph invocation: persist recipes when done, or report
    the review pause. `result` is the graph's final state (None never reaches here on
    a completed run, but is tolerated)."""
    with SessionLocal() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        if run is None:
            return "Extraction run not found"

        if run.status == TaskStatus.REVIEW:
            logger.info(f"Extraction paused for review: run {run_id}")
            return f"Extraction paused for review. Check run {run_id}"

        if run.status == TaskStatus.DONE:
            book = session.get(Book, run.book_id)
            if book is None:
                return "Book not found"
            raw_recipes = (result or {}).get("raw_recipes", [])
            created = save_recipes_from_graph_state(session, book, run, raw_recipes)
            logger.info(f"Finished extraction for {book.title}. Processed {created} recipes.")
            return f"Extracted {created} recipes for {book.title}"

    return "Extraction completed with unknown status"


def extract_recipes_from_book(book_id: str, extraction_id: str | None = None) -> str:
    """Run extraction for a book to completion or to the human-review pause. Creates a
    new TaskRun unless an existing one is supplied (e.g. a retry)."""
    with SessionLocal() as session:
        book = session.get(Book, uuid.UUID(book_id))
        if book is None:
            logger.error(f"Book with id {book_id} not found")
            return "Book not found"

        run: TaskRun | None = None
        if extraction_id:
            run = session.get(TaskRun, uuid.UUID(extraction_id))
        if run is None:
            config = get_config(session)
            run = TaskRun(
                task_type=TaskType.EXTRACTION,
                book_id=book.id,
                provider_name=config.ai_provider,
            )
            session.add(run)

        run.status = TaskStatus.RUNNING
        run.started_at = datetime.now(UTC)
        session.commit()

        run_id = str(run.id)
        book_uuid = str(book.id)
        epub = epub_path(book)
        pdf = pdf_path(book)

    logger.info(f"Starting recipe extraction for book {book_uuid} (run {run_id})")

    initial_state = {
        "book_id": book_uuid,
        "report_id": run_id,
        "already_tried": [],
    }
    if epub is not None:
        initial_state["epub_path"] = str(epub)
    elif pdf is not None:
        initial_state["pdf_path"] = str(pdf)
    graph_config = {"configurable": {"thread_id": _thread_id(run_id)}}

    result = get_extraction_graph().invoke(initial_state, graph_config)
    return _finalise_result(run_id, result)


def resume_extraction(extraction_id: str, human_response: str) -> str:
    """Resume an extraction paused for human review, supplying the answer to the
    'does this cookbook have photos?' question and driving the graph to completion."""
    if human_response not in VALID_HUMAN_RESPONSES:
        raise ValueError(
            f"Invalid response '{human_response}'; expected one of {sorted(VALID_HUMAN_RESPONSES)}"
        )

    with SessionLocal() as session:
        run = session.get(TaskRun, uuid.UUID(extraction_id))
        if run is None:
            return "Extraction run not found"
        if run.status != TaskStatus.REVIEW:
            return "This extraction is not awaiting review."
        run_id = str(run.id)

    graph_config = {"configurable": {"thread_id": _thread_id(run_id)}}
    graph = get_extraction_graph()

    # The checkpoint carries the state the remaining nodes read (report_id, epub_path,
    # chapter files). If it's gone — DB replaced, run paused by an older build — then
    # update_state would fabricate a state holding only the answer, and the next node
    # dies on a bare KeyError, leaving the run wedged in REVIEW. Fail it honestly
    # instead; re-extracting the book from scratch is the way back.
    if "report_id" not in graph.get_state(graph_config).values:
        raise RuntimeError(
            f"Cannot resume run {run_id}: its saved graph state is gone. Re-run extraction."
        )

    graph.update_state(graph_config, {"human_response": human_response}, as_node="await_human")
    result = graph.invoke(None, graph_config)

    return _finalise_result(run_id, result)


@celery_app.task(name="extract_recipes_from_book")
def extract_recipes_from_book_task(book_id: str, extraction_id: str | None = None) -> str:
    try:
        return extract_recipes_from_book(book_id, extraction_id)
    except Exception as exc:
        # The trigger endpoint always supplies the run id, so a crash is recorded on
        # the row; re-raise so Celery also captures the traceback in the backend.
        if extraction_id:
            _mark_run_failed(extraction_id, exc)
        raise


@celery_app.task(name="resume_extraction")
def resume_extraction_task(extraction_id: str, human_response: str) -> str:
    try:
        return resume_extraction(extraction_id, human_response)
    except Exception as exc:
        # Mirrors the trigger task: without this a crashed resume leaves the run in
        # REVIEW, still offering the question that just failed to be answered.
        _mark_run_failed(extraction_id, exc)
        raise
