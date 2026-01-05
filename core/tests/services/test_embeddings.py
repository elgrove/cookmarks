import tempfile
from unittest.mock import MagicMock, patch

import pytest

from core.models import Book, Config, Keyword, Recipe
from core.services.embeddings import (
    VectorStore,
    generate_recipe_embedding,
    generate_recipe_embeddings_batch,
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
            patch("core.services.embeddings.get_ai_provider") as mock_get_provider,
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

    def test_batch_generates_and_stores_embeddings(self, gemini_config, sample_book):
        recipe1 = Recipe.objects.create(
            book=sample_book, order=1, name="Recipe 1", ingredients=["ingredient 1"]
        )
        recipe2 = Recipe.objects.create(
            book=sample_book, order=2, name="Recipe 2", ingredients=["ingredient 2"]
        )
        recipes = [recipe1, recipe2]

        fake_embeddings = [[0.1] * 3072, [0.2] * 3072]

        with (
            patch("core.services.embeddings.get_ai_provider") as mock_get_provider,
            patch("core.services.embeddings.VectorStore") as mock_store_class,
        ):
            mock_provider = MagicMock()
            mock_provider.generate_embeddings_batch.return_value = fake_embeddings
            mock_get_provider.return_value = mock_provider

            mock_store = MagicMock()
            mock_store_class.return_value = mock_store

            generate_recipe_embeddings_batch(recipes)

            mock_provider.generate_embeddings_batch.assert_called_once()
            call_args = mock_provider.generate_embeddings_batch.call_args
            assert len(call_args[0][0]) == 2
            assert "Recipe 1" in call_args[0][0][0]
            assert "Recipe 2" in call_args[0][0][1]

            mock_store.upsert_batch.assert_called_once()
            batch_items = mock_store.upsert_batch.call_args[0][0]
            assert len(batch_items) == 2
            assert batch_items[0] == (str(recipe1.id), fake_embeddings[0])
            assert batch_items[1] == (str(recipe2.id), fake_embeddings[1])


class TestSearchRecipes:
    def test_searches_and_returns_recipes(self, gemini_config, sample_recipe):
        fake_query_embedding = [0.2] * 3072

        with (
            patch("core.services.embeddings.get_ai_provider") as mock_get_provider,
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
                "spicy curry", "RETRIEVAL_QUERY"
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

    def test_upsert_batch_and_search(self, gemini_config):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        store = VectorStore(db_path=db_path)

        embedding1 = [1.0, 0.0, 0.0] + [0.0] * 3069
        embedding2 = [0.0, 1.0, 0.0] + [0.0] * 3069
        embedding3 = [0.0, 0.0, 1.0] + [0.0] * 3069

        items = [
            ("recipe-1", embedding1),
            ("recipe-2", embedding2),
            ("recipe-3", embedding3),
        ]
        store.upsert_batch(items)

        query = [0.9, 0.1, 0.0] + [0.0] * 3069
        results = store.search(query, limit=3)

        assert len(results) == 3
        assert results[0][0] == "recipe-1"
