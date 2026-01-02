import logging
import warnings
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from core.models import Book, ExtractionReport, RecipeData
from core.services.ai import ExtractionMethod, GeminiProvider, OpenRouterProvider, get_config
from core.services.epub import (
    MANY_RECIPES_PER_FILE_THRESHOLD,
    get_block_content,
    get_chapterlike_files_from_epub,
    get_sample_chapters_content,
    has_separate_image_chapters,
    split_chapters_into_blocks,
)
from core.services.rate_limiter import RateLimitedExecutor

warnings.warn(
    "core.services.extract is deprecated and will be removed in a future version. "
    "Use core.services.extraction.graph instead.",
    DeprecationWarning,
    stacklevel=2,
)

logger = logging.getLogger(__name__)


def deduplicate_recipes_by_title(recipes: list[RecipeData]) -> list[RecipeData]:
    seen_titles = set()
    unique_recipes = []
    for recipe in recipes:
        title_key = recipe.name.lower().strip()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_recipes.append(recipe)
        else:
            logger.debug(f"Deduplicating recipe: {recipe.name}")
    return unique_recipes


def _build_image_path_lookup(epub_path: Path) -> dict[str, list[str]]:
    cache = {}
    try:
        with zipfile.ZipFile(epub_path, "r") as epub:
            for file_path in epub.namelist():
                if file_path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                    filename = Path(file_path).name.lower()
                    if filename not in cache:
                        cache[filename] = []
                    cache[filename].append(file_path)
    except Exception as e:
        logger.error(f"Error building image cache for {epub_path}: {e}")
    return cache


def _resolve_image_path_in_epub(
    relative_image_path: str | None, image_cache: dict[str, list[str]]
) -> str | None:
    if not relative_image_path:
        return None

    filename = Path(relative_image_path).name.lower()
    matches = image_cache.get(filename, [])

    if not matches:
        return None

    if len(matches) == 1:
        return matches[0]

    relative_lower = relative_image_path.lower()
    for match in matches:
        if match.lower().endswith(relative_lower):
            return match

    logger.warning(f"Multiple matches for {filename}, using first: {matches[0]}")
    return matches[0]


def _extract_in_files(
    epub_path: Path, chapter_files: list[str], report: ExtractionReport
) -> list[RecipeData]:
    config = get_config()
    provider = GeminiProvider() if config.ai_provider == "GEMINI" else OpenRouterProvider()
    rate_limiter = RateLimitedExecutor(
        max_workers=settings.EXTRACTION_THREADS,
        rate_per_minute=config.extraction_rate_limit_per_minute,
    )

    is_many_per_file = len(chapter_files) <= MANY_RECIPES_PER_FILE_THRESHOLD
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

    logger.info(
        f"Using extraction method: {extraction_method.value} ({len(chapter_files)} chapters)"
    )
    logger.info(f"Extracting recipes using provider={provider.NAME}, model={model}")

    def process_chapter(
        chapter_index: int, file_path: str
    ) -> tuple[int, str, list[RecipeData], dict]:
        try:
            with zipfile.ZipFile(epub_path, "r") as epub:
                html_content = epub.read(file_path).decode("utf-8")
            logger.info(f"Processing chapter {file_path} (size: {len(html_content)} chars)")

            with rate_limiter:
                recipes, usage = provider.extract_recipes(html_content, model=model)

            logger.info(f"Found {len(recipes)} recipes in {file_path}")
            return (chapter_index, file_path, recipes, usage)
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            report.errors.append(f"Error reading {file_path}: {e}")
            return (
                chapter_index,
                file_path,
                [],
                {"cost_usd": None, "input_tokens": None, "output_tokens": None},
            )

    all_recipes: list[tuple[int, RecipeData]] = []
    with ThreadPoolExecutor(max_workers=settings.EXTRACTION_THREADS) as executor:
        futures = {
            executor.submit(process_chapter, i, file_path): file_path
            for i, file_path in enumerate(chapter_files)
        }

        for future in as_completed(futures):
            file_path = futures[future]
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
                logger.error(f"Error processing chapter {file_path}: {e}")
                report.errors.append(f"Error processing chapter {file_path}: {e}")

    all_recipes.sort(key=lambda x: x[0])
    return [recipe for _, recipe in all_recipes]


