import json
import logging
from pathlib import Path

import inflect
import titlecase
from django.conf import settings
from django.forms.models import model_to_dict
from django.utils import timezone

from core.models import Book, ExtractionReport, Keyword, Recipe, RecipeData
from core.services.ai import (
    GeminiProvider,
    OpenRouterProvider,
    get_ai_provider,
    get_config,
)
from core.services.calibre import load_books_from_calibre
from core.services.embeddings import generate_recipe_embeddings_batch
from core.services.extraction import app as extraction_app

logger = logging.getLogger(__name__)


def pre_deduplicate_keywords(keywords: list[str]) -> tuple[list[str], dict[str, str]]:
    p = inflect.engine()
    merge_map = {}
    seen = {}

    for kw in keywords:
        normalized = " ".join(kw.strip().split())
        titlecased = titlecase.titlecase(normalized)
        comparison_key = titlecased.lower()

        if normalized != titlecased:
            merge_map[normalized] = titlecased

        if comparison_key not in seen:
            seen[comparison_key] = titlecased

    for comparison_key, canonical in list(seen.items()):
        singular = p.singular_noun(comparison_key)
        if singular and singular in seen:
            merge_map[canonical] = seen[singular]
            del seen[comparison_key]

    return list(seen.values()), merge_map


def deduplicate_keywords_task():
    logger.info("Starting keyword deduplication task.")

    all_keywords = list(Keyword.objects.values_list("name", flat=True))
    logger.info(f"Found {len(all_keywords)} keywords to process.")

    deduplicated_keywords, pre_merge_map = pre_deduplicate_keywords(all_keywords)
    logger.info(
        f"Pre-deduplication reduced to {len(deduplicated_keywords)} keywords, {len(pre_merge_map)} merges."
    )

    config = get_config()
    provider_map = {"GEMINI": GeminiProvider, "OPENROUTER": OpenRouterProvider}
    provider = provider_map[config.ai_provider]()
    ai_deduplication_map = provider.deduplicate_keywords(deduplicated_keywords)

    deduplication_map = {**pre_merge_map, **ai_deduplication_map}

    if not deduplication_map:
        logger.info("No keyword duplications found.")
        return "No keyword duplications found."

    logger.info(f"AI suggested {len(deduplication_map)} keyword amalgamations.")

    for original, canonical in deduplication_map.items():
        if original == canonical:
            continue

        canonical_keyword, _ = Keyword.objects.get_or_create(name=canonical)
        if _:
            logger.info(f"Created new canonical keyword: {canonical}")

        try:
            original_keyword = Keyword.objects.get(name=original)
            recipes_to_update = Recipe.objects.filter(keywords=original_keyword)

            for recipe in recipes_to_update:
                recipe.keywords.remove(original_keyword)
                recipe.keywords.add(canonical_keyword)

            original_keyword.delete()
            logger.info(f"Merged '{original}' into '{canonical}'.")

        except Keyword.DoesNotExist:
            logger.warning(f"Original keyword '{original}' not found in database, skipping.")

    logger.info("Finished keyword deduplication task.")
    return f"Processed {len(deduplication_map)} keyword amalgamations."


def load_books_from_calibre_task():
    try:
        logger.info(f"Starting loading of books from Calibre library at {settings.CALIBRE_ROOT}")
        created_count, updated_count = load_books_from_calibre(Path(settings.CALIBRE_ROOT))
        logger.info(f"Loading complete. Created: {created_count}, Updated: {updated_count}")
        return f"Loading complete. Created: {created_count}, Updated: {updated_count}"
    except FileNotFoundError as e:
        logger.error(f"Error during loading: {e}")
        return str(e)
    except Exception as e:
        logger.error(f"Unexpected error during loading: {e}")
        raise e


def generate_book_embeddings_task(book_id: str):
    try:
        book = Book.objects.get(id=book_id)
        recipes = list(book.recipes.select_related("book").prefetch_related("keywords").all())

        if not recipes:
            logger.info(f"No recipes to embed for book: {book.title}")
            return "No recipes to embed"

        logger.info(f"Generating embeddings for {len(recipes)} recipes from: {book.title}")
        generate_recipe_embeddings_batch(recipes)
        logger.info(f"Finished generating embeddings for {len(recipes)} recipes from: {book.title}")
        return f"Generated embeddings for {len(recipes)} recipes"

    except Book.DoesNotExist:
        logger.error(f"Book with id {book_id} not found")
        return "Book not found"
    except Exception as e:
        logger.error(f"Error generating embeddings for book: {e}")
        raise e


