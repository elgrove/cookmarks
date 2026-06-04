"""Semantic search over the seeded recipes, end to end with the offline StubProvider
(deterministic hash vectors) so it runs with no network and no API key."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import AIProvider
from app.models.recipe import Recipe
from app.services import embeddings
from app.services.ai import get_config
from app.services.ai.base import EmbedTask
from app.services.ai.stub import StubProvider


class _CountingStub(StubProvider):
    """A stub that records how many times it's asked to embed a query."""

    def __init__(self) -> None:
        super().__init__(api_key="")
        self.embed_calls = 0

    def embed(self, text: str, task: EmbedTask) -> list[float]:
        self.embed_calls += 1
        return super().embed(text, task)


def _configure_stub(session: Session) -> None:
    config = get_config(session)
    config.ai_provider = AIProvider.STUB
    session.commit()


def _seeded_recipes(session: Session) -> list[Recipe]:
    return list(
        session.scalars(
            select(Recipe).options(selectinload(Recipe.keywords)).order_by(Recipe.order)
        )
    )


def test_recipe_to_text_includes_name_keywords_ingredients(session: Session) -> None:
    recipe = session.scalar(
        select(Recipe).options(selectinload(Recipe.keywords)).where(Recipe.name == "Recipe 0")
    )
    assert recipe is not None
    rendered = embeddings.recipe_to_text(recipe)
    assert rendered.startswith("Recipe 0")
    assert "Pasta" in rendered and "Quick" in rendered
    assert "200g pasta" in rendered


def test_search_ranks_exact_text_first(session: Session) -> None:
    _configure_stub(session)
    recipes = _seeded_recipes(session)
    embeddings.embed_recipes(session, recipes)

    target = next(r for r in recipes if r.name == "Recipe 0")
    matches = embeddings.search(session, embeddings.recipe_to_text(target), limit=3)
    assert matches is not None
    assert matches[0][0] == target.id
    assert matches[0][1] == pytest.approx(0.0, abs=1e-6)


def test_search_is_unavailable_without_provider(session: Session) -> None:
    # No provider configured → None (unavailable), distinct from an empty result.
    assert embeddings.search(session, "anything", limit=5) is None


def test_query_embedding_is_cached(session: Session) -> None:
    _configure_stub(session)
    embeddings.embed_recipes(session, _seeded_recipes(session))
    provider = _CountingStub()

    first = embeddings.search(session, "warming braise", limit=3, provider=provider)
    repeat = embeddings.search(session, "warming braise", limit=3, provider=provider)
    assert provider.embed_calls == 1  # the repeat served the query vector from cache
    assert first == repeat

    embeddings.search(session, "a different dish", limit=3, provider=provider)
    assert provider.embed_calls == 2  # a new query embeds afresh


def test_backfill_embeds_only_what_is_missing(session: Session) -> None:
    _configure_stub(session)
    assert embeddings.backfill(session) == 3  # the three seeded recipes
    assert embeddings.backfill(session) == 0  # nothing left to embed


def test_endpoint_unavailable_without_provider(client: TestClient) -> None:
    body = client.get("/api/recipes/semantic", params={"q": "pasta"}).json()
    assert body == {"available": False, "query": "pasta", "total": 0, "items": []}


def test_endpoint_empty_query_is_resting(client: TestClient) -> None:
    body = client.get("/api/recipes/semantic", params={"q": "   "}).json()
    assert body == {"available": True, "query": "", "total": 0, "items": []}


def test_endpoint_ranks_and_shapes_results(client: TestClient, session: Session) -> None:
    _configure_stub(session)
    recipes = _seeded_recipes(session)
    embeddings.embed_recipes(session, recipes)
    session.commit()
    target = next(r for r in recipes if r.name == "Recipe 0")

    body = client.get(
        "/api/recipes/semantic",
        params={"q": embeddings.recipe_to_text(target), "limit": 3},
    ).json()

    assert body["available"] is True
    assert body["total"] == 3
    assert body["items"][0]["id"] == str(target.id)
    assert body["items"][0]["name"] == "Recipe 0"
    assert set(body["items"][0].keys()) == {
        "id",
        "name",
        "book_id",
        "book_title",
        "book_author",
        "keywords",
        "distance",
    }
    # Distances are non-decreasing — closest first.
    distances = [item["distance"] for item in body["items"]]
    assert distances == sorted(distances)
