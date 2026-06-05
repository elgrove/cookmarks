import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.covers import epub_path
from app.db import SessionLocal
from app.models.book import Book
from app.models.enums import ExtractionStatus
from app.models.extraction import ExtractionRun
from app.models.recipe import Keyword, Recipe
from app.schemas.extraction import RecipeData
from app.services.ai import get_config
from app.services.embeddings import embed_recipes
from app.services.extraction.graph import get_extraction_graph
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_VALID_HUMAN_RESPONSES = ("has_images", "no_images")


def enqueue_extract_recipes(book_id: str, run_id: str) -> None:
    """Dispatch the extraction task to the Celery worker. The single seam the trigger
    endpoint goes through (and tests stub) so a queued run never blocks the request
    thread and the dispatch stays out of the API and contract layers."""
    extract_recipes_from_book_task.delay(book_id, run_id)


def _mark_run_failed(extraction_id: str, exc: Exception) -> None:
    """Record a crashed run on its row: status FAILED, the error appended, completed
    stamped — so a worker exception leaves an honest record instead of a run wedged
    in RUNNING forever. Best-effort: a failure here must not mask the original."""
    try:
        with SessionLocal() as session:
            run = session.get(ExtractionRun, uuid.UUID(extraction_id))
            if run is None:
                return
            run.status = ExtractionStatus.FAILED
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


def _get_or_create_keyword(session: Session, name: str) -> Keyword:
    keyword = session.scalar(select(Keyword).where(Keyword.name == name))
    if keyword is None:
        keyword = Keyword(name=name)
        session.add(keyword)
        session.flush()
    return keyword


def _upsert_recipe(session: Session, book: Book, run: ExtractionRun, data: RecipeData) -> Recipe:
    """Reconcile by normalised name within the book: update the existing recipe in
    place if one matches, else create it. Identity is stable across re-extraction so
    favourites and list membership survive a re-run."""
    recipe = session.scalar(
        select(Recipe).where(Recipe.book_id == book.id, Recipe.name == data.name)
    )
    if recipe is None:
        recipe = Recipe(book_id=book.id, name=data.name, order=data.book_order or 0)
        session.add(recipe)

    recipe.extraction_run_id = run.id
    recipe.order = data.book_order or 0
    recipe.description = data.description
    recipe.ingredients = data.ingredients
    recipe.instructions = data.instructions
    recipe.yields = data.yields
    recipe.image = data.image
    recipe.keywords = [_get_or_create_keyword(session, name) for name in data.keywords]
    session.flush()
    return recipe


def save_recipes_from_graph_state(
    session: Session, book: Book, run: ExtractionRun, raw_recipes: list[dict]
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
    session.commit()

    logger.info(f"Saved {len(saved)} recipes for {book.title}")
    return len(saved)


def _finalise_result(run_id: str, result: dict | None) -> str:
    """Inspect the run after a graph invocation: persist recipes when done, or report
    the review pause. `result` is the graph's final state (None never reaches here on
    a completed run, but is tolerated)."""
    with SessionLocal() as session:
        run = session.get(ExtractionRun, uuid.UUID(run_id))
        if run is None:
            return "Extraction run not found"

        if run.status == ExtractionStatus.REVIEW:
            logger.info(f"Extraction paused for review: run {run_id}")
            return f"Extraction paused for review. Check run {run_id}"

        if run.status == ExtractionStatus.DONE:
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
    new ExtractionRun unless an existing one is supplied (e.g. a retry)."""
    with SessionLocal() as session:
        book = session.get(Book, uuid.UUID(book_id))
        if book is None:
            logger.error(f"Book with id {book_id} not found")
            return "Book not found"

        run: ExtractionRun | None = None
        if extraction_id:
            run = session.get(ExtractionRun, uuid.UUID(extraction_id))
        if run is None:
            config = get_config(session)
            run = ExtractionRun(book_id=book.id, provider_name=config.ai_provider)
            session.add(run)

        run.status = ExtractionStatus.RUNNING
        run.started_at = datetime.now(UTC)
        session.commit()

        run_id = str(run.id)
        book_uuid = str(book.id)
        epub = str(epub_path(book))

    logger.info(f"Starting recipe extraction for book {book_uuid} (run {run_id})")

    initial_state = {
        "book_id": book_uuid,
        "epub_path": epub,
        "report_id": run_id,
        "already_tried": [],
    }
    graph_config = {"configurable": {"thread_id": _thread_id(run_id)}}

    result = get_extraction_graph().invoke(initial_state, graph_config)
    return _finalise_result(run_id, result)


def resume_extraction(extraction_id: str, human_response: str) -> str:
    """Resume an extraction paused for human review, supplying the answer to the
    'does this cookbook have photos?' question and driving the graph to completion."""
    if human_response not in _VALID_HUMAN_RESPONSES:
        raise ValueError(
            f"Invalid response '{human_response}'; expected one of {_VALID_HUMAN_RESPONSES}"
        )

    with SessionLocal() as session:
        run = session.get(ExtractionRun, uuid.UUID(extraction_id))
        if run is None:
            return "Extraction run not found"
        if run.status != ExtractionStatus.REVIEW:
            return "This extraction is not awaiting review."
        run_id = str(run.id)

    graph_config = {"configurable": {"thread_id": _thread_id(run_id)}}
    graph = get_extraction_graph()
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
    return resume_extraction(extraction_id, human_response)