def save_recipes_from_graph_state(
    book: Book, extraction: ExtractionReport, raw_recipes: list[dict]
):
    logger.info(f"Saving {len(raw_recipes)} recipes for {book.title}")

    created_count = 0
    for recipe_dict in raw_recipes:
        try:
            recipe_data = RecipeData(**recipe_dict)
        except Exception as e:
            logger.error(f"Invalid recipe data: {e}")
            continue

        recipe, _ = Recipe.objects.update_or_create(
            book=book,
            name=recipe_data.name,
            defaults={
                "extraction_report": extraction,
                "order": recipe_data.book_order or 0,
                "description": recipe_data.description,
                "ingredients": recipe_data.ingredients,
                "instructions": recipe_data.instructions,
                "yields": recipe_data.yields,
                "image": recipe_data.image,
            },
        )

        keyword_objects = []
        for keyword_name in recipe_data.keywords:
            keyword, _ = Keyword.objects.get_or_create(name=keyword_name)
            keyword_objects.append(keyword)
        recipe.keywords.set(keyword_objects)

        created_count += 1

    recipes_to_embed = (
        Recipe.objects.filter(book=book, extraction_report=extraction)
        .select_related("book")
        .prefetch_related("keywords")
    )

    try:
        provider = get_ai_provider()
        if provider and provider.EMBEDDING_MODEL:
            generate_recipe_embeddings_batch(list(recipes_to_embed))
    except ValueError:
        pass
    except Exception as e:
        embedding_error = f"Batch embedding failed: {e}"
        logger.warning(embedding_error)
        extraction.errors = [*extraction.errors, embedding_error]
        extraction.save(update_fields=["errors"])

    recipes_data = []
    for recipe_dict in raw_recipes:
        try:
            recipes_data.append(RecipeData(**recipe_dict))
        except Exception:
            continue

    with open(book.get_recipes_json_path(), "w") as f:
        json.dump([r.model_dump() for r in recipes_data], f, indent=2, ensure_ascii=False)

    with open(book.get_report_path(), "w") as f:
        json.dump(model_to_dict(extraction), f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"Saved {created_count} recipes for {book.title}")
    return created_count


def extract_recipes_from_book(book_id: str, extraction_id: str | None = None):
    try:
        book = Book.objects.get(id=book_id)
        logger.info(f"Starting LangGraph recipe extraction for book: {book.title}")

        if extraction_id:
            try:
                extraction = ExtractionReport.objects.get(id=extraction_id)
            except Exception:
                extraction = None
        else:
            extraction = None

        if extraction is None:
            config = get_config()
            extraction = ExtractionReport.objects.create(
                book=book,
                provider_name=config.ai_provider,
                status="running",
            )

        extraction.started_at = timezone.now()
        extraction.thread_id = f"report_{extraction.id}"
        extraction.save()

        initial_state = {
            "book_id": str(book.id),
            "epub_path": str(book.get_epub_path()),
            "report_id": str(extraction.id),
            "already_tried": [],
        }

        graph_config = {"configurable": {"thread_id": extraction.thread_id}}

        result = extraction_app.invoke(initial_state, graph_config)

        extraction.refresh_from_db()

        if extraction.status == "review":
            logger.info(f"Extraction paused for human review: {book.title}")
            return f"Extraction paused for review. Check report {extraction.id}"

        if extraction.status == "done":
            raw_recipes = result.get("raw_recipes", [])
            created_count = save_recipes_from_graph_state(book, extraction, raw_recipes)
            logger.info(f"Finished extraction for {book.title}. Processed {created_count} recipes.")
            return f"Extracted {created_count} recipes for {book.title}"

        return "Extraction completed with unknown status"

    except Book.DoesNotExist:
        logger.error(f"Book with id {book_id} not found")
        return "Book not found"
    except Exception as e:
        logger.error(f"Error extracting recipes with LangGraph: {e}")
        raise e
