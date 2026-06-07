import logging
import sqlite3
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.book import Book
from app.models.enums import ExtractionMethod, ExtractionStatus
from app.models.extraction import ExtractionRun
from app.schemas.extraction import RecipeData
from app.services.ai import AIProvider, ModelRole, Usage, get_ai_provider, get_config
from app.services.epub import (
    MANY_RECIPES_PER_FILE_THRESHOLD,
    get_block_content,
    get_chapterlike_files_from_epub,
    get_sample_chapters_content,
    has_separate_image_chapters,
    split_chapters_into_blocks,
)
from app.services.extraction.review import REVIEW_QUESTION
from app.services.extraction.state import ExtractionState
from app.services.extraction.utils import (
    build_image_path_lookup,
    deduplicate_recipes_by_title,
    resolve_image_path_in_epub,
)
from app.services.rate_limiter import RateLimitedExecutor

logger = logging.getLogger(__name__)

_EMPTY_USAGE = Usage()


def _load_run(session: Session, report_id: str) -> ExtractionRun:
    run = session.get(ExtractionRun, uuid.UUID(report_id))
    if run is None:
        raise ValueError(f"ExtractionRun {report_id} not found")
    return run


def _require_provider(session: Session) -> AIProvider:
    provider = get_ai_provider(session)
    if provider is None:
        raise RuntimeError("No usable AI provider is configured")
    return provider


def _apply_usage(run: ExtractionRun, usage: Usage) -> None:
    """Accumulate one call's cost/tokens onto the run, leaving unreported (None)
    components untouched. Cost is rounded to 4dp as it lands, matching v1."""
    if usage.cost_usd is not None:
        run.cost_usd = round((run.cost_usd or Decimal(0)) + usage.cost_usd, 4)
    if usage.input_tokens is not None:
        run.input_tokens = (run.input_tokens or 0) + usage.input_tokens
    if usage.output_tokens is not None:
        run.output_tokens = (run.output_tokens or 0) + usage.output_tokens


def analyse_epub(state: ExtractionState) -> dict:
    with SessionLocal() as session:
        run = _load_run(session, state["report_id"])
        epub_path = Path(state["epub_path"])

        logger.info(f"Analysing EPUB: {epub_path}")

        chapter_files = get_chapterlike_files_from_epub(epub_path)
        run.total_chapters = len(chapter_files)

        images_in_separate = has_separate_image_chapters(chapter_files)
        run.images_in_separate_chapters = images_in_separate

        logger.info(f"Found {len(chapter_files)} chapters, images_in_separate={images_in_separate}")

        if images_in_separate:
            if run.images_can_be_matched is not None:
                # A pre-set decision (e.g. from the eval) overrides the model check,
                # which can misjudge a book and force a wasteful fallback extraction.
                images_can_be_matched = run.images_can_be_matched
                logger.info(f"Using pre-set image-match decision: {images_can_be_matched}")
            else:
                sample_content = get_sample_chapters_content(epub_path, chapter_files)
                provider = _require_provider(session)
                images_can_be_matched, usage = provider.check_if_can_match_images(
                    sample_content, model=run.model_name
                )
                _apply_usage(run, usage)
                run.images_can_be_matched = images_can_be_matched

            extraction_type = "block" if images_can_be_matched else "file"
            logger.info(
                f"Images can be matched: {images_can_be_matched}, "
                f"using extraction type: {extraction_type}"
            )
        else:
            extraction_type = "file"
            logger.info("Images in same file as recipes, using file extraction")

        run.extraction_method = ExtractionMethod(extraction_type)
        session.commit()

    return {
        "chapter_files": chapter_files,
        "extraction_type": extraction_type,
        "images_in_separate_chapters": images_in_separate,
    }


