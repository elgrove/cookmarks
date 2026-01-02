import json
from unittest.mock import MagicMock, patch

import pytest
import responses

from core.models import Book, ExtractionReport, Keyword, Recipe, RecipeData
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


@pytest.mark.django_db(transaction=True)
class TestLangGraphExtractionE2E:
    @patch("core.services.extraction.graph.get_chapterlike_files_from_epub")
    @patch("core.services.extraction.graph.has_separate_image_chapters")
    @patch("core.services.extraction.graph.extract_file")
    @patch("core.models.Book.get_epub_path")
    def test_full_extraction_file_method(
        self,
        mock_get_path,
        mock_extract_file,
        mock_has_separate,
        mock_get_files,
        configured_app,
    ):
        book = Book.objects.create(
            calibre_id=999,
            title="Test Cookbook",
            author="Test Author",
            path="/fake/path/to/book",
        )

        mock_get_path.return_value = "/fake/path/to/book/test.epub"
        mock_get_files.return_value = ["chapter1.xhtml", "chapter2.xhtml"]
        mock_has_separate.return_value = False
        mock_extract_file.return_value = {
            "raw_recipes": [
                {
                    "name": "Recipe 1",
                    "image": "image1.jpg",
                    "ingredients": ["ingredient 1"],
                    "instructions": ["step 1"],
                },
                {
                    "name": "Recipe 2",
                    "image": "image2.jpg",
                    "ingredients": ["ingredient 2"],
                    "instructions": ["step 2"],
                },
            ]
        }

        result = extract_recipes_from_book(str(book.id))

        assert "Extracted" in result or "paused" in result.lower()

        report = ExtractionReport.objects.filter(book=book).first()
        assert report is not None

        if report.status == "done":
            assert report.recipes_found > 0
            recipes = Recipe.objects.filter(book=book)
            assert recipes.count() == report.recipes_found

    @patch("core.tasks.save_recipes_from_graph_state")
    @patch("core.services.extraction.graph.get_chapterlike_files_from_epub")
    @patch("core.services.extraction.graph.has_separate_image_chapters")
    @patch("core.services.extraction.graph.get_config")
    @patch("core.services.extraction.graph.get_sample_chapters_content")
    @patch("core.services.extraction.graph.split_chapters_into_blocks")
    @patch("core.services.extraction.graph.get_block_content")
    @patch("core.services.extraction.graph.build_image_path_lookup")
    @patch("core.services.extraction.graph.resolve_image_path_in_epub")
    @patch("core.models.Book.get_epub_path")
    def test_full_extraction_block_method(
        self,
        mock_get_path,
        mock_resolve_image,
        mock_build_lookup,
        mock_get_block_content,
        mock_split_blocks,
        mock_sample_content,
        mock_get_config,
        mock_has_separate,
        mock_get_files,
        mock_save_recipes,
        configured_app,
    ):
        book = Book.objects.create(
            calibre_id=999,
            title="Test Cookbook",
            author="Test Author",
            path="/fake/path/to/book",
        )

        mock_get_path.return_value = "/fake/path/to/book/test.epub"
        mock_get_files.return_value = ["chapter1.xhtml", "chapter2.xhtml"]
        mock_has_separate.return_value = True
        mock_sample_content.return_value = "sample content"
        mock_build_lookup.return_value = {"image1.jpg": ["OEBPS/images/image1.jpg"]}
        mock_resolve_image.return_value = "OEBPS/images/image1.jpg"
        mock_split_blocks.return_value = [["chapter1.xhtml", "chapter2.xhtml"]]
        mock_get_block_content.return_value = "Sample HTML content with recipes"
        mock_save_recipes.return_value = 1

        mock_config = MagicMock()
        mock_config.ai_provider = "GEMINI"
        mock_config.extraction_rate_limit_per_minute = 999
        mock_get_config.return_value = mock_config

        with patch("core.services.extraction.graph.GeminiProvider") as mock_provider_class:
            provider_instance = mock_provider_class.return_value
            provider_instance.check_if_can_match_images.return_value = (
                True,
                {"cost_usd": 0.001, "input_tokens": 100, "output_tokens": 10},
            )
            provider_instance._get_model_for_extraction_method.return_value = "gemini-1.5-flash"

            test_recipe = RecipeData(
                name="Recipe 1",
                image="image1.jpg",
                ingredients=["ingredient 1"],
                instructions=["step 1"],
            )
            provider_instance.extract_recipes.return_value = (
                [test_recipe],
                {"cost_usd": None, "input_tokens": 50, "output_tokens": 20},
            )

            result = extract_recipes_from_book(str(book.id))

            assert "Extracted 1 recipes" in result

            report = ExtractionReport.objects.filter(book=book).first()
            assert report is not None
            assert report.status == "done"
            assert report.recipes_found == 1

    @patch("core.services.extraction.graph.get_chapterlike_files_from_epub")
    @patch("core.services.extraction.graph.has_separate_image_chapters")
    @patch("core.services.extraction.graph.get_config")
    @patch("core.services.extraction.graph.get_sample_chapters_content")
    @patch("core.services.extraction.graph.extract_file")
    @patch("core.services.extraction.graph.build_image_path_lookup")
    @patch("core.services.extraction.graph.resolve_image_path_in_epub")
    @patch("core.models.Book.get_epub_path")
    def test_extraction_pauses_for_human_review(
        self,
        mock_get_path,
        mock_resolve_image,
        mock_build_lookup,
        mock_extract_file,
        mock_sample_content,
        mock_get_config,
        mock_has_separate,
        mock_get_files,
        configured_app,
    ):
        book = Book.objects.create(
            calibre_id=999,
            title="Test Cookbook",
            author="Test Author",
            path="/fake/path/to/book",
        )

        mock_get_path.return_value = "/fake/path/to/book/test.epub"
        mock_get_files.return_value = ["chapter1.xhtml", "chapter2.xhtml"]
        mock_has_separate.return_value = True
        mock_sample_content.return_value = "sample content"
        mock_build_lookup.return_value = {}
        mock_resolve_image.return_value = None

        mock_config = MagicMock()
        mock_config.ai_provider = "GEMINI"
        mock_get_config.return_value = mock_config

        with patch("core.services.extraction.graph.GeminiProvider") as mock_provider:
            provider_instance = mock_provider.return_value
            provider_instance.check_if_can_match_images.return_value = (
                False,
                {},
            )
            provider_instance._get_model_for_extraction_method.return_value = "gemini-1.5-flash"

            mock_extract_file.return_value = {
                "raw_recipes": [
                    {
                        "name": "Test Recipe",
                        "image": None,
                        "ingredients": ["test"],
                        "instructions": ["test"],
                    }
                ]
            }

            result = extract_recipes_from_book(str(book.id))

        assert "paused for review" in result.lower()

        report = ExtractionReport.objects.filter(book=book).first()
        assert report.status == "review"