def _extract_in_blocks_of_files(
    epub_path: Path, chapter_files: list[str], report: ExtractionReport
) -> list[RecipeData]:
    blocks = split_chapters_into_blocks(chapter_files)
    logger.info(f"Split {len(chapter_files)} chapters into {len(blocks)} blocks")

    config = get_config()
    provider = GeminiProvider() if config.ai_provider == "GEMINI" else OpenRouterProvider()

    # Use report's model_name if already set (user override), otherwise auto-select
    if report.model_name:
        model = report.model_name
        logger.info(f"Using user-specified model override: {model}")
    else:
        model = provider._get_model_for_extraction_method(ExtractionMethod.BLOCKS_OF_FILES)
        report.model_name = model

    logger.info(
        f"Extracting recipes using provider={provider.NAME}, model={model}, method={ExtractionMethod.BLOCKS_OF_FILES.value}"
    )
    rate_limiter = RateLimitedExecutor(
        max_workers=settings.EXTRACTION_THREADS,
        rate_per_minute=config.extraction_rate_limit_per_minute,
    )

    def process_block(
        block_info: tuple[int, list[str]],
    ) -> tuple[int, list[str], list[RecipeData], dict]:
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

    all_recipes: list[tuple[int, RecipeData]] = []
    with ThreadPoolExecutor(max_workers=settings.EXTRACTION_THREADS) as executor:
        futures = {executor.submit(process_block, (i, block)): i for i, block in enumerate(blocks)}

        for future in as_completed(futures):
            block_idx = futures[future]
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
                logger.error(f"Error processing block {block_idx + 1}: {e}")
                report.errors.append(f"Error processing block {block_idx + 1}: {e}")

    all_recipes.sort(key=lambda x: x[0])
    return deduplicate_recipes_by_title([recipe for _, recipe in all_recipes])


def _extract(
    epub_path: Path, chapter_files: list[str], report: ExtractionReport
) -> list[RecipeData]:
    if report.extraction_method == "block":
        logger.info("Using block extraction method")
        return _extract_in_blocks_of_files(epub_path, chapter_files, report)
    else:
        logger.info("Using file extraction method")
        return _extract_in_files(epub_path, chapter_files, report)


def create_extraction_file_handler(book: Book) -> logging.FileHandler:
    handler = logging.FileHandler(book.get_log_path(), mode="w")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    handler.setLevel(logging.DEBUG)
    return handler


def extract_recipe_data_from_book(
    book: Book, report: ExtractionReport | None = None
) -> tuple[list[RecipeData], ExtractionReport]:
    epub_path = book.get_epub_path()
    config = get_config()

    if report is None:
        report = ExtractionReport(
            book=book,
            provider_name=config.ai_provider,
            total_chapters=0,
            chapters_processed=[],
            recipes_found=0,
            errors=[],
        )
        report.save()

    report.started_at = timezone.now()
    report.save()

    file_handler = create_extraction_file_handler(book)
    logger.addHandler(file_handler)

    try:
        if not epub_path:
            logger.warning(f"No EPUB file found for {book.title}")
            report.errors.append(f"No EPUB file found for {book.title}")
            report.save()
            return [], report

        logger.info(f"Processing EPUB: {epub_path}")

        chapter_files = get_chapterlike_files_from_epub(epub_path)
        report.total_chapters = len(chapter_files)

        if report.extraction_method is None:
            report.images_in_separate_chapters = has_separate_image_chapters(chapter_files)

            if report.images_in_separate_chapters:
                logger.info(
                    "Book may have images in separate chapters, checking if images can be reliably matched to recipes"
                )
                sample_content = get_sample_chapters_content(epub_path, chapter_files)

                provider = (
                    GeminiProvider() if config.ai_provider == "GEMINI" else OpenRouterProvider()
                )
                report.images_can_be_matched, usage = provider.check_if_can_match_images(
                    sample_content
                )

                # Add image match check costs to the extraction report
                if usage.get("cost_usd") is not None:
                    report.cost_usd = round((report.cost_usd or 0) + usage["cost_usd"], 4)
                if usage.get("input_tokens") is not None:
                    report.input_tokens = (report.input_tokens or 0) + usage["input_tokens"]
                if usage.get("output_tokens") is not None:
                    report.output_tokens = (report.output_tokens or 0) + usage["output_tokens"]

                if report.images_can_be_matched:
                    logger.info("Images can be matched to recipes, using block extraction")
                    report.extraction_method = "block"
                else:
                    logger.info(
                        "Images cannot be matched to recipes, falling back to file extraction"
                    )
                    report.extraction_method = "file"
            else:
                logger.info("Images seem to be in same file as recipe, using file extraction")
                report.extraction_method = "file"
            report.save()

        image_path_lookup = _build_image_path_lookup(epub_path)
        all_recipes = _extract(epub_path, chapter_files, report)

        for order, recipe in enumerate(all_recipes, start=1):
            recipe.book_order = order
            recipe.author = book.author
            recipe.book_title = book.title
            recipe.image = _resolve_image_path_in_epub(recipe.image, image_path_lookup)

        report.recipes_found = len(all_recipes)
        report.completed_at = timezone.now()
        report.save()
        logger.info(f"Total recipes found in {book.title}: {len(all_recipes)}")

        return all_recipes, report

    finally:
        file_handler.flush()
        file_handler.close()
        logger.removeHandler(file_handler)
