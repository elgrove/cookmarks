import json
import math

import pytest
import responses
from django.conf import settings

from core.models import Book, Config, ExtractionReport, Keyword, Recipe
from core.services.calibre import load_books_from_calibre
from core.services.epub import get_chapterlike_files_from_epub
from core.tasks import extract_recipes_from_book


BOOKS_DIR = settings.BASE_DIR / "_books"
TEST_CALIBRE_DIR = settings.BASE_DIR / "_test_calibre"

# Test calibre book info
TEST_CALIBRE_BOOK = {
    "title": "Asma's Indian Kitchen: Home-Cooked Food Brought to You by Darjeeling Express",
    "author": "Asma Khan",
    "folder_name": "Asma's Indian Kitchen_ Home-Cooked Food Brought to You by Darjeeling Express (578)",
    "path": "Asma Khan/Asma's Indian Kitchen_ Home-Cooked Food Brought to You by Darjeeling Express (1)",
    "expected_chapters": 4,
}


def load_gold_recipes() -> list[dict]:
    recipes_path = BOOKS_DIR / TEST_CALIBRE_BOOK["folder_name"] / "_cookmarks" / "recipes.json"
    with open(recipes_path) as f:
        return json.load(f)


def split_recipes_for_api_calls(recipes: list[dict], num_calls: int) -> list[str]:
    if num_calls <= 0:
        return []
    
    chunk_size = math.ceil(len(recipes) / num_calls)
    chunks = []
    for i in range(0, len(recipes), chunk_size):
        chunk = recipes[i:i + chunk_size]
        chunks.append(json.dumps(chunk))
    
    while len(chunks) < num_calls:
        chunks.append("[]")
    
    return chunks


@pytest.fixture
def configured_app(db):
    Config.objects.update_or_create(
        pk=1,
        defaults={
            "ai_provider": "OPENROUTER",
            "api_key": "test-api-key",
            "extraction_rate_limit_per_minute": 999,
        },
    )


@pytest.fixture
def calibre_books(db):
    if not TEST_CALIBRE_DIR.exists():
        pytest.skip(f"Test calibre directory not found: {TEST_CALIBRE_DIR}")
    
    created_count, updated_count = load_books_from_calibre(TEST_CALIBRE_DIR)
    
    # Return the book we expect to be loaded
    book = Book.objects.filter(title=TEST_CALIBRE_BOOK["title"]).first()
    if not book:
        pytest.skip(f"Test book not found after loading: {TEST_CALIBRE_BOOK['title']}")
    
    return book


@pytest.mark.django_db(transaction=True)
class TestLoadBooksFromCalibre:

    def test_load_books_creates_book_record(self, db):
        if not TEST_CALIBRE_DIR.exists():
            pytest.skip(f"Test calibre directory not found: {TEST_CALIBRE_DIR}")
        
        # Ensure no books exist before loading
        assert Book.objects.count() == 0
        
        created_count, updated_count = load_books_from_calibre(TEST_CALIBRE_DIR)
        
        # Should have created at least one book
        assert created_count >= 1
        assert Book.objects.count() >= 1
        
        # Verify the test book was loaded correctly
        book = Book.objects.filter(title=TEST_CALIBRE_BOOK["title"]).first()
        assert book is not None, f"Expected book '{TEST_CALIBRE_BOOK['title']}' not found"
        assert book.author == TEST_CALIBRE_BOOK["author"]
        assert book.calibre_id is not None
        assert book.path is not None

    def test_loaded_book_has_valid_epub_path(self, db):
        if not TEST_CALIBRE_DIR.exists():
            pytest.skip(f"Test calibre directory not found: {TEST_CALIBRE_DIR}")
        
        load_books_from_calibre(TEST_CALIBRE_DIR)
        
        book = Book.objects.filter(title=TEST_CALIBRE_BOOK["title"]).first()
        assert book is not None
        
        # The book's get_epub_path method should return a valid path
        epub_path = book.get_epub_path()
        assert epub_path is not None
        assert epub_path.exists(), f"EPUB file not found at {epub_path}"
        assert epub_path.suffix == ".epub"

    def test_load_books_updates_existing_records(self, db):
        if not TEST_CALIBRE_DIR.exists():
            pytest.skip(f"Test calibre directory not found: {TEST_CALIBRE_DIR}")
        
        # First load
        created_count_1, updated_count_1 = load_books_from_calibre(TEST_CALIBRE_DIR)
        book_count_after_first = Book.objects.count()
        
        # Second load should update, not create
        created_count_2, updated_count_2 = load_books_from_calibre(TEST_CALIBRE_DIR)
        
        # No new books should be created
        assert created_count_2 == 0
        assert updated_count_2 == created_count_1
        assert Book.objects.count() == book_count_after_first