def extract_file(state: ExtractionState) -> dict:
    with SessionLocal() as session:
        run = _load_run(session, state["report_id"])
        run.extraction_method = ExtractionMethod.FILE
        epub_path = Path(state["epub_path"])
        chapter_files = state["chapter_files"]

        config = get_config(session)
        provider = _require_provider(session)
        rate_limiter = RateLimitedExecutor(
            max_workers=settings.extraction_threads,
            rate_per_minute=config.extraction_rate_limit_per_minute,
        )

        is_many_per_file = len(chapter_files) <= MANY_RECIPES_PER_FILE_THRESHOLD
        role = (
            ModelRole.MANY_RECIPES_PER_FILE if is_many_per_file else ModelRole.ONE_RECIPE_PER_FILE
        )

        if run.model_name:
            model = run.model_name
            logger.info(f"Using user-specified model override: {model}")
        else:
            model = provider.model_for(role)
            run.model_name = model
            session.commit()

        logger.info(
            f"Extracting recipes using file method: {role.value} ({len(chapter_files)} chapters)"
        )

        def process_chapter(
            chapter_index: int, file_path: str
        ) -> tuple[int, str, list[RecipeData], Usage]:
            try:
                with zipfile.ZipFile(epub_path, "r") as epub:
                    html_content = epub.read(file_path).decode("utf-8")

                with rate_limiter:
                    recipes, usage = provider.extract_recipes(html_content, model=model)

                logger.info(f"Found {len(recipes)} recipes in {file_path}")
                return (chapter_index, file_path, recipes, usage)
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                return (chapter_index, file_path, [], _EMPTY_USAGE)

        all_recipes: list[tuple[int, RecipeData]] = []
        processed = list(run.chapters_processed)
        with ThreadPoolExecutor(max_workers=settings.extraction_threads) as executor:
            futures = {
                executor.submit(process_chapter, i, file_path): file_path
                for i, file_path in enumerate(chapter_files)
            }

            for future in as_completed(futures):
                try:
                    chapter_index, processed_path, recipes, usage = future.result()
                    processed.append(processed_path)
                    _apply_usage(run, usage)
                    for recipe in recipes:
                        all_recipes.append((chapter_index, recipe))
                except Exception as e:
                    logger.error(f"Error processing future: {e}")

        all_recipes.sort(key=lambda x: x[0])
        raw_recipes = [recipe.model_dump(by_alias=True) for _, recipe in all_recipes]

        run.chapters_processed = processed
        session.commit()

    return {"raw_recipes": raw_recipes}


def extract_block(state: ExtractionState) -> dict:
    with SessionLocal() as session:
        run = _load_run(session, state["report_id"])
        run.extraction_method = ExtractionMethod.BLOCK
        epub_path = Path(state["epub_path"])
        chapter_files = state["chapter_files"]

        blocks = split_chapters_into_blocks(chapter_files)
        logger.info(f"Split {len(chapter_files)} chapters into {len(blocks)} blocks")

        config = get_config(session)
        provider = _require_provider(session)

        if run.model_name:
            model = run.model_name
            logger.info(f"Using user-specified model override: {model}")
        else:
            model = provider.model_for(ModelRole.BLOCKS_OF_FILES)
            run.model_name = model
            session.commit()

        logger.info(f"Extracting recipes using block method with model {model}")

        rate_limiter = RateLimitedExecutor(
            max_workers=settings.extraction_threads,
            rate_per_minute=config.extraction_rate_limit_per_minute,
        )

        def process_block(
            block_info: tuple[int, list[str]],
        ) -> tuple[int, list[str], list[RecipeData], Usage]:
            block_index, block = block_info
            logger.info(f"Processing block {block_index + 1}/{len(blocks)} ({len(block)} chapters)")
            block_content = get_block_content(epub_path, block)

            if not block_content:
                logger.warning(f"No content in block {block_index + 1}")
                return (block_index, block, [], _EMPTY_USAGE)

            with rate_limiter:
                recipes, usage = provider.extract_recipes(block_content, model=model)

            logger.info(f"Found {len(recipes)} recipes in block {block_index + 1}")
            return (block_index, block, recipes, usage)

        all_recipes: list[tuple[int, RecipeData]] = []
        processed = list(run.chapters_processed)
        with ThreadPoolExecutor(max_workers=settings.extraction_threads) as executor:
            futures = {
                executor.submit(process_block, (i, block)): i for i, block in enumerate(blocks)
            }

            for future in as_completed(futures):
                try:
                    block_index, block_chapters, recipes, usage = future.result()
                    processed.extend(block_chapters)
                    _apply_usage(run, usage)
                    for recipe in recipes:
                        all_recipes.append((block_index, recipe))
                except Exception as e:
                    logger.error(f"Error processing block: {e}")

        all_recipes.sort(key=lambda x: x[0])
        recipe_objects = [recipe for _, recipe in all_recipes]
        deduplicated = deduplicate_recipes_by_title(recipe_objects)
        raw_recipes = [recipe.model_dump(by_alias=True) for recipe in deduplicated]

        run.chapters_processed = processed
        session.commit()

    already_tried = state.get("already_tried", [])
    if "block" not in already_tried:
        already_tried = [*already_tried, "block"]

    return {"raw_recipes": raw_recipes, "already_tried": already_tried}


def validate(state: ExtractionState) -> dict:
    raw_recipes = state.get("raw_recipes", [])
    logger.info(f"Validation: Found {len(raw_recipes)} recipes")
    return {}


