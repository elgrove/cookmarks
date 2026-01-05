import tempfile
from unittest.mock import MagicMock, patch

import pytest

from core.models import Book, Config, Keyword, Recipe
from core.services.embeddings import (
    VectorStore,
    generate_recipe_embedding,
    recipe_to_text,
    search_recipes,
)


@pytest.fixture
def gemini_config(db):
    Config.objects.update_or_create(
        pk=1,
        defaults={
            "ai_provider": "GEMINI",
            "api_key": "test-api-key",
        },
    )


@pytest.fixture
def sample_book(db):
    return Book.objects.create(
        calibre_id=1,
        title="Test Cookbook",
        author="Test Author",
        path="/fake/path",
    )


@pytest.fixture
def sample_recipe(sample_book):
    recipe = Recipe.objects.create(
        book=sample_book,
        order=1,
        name="Thai Green Curry",
        ingredients=["coconut milk", "green curry paste", "chicken"],
    )
    kw1 = Keyword.objects.create(name="Thai")
    kw2 = Keyword.objects.create(name="Curry")
    recipe.keywords.add(kw1, kw2)
    return recipe


class TestRecipeToText:
    def test_basic_recipe(self, sample_recipe):
        text = recipe_to_text(sample_recipe)

        assert "Thai Green Curry" in text
        assert "Thai" in text
        assert "Curry" in text
        assert "coconut milk" in text
        assert "green curry paste" in text


class TestGenerateRecipeEmbedding:
    def test_generates_and_stores_embedding(self, gemini_config, sample_recipe):
        fake_embedding = [0.1] * 3072

        with (
            patch("core.services.embeddings.get_embedding_provider") as mock_get_provider,
            patch("core.services.embeddings.VectorStore") as mock_store_class,
        ):
            mock_provider = MagicMock()
            mock_provider.generate_embedding.return_value = fake_embedding
            mock_get_provider.return_value = mock_provider

            mock_store = MagicMock()
            mock_store_class.return_value = mock_store

            generate_recipe_embedding(sample_recipe)

            mock_provider.generate_embedding.assert_called_once()
            call_args = mock_provider.generate_embedding.call_args
            assert "Thai Green Curry" in call_args[0][0]

            mock_store.upsert.assert_called_once_with(str(sample_recipe.id), fake_embedding)


class TestSearchRecipes:
    def test_searches_and_returns_recipes(self, gemini_config, sample_recipe):
        fake_query_embedding = [0.2] * 3072

        with (
            patch("core.services.embeddings.get_embedding_provider") as mock_get_provider,
            patch("core.services.embeddings.VectorStore") as mock_store_class,
        ):
            mock_provider = MagicMock()
            mock_provider.generate_embedding.return_value = fake_query_embedding
            mock_get_provider.return_value = mock_provider

            mock_store = MagicMock()
            mock_store.search.return_value = [(str(sample_recipe.id), 0.1)]
            mock_store_class.return_value = mock_store

            results = search_recipes("spicy curry")

            mock_provider.generate_embedding.assert_called_once_with(
                "spicy curry", task_type="RETRIEVAL_QUERY"
            )
            mock_store.search.assert_called_once()

            assert len(results) == 1
            assert results[0].id == sample_recipe.id


class TestVectorStoreIntegration:
    def test_upsert_and_search(self, gemini_config):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        store = VectorStore(db_path=db_path)

        embedding1 = [1.0, 0.0, 0.0] + [0.0] * 3069
        embedding2 = [0.0, 1.0, 0.0] + [0.0] * 3069

        store.upsert("recipe-1", embedding1)
        store.upsert("recipe-2", embedding2)

        query = [0.9, 0.1, 0.0] + [0.0] * 3069
        results = store.search(query, limit=2)

        assert len(results) == 2
        assert results[0][0] == "recipe-1"
