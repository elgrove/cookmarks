import logging
import sqlite3
import zipfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from core.models import Book, ExtractionReport
from core.services.ai import GeminiProvider, OpenRouterProvider, get_config
from core.services.epub import (
    MANY_RECIPES_PER_FILE_THRESHOLD,
    get_block_content,
    get_chapterlike_files_from_epub,
    get_sample_chapters_content,
    has_separate_image_chapters,
    split_chapters_into_blocks,
)
from core.services.extraction.state import ExtractionState
from core.services.extraction.utils import (
    build_image_path_lookup,
    deduplicate_recipes_by_title,
    resolve_image_path_in_epub,
)
from core.services.rate_limiter import RateLimitedExecutor

logger = logging.getLogger(__name__)


def analyse_epub(state: ExtractionState) -> dict:
    report = ExtractionReport.objects.get(id=state["report_id"])
    epub_path = Path(state["epub_path"])

    logger.info(f"Analysing EPUB: {epub_path}")

    chapter_files = get_chapterlike_files_from_epub(epub_path)
    report.total_chapters = len(chapter_files)

    images_in_separate = has_separate_image_chapters(chapter_files)
    report.images_in_separate_chapters = images_in_separate
    report.save()

    logger.info(f"Found {len(chapter_files)} chapters, images_in_separate={images_in_separate}")

    if images_in_separate:
        sample_content = get_sample_chapters_content(epub_path, chapter_files)
        config = get_config()
        provider = GeminiProvider() if config.ai_provider == "GEMINI" else OpenRouterProvider()

        images_can_be_matched, usage = provider.check_if_can_match_images(sample_content)

        if usage.get("cost_usd") is not None:
            report.cost_usd = round((report.cost_usd or 0) + usage["cost_usd"], 4)
        if usage.get("input_tokens") is not None:
            report.input_tokens = (report.input_tokens or 0) + usage["input_tokens"]
        if usage.get("output_tokens") is not None:
            report.output_tokens = (report.output_tokens or 0) + usage["output_tokens"]

        report.images_can_be_matched = images_can_be_matched
        report.save()

        extraction_type = "block" if images_can_be_matched else "file"
        logger.info(
            f"Images can be matched: {images_can_be_matched}, using extraction type: {extraction_type}"
        )
    else:
        extraction_type = "file"
        logger.info("Images in same file as recipes, using file extraction")

    report.extraction_method = extraction_type
    report.save()

    return {
        "chapter_files": chapter_files,
        "extraction_type": extraction_type,
        "images_in_separate_chapters": images_in_separate,
    }


def extract_file(state: ExtractionState) -> dict:
    report = ExtractionReport.objects.get(id=state["report_id"])
    epub_path = Path(state["epub_path"])
    chapter_files = state["chapter_files"]

    config = get_config()
    provider = GeminiProvider() if config.ai_provider == "GEMINI" else OpenRouterProvider()
    rate_limiter = RateLimitedExecutor(
        max_workers=settings.EXTRACTION_THREADS,
        rate_per_minute=config.extraction_rate_limit_per_minute,
    )

    is_many_per_file = len(chapter_files) <= MANY_RECIPES_PER_FILE_THRESHOLD
    from core.services.ai import ExtractionMethod

    extraction_method = (
        ExtractionMethod.MANY_RECIPES_PER_FILE
        if is_many_per_file
        else ExtractionMethod.ONE_RECIPE_PER_FILE
    )

    if report.model_name:
        model = report.model_name
        logger.info(f"Using user-specified model override: {model}")
    else:
        model = provider._get_model_for_extraction_method(extraction_method)
        report.model_name = model
        report.save()

    logger.info(
        f"Extracting recipes using file method: {extraction_method.value} ({len(chapter_files)} chapters)"
    )

    def process_chapter(chapter_index: int, file_path: str) -> tuple[int, str, list, dict]:
        try:
            with zipfile.ZipFile(epub_path, "r") as epub:
                html_content = epub.read(file_path).decode("utf-8")

            with rate_limiter:
                recipes, usage = provider.extract_recipes(html_content, model=model)

            logger.info(f"Found {len(recipes)} recipes in {file_path}")
            return (chapter_index, file_path, recipes, usage)
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return (
                chapter_index,
                file_path,
                [],
                {"cost_usd": None, "input_tokens": None, "output_tokens": None},
            )

    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_recipes = []
    with ThreadPoolExecutor(max_workers=settings.EXTRACTION_THREADS) as executor:
        futures = {
            executor.submit(process_chapter, i, file_path): file_path
            for i, file_path in enumerate(chapter_files)
        }

        for future in as_completed(futures):
            try:
                chapter_index, processed_path, recipes, usage = future.result()
                report.chapters_processed.append(processed_path)

                if usage.get("cost_usd") is not None:
                    report.cost_usd = round((report.cost_usd or 0) + usage["cost_usd"], 4)
                if usage.get("input_tokens") is not None:
                    report.input_tokens = (report.input_tokens or 0) + usage["input_tokens"]
                if usage.get("output_tokens") is not None:
                    report.output_tokens = (report.output_tokens or 0) + usage["output_tokens"]

                for recipe in recipes:
                    all_recipes.append((chapter_index, recipe))
            except Exception as e:
                logger.error(f"Error processing future: {e}")

    all_recipes.sort(key=lambda x: x[0])
    raw_recipes = [recipe.model_dump() for _, recipe in all_recipes]

    report.save()

    return {"raw_recipes": raw_recipes}


