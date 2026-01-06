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


class TestVectorSearchEndToEnd:
    def test_full_search_flow_with_real_vector_store(self, gemini_config, sample_book):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        thai_recipe = Recipe.objects.create(
            book=sample_book,
            order=1,
            name="Thai Green Curry",
            ingredients=["coconut milk", "green curry paste", "chicken"],
        )
        italian_recipe = Recipe.objects.create(
            book=sample_book,
            order=2,
            name="Spaghetti Carbonara",
            ingredients=["pasta", "eggs", "pancetta", "parmesan"],
        )
        indian_recipe = Recipe.objects.create(
            book=sample_book,
            order=3,
            name="Butter Chicken",
            ingredients=["chicken", "butter", "tomatoes", "cream"],
        )

        # Embeddings designed for cosine similarity ordering
        # Query is [1.0, 0, 0, ...]
        # Thai is closest: [0.95, 0.05, 0, ...] - nearly same direction
        # Indian is next: [0.7, 0.3, 0, ...] - more divergence
        # Italian is furthest: [0, 1, 0, ...] - perpendicular
        thai_embedding = [0.95, 0.05, 0.0] + [0.0] * 3069
        italian_embedding = [0.0, 1.0, 0.0] + [0.0] * 3069
        indian_embedding = [0.7, 0.3, 0.0] + [0.0] * 3069

        store = VectorStore(db_path=db_path)
        store.upsert(str(thai_recipe.id), thai_embedding)
        store.upsert(str(italian_recipe.id), italian_embedding)
        store.upsert(str(indian_recipe.id), indian_embedding)

        query_embedding = [1.0, 0.0, 0.0] + [0.0] * 3069

        with (
            patch("core.services.embeddings.get_ai_provider") as mock_get_provider,
            patch("core.services.embeddings.VectorStore") as mock_store_class,
        ):
            mock_provider = MagicMock()
            mock_provider.generate_embedding.return_value = query_embedding
            mock_get_provider.return_value = mock_provider

            mock_store_class.return_value = store

            results = search_recipes("spicy asian curry", limit=3)

            mock_provider.generate_embedding.assert_called_once_with(
                "spicy asian curry", "RETRIEVAL_QUERY"
            )

            assert len(results) == 3
            assert results[0].name == "Thai Green Curry"
            assert results[1].name == "Butter Chicken"
            assert results[2].name == "Spaghetti Carbonara"

    def test_search_returns_results_in_similarity_order(self, gemini_config, sample_book):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        recipe_a = Recipe.objects.create(
            book=sample_book, order=1, name="Recipe A", ingredients=["a"]
        )
        recipe_b = Recipe.objects.create(
            book=sample_book, order=2, name="Recipe B", ingredients=["b"]
        )
        recipe_c = Recipe.objects.create(
            book=sample_book, order=3, name="Recipe C", ingredients=["c"]
        )

        store = VectorStore(db_path=db_path)
        store.upsert(str(recipe_a.id), [0.1, 0.9, 0.0] + [0.0] * 3069)
        store.upsert(str(recipe_b.id), [0.5, 0.5, 0.0] + [0.0] * 3069)
        store.upsert(str(recipe_c.id), [0.9, 0.1, 0.0] + [0.0] * 3069)

        query_embedding = [1.0, 0.0, 0.0] + [0.0] * 3069

        with (
            patch("core.services.embeddings.get_ai_provider") as mock_get_provider,
            patch("core.services.embeddings.VectorStore") as mock_store_class,
        ):
            mock_provider = MagicMock()
            mock_provider.generate_embedding.return_value = query_embedding
            mock_get_provider.return_value = mock_provider
            mock_store_class.return_value = store

            results = search_recipes("test query", limit=3)

            assert len(results) == 3
            assert results[0].name == "Recipe C"
            assert results[1].name == "Recipe B"
            assert results[2].name == "Recipe A"

    def test_search_respects_limit(self, gemini_config, sample_book):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        store = VectorStore(db_path=db_path)

        for i in range(10):
            recipe = Recipe.objects.create(
                book=sample_book, order=i, name=f"Recipe {i}", ingredients=[f"ingredient {i}"]
            )
            store.upsert(str(recipe.id), [float(i) / 10] + [0.0] * 3071)

        query_embedding = [1.0] + [0.0] * 3071

        with (
            patch("core.services.embeddings.get_ai_provider") as mock_get_provider,
            patch("core.services.embeddings.VectorStore") as mock_store_class,
        ):
            mock_provider = MagicMock()
            mock_provider.generate_embedding.return_value = query_embedding
            mock_get_provider.return_value = mock_provider
            mock_store_class.return_value = store

            results = search_recipes("test", limit=5)

            assert len(results) == 5

    def test_search_handles_no_provider(self, db):
        results = search_recipes("test query")
        assert results == []

    def test_search_handles_embedding_failure(self, gemini_config):
        with patch("core.services.embeddings.get_ai_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.generate_embedding.return_value = None
            mock_get_provider.return_value = mock_provider

            results = search_recipes("test query")

            assert results == []
