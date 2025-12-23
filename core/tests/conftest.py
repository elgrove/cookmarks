import json
import math

import pytest
from django.conf import settings

from core.models import Book, Config
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