def await_human_decision(state: ExtractionState) -> dict:
    if state.get("human_response"):
        logger.info(f"Resuming with existing human response: {state['human_response']}")
        return {}

    with SessionLocal() as session:
        run = _load_run(session, state["report_id"])
        run.status = ExtractionStatus.REVIEW
        session.commit()

    logger.info("Awaiting human decision on image availability")

    response = interrupt(
        {
            "question": REVIEW_QUESTION,
            "book_id": state["book_id"],
            "report_id": state["report_id"],
        }
    )

    logger.info(f"Received human response: {response}")

    return {"human_response": response}


def resolve_images(state: ExtractionState) -> dict:
    epub_path = Path(state["epub_path"])
    raw_recipes = state.get("raw_recipes", [])

    with SessionLocal() as session:
        book = session.get(Book, uuid.UUID(state["book_id"]))
        if book is None:
            raise ValueError(f"Book {state['book_id']} not found")
        author = book.author
        book_title = book.title

    logger.info("Resolving image paths in EPUB")

    image_path_lookup = build_image_path_lookup(epub_path)

    images_attempted = 0
    images_resolved = 0

    for order, recipe_dict in enumerate(raw_recipes, start=1):
        recipe_dict["bookOrder"] = order
        recipe_dict["author"] = author
        recipe_dict["bookTitle"] = book_title

        original_image = recipe_dict.get("image")
        if original_image:
            images_attempted += 1

        recipe_dict["image"] = resolve_image_path_in_epub(original_image, image_path_lookup)

        if recipe_dict["image"]:
            images_resolved += 1

    logger.info(
        f"Image resolution: {images_resolved}/{images_attempted} images successfully resolved"
    )

    return {"raw_recipes": raw_recipes}


def finalise(state: ExtractionState) -> dict:
    raw_recipes = state.get("raw_recipes", [])

    with SessionLocal() as session:
        run = _load_run(session, state["report_id"])
        run.recipes_found = len(raw_recipes)
        run.completed_at = datetime.now(UTC)
        run.status = ExtractionStatus.DONE
        session.commit()

    logger.info(f"Extraction complete: {len(raw_recipes)} recipes found")

    return {}


def route_post_analyse(state: ExtractionState) -> str:
    extraction_type = state.get("extraction_type")
    if extraction_type == "block":
        return "extract_block"
    return "extract_file"


def route_post_validate(state: ExtractionState) -> str:
    raw_recipes = state.get("raw_recipes", [])
    has_image_paths = any(r.get("image") for r in raw_recipes)

    if has_image_paths:
        return "resolve_images"

    already_tried = state.get("already_tried", [])
    if "block" not in already_tried:
        return "await_human"

    return "resolve_images"


def route_post_human(state: ExtractionState) -> str:
    response = state.get("human_response")

    if response == "has_images":
        return "extract_block"
    return "resolve_images"


def route_post_resolve(state: ExtractionState) -> str:
    raw_recipes = state.get("raw_recipes", [])
    has_resolved_images = any(r.get("image") for r in raw_recipes)

    if has_resolved_images:
        return "finalise"

    if state.get("human_response"):
        return "finalise"

    already_tried = state.get("already_tried", [])
    if "block" not in already_tried:
        return "await_human"

    return "finalise"


@lru_cache(maxsize=1)
def get_extraction_graph():
    """Build and compile the extraction workflow, lazily, with a SQLite checkpointer
    pointed at the application database. Cached so the connection and compiled graph
    are reused; importing this module does not touch the database."""
    conn = sqlite3.connect(str(settings.db_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    workflow = StateGraph(ExtractionState)  # ty: ignore[invalid-argument-type]

    workflow.set_entry_point("analyse_epub")

    workflow.add_node("analyse_epub", analyse_epub)
    workflow.add_conditional_edges("analyse_epub", route_post_analyse)

    workflow.add_node("extract_file", extract_file)
    workflow.add_edge("extract_file", "validate")

    workflow.add_node("extract_block", extract_block)
    workflow.add_edge("extract_block", "validate")

    workflow.add_node("validate", validate)
    workflow.add_conditional_edges("validate", route_post_validate)

    workflow.add_node("await_human", await_human_decision)
    workflow.add_conditional_edges("await_human", route_post_human)

    workflow.add_node("resolve_images", resolve_images)
    workflow.add_conditional_edges("resolve_images", route_post_resolve)

    workflow.add_node("finalise", finalise)
    workflow.add_edge("finalise", END)

    return workflow.compile(checkpointer=checkpointer)
