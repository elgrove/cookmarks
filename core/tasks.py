import json
import logging
from pathlib import Path

from django.conf import settings
from django.forms.models import model_to_dict
from django.utils import timezone

from core.models import Book, ExtractionReport, Keyword, Recipe
from core.services.ai import GeminiProvider, OpenRouterProvider, get_config
from core.services.calibre import load_books_from_calibre
from core.services.extract import extract_recipe_data_from_book

logger = logging.getLogger(__name__)

def extract_recipes_from_book(book_id: str, extraction_id: str | None = None):
    try:
        book = Book.objects.get(id=book_id)
        logger.info(f"Starting recipe extraction for book: {book.title}")
        # find existing extraction record if provided else create one
        extraction = None
        if extraction_id:
            try:
                extraction = ExtractionReport.objects.get(id=extraction_id)
            except Exception:
                extraction = None

        if extraction is None:
            config = get_config()
            extraction = ExtractionReport.objects.create(
                book=book,
                provider_name=config.ai_provider,
                extraction_method="file",
            )

        # mark started and save
        extraction.started_at = timezone.now()
        extraction.save()

        recipes_data, extraction = extract_recipe_data_from_book(book, report=extraction)
        
        logger.info(f"Found {len(recipes_data)} recipes for {book.title}")
        
        created_count = 0
        for order, recipe_data in enumerate(recipes_data, start=1):
            recipe, created = Recipe.objects.update_or_create(
                book=book,
                name=recipe_data.name,
                defaults={
                    'extraction_report': extraction,
                    'order': order,
                    'description': recipe_data.description,
                    'ingredients': recipe_data.ingredients,
                    'instructions': recipe_data.instructions,
                    'yields': recipe_data.yields,
                    'image': recipe_data.image,
                }
            )
            
            keyword_objects = []
            for keyword_name in recipe_data.keywords:
                keyword, _ = Keyword.objects.get_or_create(name=keyword_name)
                keyword_objects.append(keyword)
            recipe.keywords.set(keyword_objects)
            
            created_count += 1

        with open(book.get_recipes_json_path(), 'w') as f:
            json.dump([r.model_dump() for r in recipes_data], f, indent=2, ensure_ascii=False)

        with open(book.get_report_path(), 'w') as f:
            json.dump(model_to_dict(extraction), f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"Finished extraction for {book.title}. Processed {created_count} recipes.")
        return f"Extracted {created_count} recipes for {book.title}"

    except Book.DoesNotExist:
        logger.error(f"Book with id {book_id} not found")
        return "Book not found"
    except Exception as e:
        logger.error(f"Error extracting recipes: {e}")
        raise e

def deduplicate_keywords_task():
    logger.info("Starting keyword deduplication task.")
    
    all_keywords = list(Keyword.objects.values_list('name', flat=True))
    logger.info(f"Found {len(all_keywords)} keywords to process.")
    
    config = get_config()
    provider_map = {'GEMINI': GeminiProvider, "OPENROUTER": OpenRouterProvider}
    provider = provider_map[config.ai_provider]()
    deduplication_map = provider.deduplicate_keywords(all_keywords)
    
    if not deduplication_map:
        logger.info("No keyword duplications found.")
        return "No keyword duplications found."
        
    logger.info(f"AI suggested {len(deduplication_map)} keyword amalgamations.")
    
    for original, canonical in deduplication_map.items():
        if original == canonical:
            continue

        canonical_keyword, created = Keyword.objects.get_or_create(name=canonical)
        if created:
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
