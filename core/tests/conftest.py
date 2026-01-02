import json
import math
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

from core.models import Book, Config, RecipeData
from core.services.calibre import load_books_from_calibre

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
        chunk = recipes[i : i + chunk_size]
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


@pytest.fixture
def mock_langgraph_extraction():
    """
    Consolidated fixture for LangGraph extraction tests.
    Patches all external dependencies with sensible defaults.
    Tests can override specific mock behaviors as needed.
    """
    graph_module = "core.services.extraction.graph"

    with ExitStack() as stack:
        mocks = {
            "get_epub_path": stack.enter_context(patch("core.models.Book.get_epub_path")),
            "get_chapters": stack.enter_context(
                patch(f"{graph_module}.get_chapterlike_files_from_epub")
            ),
            "has_separate_images": stack.enter_context(
                patch(f"{graph_module}.has_separate_image_chapters")
            ),
            "get_config": stack.enter_context(patch(f"{graph_module}.get_config")),
            "sample_content": stack.enter_context(
                patch(f"{graph_module}.get_sample_chapters_content")
            ),
            "split_blocks": stack.enter_context(
                patch(f"{graph_module}.split_chapters_into_blocks")
            ),
            "block_content": stack.enter_context(patch(f"{graph_module}.get_block_content")),
            "build_lookup": stack.enter_context(patch(f"{graph_module}.build_image_path_lookup")),
            "resolve_image": stack.enter_context(
                patch(f"{graph_module}.resolve_image_path_in_epub")
            ),
            "extract_file": stack.enter_context(patch(f"{graph_module}.extract_file")),
            "save_recipes": stack.enter_context(patch("core.tasks.save_recipes_from_graph_state")),
            "gemini_provider": stack.enter_context(patch(f"{graph_module}.GeminiProvider")),
        }

        # Set sensible defaults
        mocks["get_epub_path"].return_value = "/fake/path/to/book/test.epub"
        mocks["get_chapters"].return_value = ["chapter1.xhtml", "chapter2.xhtml"]
        mocks["has_separate_images"].return_value = False
        mocks["sample_content"].return_value = "sample content"
        mocks["split_blocks"].return_value = [[("chapter1.xhtml", "chapter2.xhtml")]]
        mocks["block_content"].return_value = "Sample HTML content with recipes"
        mocks["build_lookup"].return_value = {"image1.jpg": ["OEBPS/images/image1.jpg"]}
        mocks["resolve_image"].return_value = "OEBPS/images/image1.jpg"
        mocks["save_recipes"].return_value = 1

        # Config mock
        mock_config = MagicMock()
        mock_config.ai_provider = "GEMINI"
        mock_config.extraction_rate_limit_per_minute = 999
        mocks["get_config"].return_value = mock_config

        # Gemini provider mock with default behaviors
        provider_instance = mocks["gemini_provider"].return_value
        provider_instance.check_if_can_match_images.return_value = (
            True,
            {
                "cost_usd": 0.001,
                "input_tokens": 100,
                "output_tokens": 10,
            },
        )
        provider_instance._get_model_for_extraction_method.return_value = "gemini-1.5-flash"
        provider_instance.extract_recipes.return_value = (
            [
                RecipeData(
                    name="Test Recipe",
                    image="image1.jpg",
                    ingredients=["ingredient 1"],
                    instructions=["step 1"],
                )
            ],
            {"cost_usd": None, "input_tokens": 50, "output_tokens": 20},
        )

        # Default extract_file response
        mocks["extract_file"].return_value = {
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

        yield mocks
