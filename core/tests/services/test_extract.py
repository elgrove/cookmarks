import json
import math
from dataclasses import dataclass
from pathlib import Path

import pytest
import responses
from django.conf import settings

from core.models import Book, Config
from core.services.epub import CHAPTER_BLOCK_COUNT, get_chapterlike_files_from_epub
from core.services.extract import extract_recipe_data_from_book

EVAL_DIR = settings.BASE_DIR / "_eval"


@dataclass
class EvalBook:
    name: str
    folder_name: str
    author: str
    expected_extraction_method: str
    expected_images_in_separate_chapters: bool
    expected_images_can_be_matched: bool | None
    expected_total_chapters: int


EVAL_BOOKS = [
    EvalBook(
        name="Craveable",
        folder_name="Craveable_ All I Want to Eat, Big Flavours for Every Mood (751)",
        author="Seema Pankhania",
        expected_extraction_method="file",
        expected_images_in_separate_chapters=False,
        expected_images_can_be_matched=None,
        expected_total_chapters=16,
    ),
    EvalBook(
        name="Nothing Fancy",
        folder_name="Nothing Fancy_ Unfussy Food for Having People Over (227)",
        author="Alison Roman",
        expected_extraction_method="block",
        expected_images_in_separate_chapters=True,
        expected_images_can_be_matched=True,
        expected_total_chapters=273,
    ),
    EvalBook(
        name="The Curry Guy",
        folder_name="The Curry Guy_ Recreate Over 100 of the Best British Indian Restaurant Recipes at Home (502)",
        author="Dan Toombs",
        expected_extraction_method="file",
        expected_images_in_separate_chapters=False,
        expected_images_can_be_matched=None,
        expected_total_chapters=125,
    ),
]


def load_gold_recipes(book_folder: str) -> list[dict]:
    recipes_path = EVAL_DIR / book_folder / "_cookmarks" / "recipes.json"
    with open(recipes_path) as f:
        return json.load(f)


def load_gold_report(book_folder: str) -> dict:
    report_path = EVAL_DIR / book_folder / "_cookmarks" / "report.json"
    with open(report_path) as f:
        return json.load(f)


def get_epub_path(book_folder: str) -> Path:
    book_path = EVAL_DIR / book_folder
    epub_files = list(book_path.glob("*.epub"))
    return epub_files[0] if epub_files else None


def split_recipes_for_api_calls(recipes: list[dict], num_calls: int) -> list[str]:
    if num_calls <= 0:
        return []

    chunk_size = math.ceil(len(recipes) / num_calls)
    chunks = []
    for i in range(0, len(recipes), chunk_size):
        chunk = recipes[i : i + chunk_size]
        chunks.append(json.dumps(chunk))

    # Pad with empty arrays if we need more calls than recipe chunks
    while len(chunks) < num_calls:
        chunks.append("[]")

    return chunks


def calculate_expected_api_calls(epub_path: Path, extraction_method: str) -> int:
    chapter_files = get_chapterlike_files_from_epub(epub_path)

    if extraction_method == "block":
        return CHAPTER_BLOCK_COUNT
    else:
        return len(chapter_files)


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
class TestExtractRecipeDataFromBook:
    @responses.activate
    @pytest.mark.parametrize("eval_book", EVAL_BOOKS, ids=[b.name for b in EVAL_BOOKS])
    def test_extract_function_on_eval_books(self, configured_app, eval_book: EvalBook):
        book_path = EVAL_DIR / eval_book.folder_name
        if not book_path.exists():
            pytest.skip(f"Eval book not found: {eval_book.folder_name}")

        epub_path = get_epub_path(eval_book.folder_name)
        if not epub_path:
            pytest.skip(f"No epub found for: {eval_book.folder_name}")

        # Load gold standard data
        gold_recipes = load_gold_recipes(eval_book.folder_name)

        # Calculate expected API calls
        expected_api_calls = calculate_expected_api_calls(
            epub_path, eval_book.expected_extraction_method
        )

        # Split recipes to match expected API calls
        recipe_chunks = split_recipes_for_api_calls(gold_recipes, expected_api_calls)

        # Mock the image match check for books with separate image chapters
        if eval_book.expected_images_in_separate_chapters:
            image_match_response = "yes" if eval_book.expected_images_can_be_matched else "no"
            mock_openrouter_response(image_match_response)

        # Mock recipe extraction API calls
        for chunk in recipe_chunks:
            mock_openrouter_response(chunk)

        # Create test book
        book = Book.objects.create(
            title=eval_book.folder_name,
            author=eval_book.author,
            path=str(book_path),
            calibre_id=hash(eval_book.folder_name) % 10000,
        )

        # === RUN THE FUNCTION ===
        recipes, report = extract_recipe_data_from_book(book)

        # === VALIDATE RECIPES ===
        assert recipes is not None, "Should return recipes list"
        assert len(recipes) > 0, "Should extract recipes"

        for recipe in recipes:
            assert recipe.name, "Recipe should have a name"
            assert recipe.ingredients, "Recipe should have ingredients"
            assert recipe.instructions, "Recipe should have instructions"
            assert recipe.author == book.author, "Recipe should have book author"
            assert recipe.book_title == book.title, "Recipe should have book title"
            assert recipe.book_order is not None, "Recipe should have book_order"

        # Check recipes are ordered
        orders = [r.book_order for r in recipes]
        assert orders == sorted(orders), "Recipes should be in order"

        # === VALIDATE EXTRACTION REPORT ===
        assert report is not None, "Should return ExtractionReport"
        assert report.book == book
        assert report.provider_name == "OPENROUTER"
        assert report.started_at is not None
        assert report.completed_at is not None
        assert report.extraction_method == eval_book.expected_extraction_method, (
            f"Expected {eval_book.expected_extraction_method}, got {report.extraction_method}"
        )
        assert report.images_in_separate_chapters == eval_book.expected_images_in_separate_chapters
        assert report.total_chapters == eval_book.expected_total_chapters
        assert len(report.chapters_processed) > 0
        assert report.recipes_found == len(recipes)
        assert report.errors == []

        # Validate image matching for books with separate chapters
        if eval_book.expected_images_in_separate_chapters:
            assert report.images_can_be_matched == eval_book.expected_images_can_be_matched

    @responses.activate
    def test_extract_function_handles_empty_response(self, configured_app):
        eval_book = EVAL_BOOKS[0]  # Craveable - simplest case
        book_path = EVAL_DIR / eval_book.folder_name

        if not book_path.exists():
            pytest.skip(f"Eval book not found: {eval_book.folder_name}")

        epub_path = get_epub_path(eval_book.folder_name)
        expected_api_calls = calculate_expected_api_calls(epub_path, "file")

        # Mock all API calls to return empty arrays
        for _ in range(expected_api_calls):
            mock_openrouter_response("[]")

        book = Book.objects.create(
            title=eval_book.folder_name,
            author=eval_book.author,
            path=str(book_path),
            calibre_id=99998,
        )

        recipes, report = extract_recipe_data_from_book(book)

        assert recipes == []
        assert report.recipes_found == 0
        assert report.completed_at is not None