def extract_block(state: ExtractionState) -> dict:
    report = ExtractionReport.objects.get(id=state["report_id"])
    epub_path = Path(state["epub_path"])
    chapter_files = state["chapter_files"]

    blocks = split_chapters_into_blocks(chapter_files)
    logger.info(f"Split {len(chapter_files)} chapters into {len(blocks)} blocks")

    config = get_config()
    provider = GeminiProvider() if config.ai_provider == "GEMINI" else OpenRouterProvider()

    if report.model_name:
        model = report.model_name
        logger.info(f"Using user-specified model override: {model}")
    else:
        from core.services.ai import ExtractionMethod

        model = provider._get_model_for_extraction_method(ExtractionMethod.BLOCKS_OF_FILES)
        report.model_name = model
        report.save()

    logger.info(f"Extracting recipes using block method with model {model}")

    rate_limiter = RateLimitedExecutor(
        max_workers=settings.EXTRACTION_THREADS,
        rate_per_minute=config.extraction_rate_limit_per_minute,
    )

    def process_block(block_info: tuple[int, list[str]]) -> tuple[int, list[str], list, dict]:
        block_index, block = block_info
        logger.info(f"Processing block {block_index + 1}/{len(blocks)} ({len(block)} chapters)")
        block_content = get_block_content(epub_path, block)

        if not block_content:
            logger.warning(f"No content in block {block_index + 1}")
            return (
                block_index,
                block,
                [],
                {"cost_usd": None, "input_tokens": None, "output_tokens": None},
            )

        with rate_limiter:
            recipes, usage = provider.extract_recipes(block_content, model=model)

        logger.info(f"Found {len(recipes)} recipes in block {block_index + 1}")
        return (block_index, block, recipes, usage)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_recipes = []
    with ThreadPoolExecutor(max_workers=settings.EXTRACTION_THREADS) as executor:
        futures = {executor.submit(process_block, (i, block)): i for i, block in enumerate(blocks)}

        for future in as_completed(futures):
            try:
                block_index, block_chapters, recipes, usage = future.result()
                report.chapters_processed.extend(block_chapters)

                if usage.get("cost_usd") is not None:
                    report.cost_usd = round((report.cost_usd or 0) + usage["cost_usd"], 4)
                if usage.get("input_tokens") is not None:
                    report.input_tokens = (report.input_tokens or 0) + usage["input_tokens"]
                if usage.get("output_tokens") is not None:
                    report.output_tokens = (report.output_tokens or 0) + usage["output_tokens"]

                for recipe in recipes:
                    all_recipes.append((block_index, recipe))
            except Exception as e:
                logger.error(f"Error processing block: {e}")

    all_recipes.sort(key=lambda x: x[0])
    recipe_objects = [recipe for _, recipe in all_recipes]
    deduplicated = deduplicate_recipes_by_title(recipe_objects)
    raw_recipes = [recipe.model_dump() for recipe in deduplicated]

    report.save()

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

    report = ExtractionReport.objects.get(id=state["report_id"])
    report.status = "review"
    report.save()

    logger.info("Awaiting human decision on image availability")

    response = interrupt(
        {
            "question": "Zero images found. Does this cookbook have photos?",
            "book_id": state["book_id"],
            "report_id": state["report_id"],
        }
    )

    logger.info(f"Received human response: {response}")

    return {"human_response": response}


def resolve_images(state: ExtractionState) -> dict:
    epub_path = Path(state["epub_path"])
    book = Book.objects.get(id=state["book_id"])
    raw_recipes = state.get("raw_recipes", [])

    logger.info("Resolving image paths in EPUB")

    image_path_lookup = build_image_path_lookup(epub_path)

    images_attempted = 0
    images_resolved = 0

    for order, recipe_dict in enumerate(raw_recipes, start=1):
        recipe_dict["bookOrder"] = order
        recipe_dict["author"] = book.author
        recipe_dict["bookTitle"] = book.title

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
    report = ExtractionReport.objects.get(id=state["report_id"])
    raw_recipes = state.get("raw_recipes", [])

    report.recipes_found = len(raw_recipes)
    report.completed_at = timezone.now()
    report.status = "done"
    report.save()

    logger.info(f"Extraction complete: {len(raw_recipes)} recipes found")

    return {}


def route_post_analyse(state: ExtractionState) -> str:
    extraction_type = state.get("extraction_type")
    if extraction_type == "block":
        return "extract_block"
    else:
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
    else:
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


conn = sqlite3.connect(settings.DATABASES["default"]["NAME"], check_same_thread=False)
memory = SqliteSaver(conn)

workflow = StateGraph(ExtractionState)

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

app = workflow.compile(checkpointer=memory)
