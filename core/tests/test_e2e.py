import json

import pytest
import responses

from core.models import ExtractionReport, Keyword, Recipe
from core.services.epub import get_chapterlike_files_from_epub
from core.tasks import extract_recipes_from_book
from core.tests.conftest import load_gold_recipes, split_recipes_for_api_calls

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
    def test_task(self, configured_app, calibre_books):
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
