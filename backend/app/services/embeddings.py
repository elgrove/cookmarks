"""Recipe embedding generation — the AI layer over the vec0 vector store.

`app/services/vector_store.py` owns the `recipe_embeddings` vec0 table (storage and
the cosine KNN, plus the hyphenated/un-hyphenated id bridging). This module is the
*generation* side that sits on top of it: it turns a recipe into text, calls the AI
provider to embed it, and stores the result via `VectorStore` — and at query time
embeds the search text and asks `VectorStore` for the nearest recipes.

Keeping the two apart means there's exactly one place that touches the vec0 table
(VectorStore), while the provider/embedding concerns live here.
"""

import logging
import uuid
from collections import OrderedDict

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.recipe import Recipe
from app.services.ai import get_ai_provider
from app.services.ai.base import AIProvider, EmbedTask
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Recipes per embedding API call. Generous — the provider batches internally; the
# cap just bounds request size and memory for a full-library backfill.
EMBED_BATCH_SIZE = 100

# Query embeddings are deterministic, so cache them in-process: a repeated query
# (back-navigation, re-pressing AI search, a shared URL reopened) then skips the
# provider round-trip. Keyed by (embedding model, query) so it stays correct if the
# model changes; the vec0 search still re-runs against live data, so results never go
# stale. Module-global like the other read caches — the test suite clears it.
_QUERY_EMBED_CACHE: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
_QUERY_EMBED_CACHE_MAX = 256


def _clear_query_embed_cache() -> None:
    _QUERY_EMBED_CACHE.clear()


def _embed_query(provider: AIProvider, query: str) -> list[float]:
    """Embed a search query, served from the in-process cache on a repeat."""
    key = (provider.embedding_model or provider.name, query)
    cached = _QUERY_EMBED_CACHE.get(key)
    if cached is not None:
        _QUERY_EMBED_CACHE.move_to_end(key)
        return cached
    vector = provider.embed(query, EmbedTask.QUERY)
    _QUERY_EMBED_CACHE[key] = vector
    _QUERY_EMBED_CACHE.move_to_end(key)
    while len(_QUERY_EMBED_CACHE) > _QUERY_EMBED_CACHE_MAX:
        _QUERY_EMBED_CACHE.popitem(last=False)
    return vector


def recipe_to_text(recipe: Recipe) -> str:
    """The text a recipe is embedded from: name, then its keywords, then its
    ingredients — what a dish *is* and what's *in* it (method/description excluded,
    matching the vectors already imported from v1)."""
    parts = [recipe.name]
    if recipe.keywords:
        parts.append(", ".join(k.name for k in recipe.keywords))
    if recipe.ingredients_verbatim:
        parts.append(", ".join(line.text for line in recipe.ingredients_verbatim))
    return ". ".join(parts)


def embed_recipes(
    session: Session, recipes: list[Recipe], provider: AIProvider | None = None
) -> int:
    """Embed and store vectors for `recipes` via the VectorStore. A no-op (returns 0)
    when no embedding-capable provider is configured, so extraction still completes
    without one. Does not commit — the caller owns the transaction."""
    provider = provider or get_ai_provider(session)
    if provider is None or not provider.supports_embeddings:
        logger.warning("No embedding-capable AI provider; skipping %d recipe(s)", len(recipes))
        return 0

    store = VectorStore(session)
    count = 0
    for start in range(0, len(recipes), EMBED_BATCH_SIZE):
        batch = recipes[start : start + EMBED_BATCH_SIZE]
        vectors = provider.embed_batch([recipe_to_text(r) for r in batch], EmbedTask.DOCUMENT)
        for recipe, vector in zip(batch, vectors, strict=True):
            store.upsert(recipe.id, vector)
            count += 1
    logger.info("Embedded %d recipe(s)", count)
    return count


def search(
    session: Session, query: str, limit: int, provider: AIProvider | None = None
) -> list[tuple[uuid.UUID, float]] | None:
    """Nearest recipes to `query` by cosine distance, closest first — (recipe_id,
    distance). Returns None when semantic search is unavailable (no embedding-capable
    provider), distinct from an empty result set."""
    provider = provider or get_ai_provider(session)
    if provider is None or not provider.supports_embeddings:
        return None
    query_vector = _embed_query(provider, query)
    return VectorStore(session).search(query_vector, limit)


def backfill(session: Session, provider: AIProvider | None = None) -> int:
    """Embed every recipe that has no stored vector. Commits. Returns how many were
    embedded. Fills gaps after import or extractions that ran without a provider."""
    provider = provider or get_ai_provider(session)
    if provider is None or not provider.supports_embeddings:
        logger.warning("No embedding-capable AI provider; nothing to backfill")
        return 0
    embedded = VectorStore(session).embedded_ids()
    recipes = [
        recipe
        for recipe in session.scalars(
            select(Recipe).options(
                selectinload(Recipe.keywords), selectinload(Recipe.ingredients)
            )
        )
        if recipe.id not in embedded
    ]
    count = embed_recipes(session, recipes, provider)
    session.commit()
    return count