def mock_openrouter_response(response_content: str):
    responses.add(
        responses.POST,
        "https://openrouter.ai/api/v1/chat/completions",
        json={
            "choices": [{"message": {"content": response_content}}],
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "cost": 0.001,
            },
        },
        status=200,
    )


@pytest.mark.django_db(transaction=True)
class TestExtractRecipesFromBookTask:

    @responses.activate
    def test_task_full_flow(self, configured_app, calibre_books):
        # Get the book loaded from calibre database
        book = calibre_books
        
        # Get epub path from the book model (as the real application does)
        epub_path = book.get_epub_path()
        if not epub_path or not epub_path.exists():
            pytest.skip("No epub found for test calibre book")
        
        # Load gold recipes from _books directory
        gold_recipes = load_gold_recipes()
        
        # Calculate expected API calls (file extraction with expected chapters)
        chapter_count = len(get_chapterlike_files_from_epub(epub_path))
        recipe_chunks = split_recipes_for_api_calls(gold_recipes, chapter_count)
        
        # Mock recipe extraction API calls
        for chunk in recipe_chunks:
            mock_openrouter_response(chunk)
        
        # === RUN THE TASK ===
        result = extract_recipes_from_book(str(book.id))
        
        # === VALIDATE RESULT MESSAGE ===
        assert "Extracted" in result
        assert "recipes" in result.lower()
        
        # === VALIDATE EXTRACTION REPORT IN DATABASE ===
        report = ExtractionReport.objects.filter(book=book).first()
        assert report is not None, "ExtractionReport should be created in database"
        assert report.started_at is not None
        assert report.completed_at is not None
        assert report.provider_name == "OPENROUTER"
        assert report.recipes_found > 0
        assert report.errors == []
        
        # === VALIDATE RECIPES IN DATABASE ===
        db_recipes = Recipe.objects.filter(book=book)
        assert db_recipes.count() > 0, "Recipes should be created in database"
        assert db_recipes.count() == report.recipes_found
        
        for recipe in db_recipes:
            assert recipe.name, "Recipe should have name"
            assert recipe.ingredients, "Recipe should have ingredients"
            assert recipe.instructions, "Recipe should have instructions"
            assert recipe.order > 0, "Recipe should have order"
            assert recipe.extraction_report == report, "Recipe should link to report"
        
        # === VALIDATE KEYWORDS ===
        recipes_with_keywords = [r for r in db_recipes if r.keywords.count() > 0]
        assert len(recipes_with_keywords) > 0, "Some recipes should have keywords"
        assert Keyword.objects.count() > 0, "Keywords should be created"
        
        # === VALIDATE JSON FILES ===
        recipes_json_path = book.get_recipes_json_path()
        assert recipes_json_path.exists(), "recipes.json should be saved"
        with open(recipes_json_path) as f:
            saved_recipes = json.load(f)
        assert len(saved_recipes) == db_recipes.count()
        
        report_json_path = book.get_report_path()
        assert report_json_path.exists(), "report.json should be saved"
        with open(report_json_path) as f:
            saved_report = json.load(f)
        assert "book" in saved_report
        assert "provider_name" in saved_report
        assert "extraction_method" in saved_report
        assert saved_report["recipes_found"] == db_recipes.count()

    def test_task_handles_missing_book(self, configured_app):
        result = extract_recipes_from_book("00000000-0000-0000-0000-000000000000")
        assert result == "Book not found"

    @responses.activate
    def test_task_with_existing_extraction_id(self, configured_app, calibre_books):
        # Get the book loaded from calibre database
        book = calibre_books
        
        # Get epub path from the book model (as the real application does)
        epub_path = book.get_epub_path()
        if not epub_path or not epub_path.exists():
            pytest.skip("No epub found for test calibre book")
        
        gold_recipes = load_gold_recipes()
        chapter_count = len(get_chapterlike_files_from_epub(epub_path))
        recipe_chunks = split_recipes_for_api_calls(gold_recipes, chapter_count)
        
        for chunk in recipe_chunks:
            mock_openrouter_response(chunk)
        
        # Pre-create an extraction report
        existing_report = ExtractionReport.objects.create(
            book=book,
            provider_name="OPENROUTER",
            extraction_method="file",
        )
        
        # Run task with existing extraction ID
        result = extract_recipes_from_book(str(book.id), str(existing_report.id))
        
        assert "Extracted" in result
        
        # Should use the existing report, not create a new one
        assert ExtractionReport.objects.filter(book=book).count() == 1
        
        existing_report.refresh_from_db()
        assert existing_report.started_at is not None
        assert existing_report.completed_at is not None
        assert existing_report.recipes_found > 0
