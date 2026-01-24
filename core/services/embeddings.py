import logging
import sqlite3
import struct
from pathlib import Path

import sqlite_vec
from django.conf import settings

from core.models import Recipe
from core.services.ai import GeminiProvider, get_ai_provider

logger = logging.getLogger(__name__)


def recipe_to_text(recipe: Recipe) -> str:
    parts = [recipe.name]

    keywords = recipe.keywords.values_list("name", flat=True)
    if keywords:
        parts.append(", ".join(keywords))

    if recipe.ingredients:
        parts.append(", ".join(recipe.ingredients))

    return ". ".join(parts)


class VectorStore:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = settings.DATABASES["default"]["NAME"]
        self.db_path = str(db_path)
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return conn

    def _ensure_tables(self):
        conn = self._get_connection()
        try:
            conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS recipe_embeddings USING vec0(
                    recipe_id TEXT PRIMARY KEY,
                    embedding FLOAT[{GeminiProvider.EMBEDDING_DIMENSIONS}] distance_metric=cosine
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def upsert(self, recipe_id: str, embedding: list[float]):
        conn = self._get_connection()
        try:
            conn.execute("DELETE FROM recipe_embeddings WHERE recipe_id = ?", (recipe_id,))
            conn.execute(
                "INSERT INTO recipe_embeddings (recipe_id, embedding) VALUES (?, ?)",
                (recipe_id, sqlite_vec.serialize_float32(embedding)),
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_batch(self, items: list[tuple[str, list[float]]]):
        conn = self._get_connection()
        try:
            recipe_ids = [item[0] for item in items]
            conn.execute(
                f"DELETE FROM recipe_embeddings WHERE recipe_id IN ({','.join('?' * len(recipe_ids))})",
                recipe_ids,
            )
            conn.executemany(
                "INSERT INTO recipe_embeddings (recipe_id, embedding) VALUES (?, ?)",
                [(rid, sqlite_vec.serialize_float32(emb)) for rid, emb in items],
            )
            conn.commit()
        finally:
            conn.close()

    def search(self, query_embedding: list[float], limit: int = 20) -> list[tuple[str, float]]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT recipe_id, distance
                FROM recipe_embeddings
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT ?
                """,
                (sqlite_vec.serialize_float32(query_embedding), limit),
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def get_embedding(self, recipe_id: str) -> list[float] | None:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT embedding FROM recipe_embeddings WHERE recipe_id = ?",
                (recipe_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            blob = row[0]
            num_floats = len(blob) // 4
            return list(struct.unpack(f"{num_floats}f", blob))
        finally:
            conn.close()

    def search_excluding(
        self, query_embedding: list[float], exclude_id: str, limit: int = 20
    ) -> list[tuple[str, float]]:
        results = self.search(query_embedding, limit=limit + 1)
        return [(rid, dist) for rid, dist in results if rid != exclude_id][:limit]


def generate_recipe_embedding(recipe: Recipe) -> None:
    provider = get_ai_provider()
    if not provider:
        logger.warning("No AI provider configured")
        return

    text = recipe_to_text(recipe)
    embedding = provider.generate_embedding(text, "RETRIEVAL_DOCUMENT")
    if not embedding:
        return

    store = VectorStore()
    store.upsert(str(recipe.id), embedding)
    logger.info(f"Generated embedding for recipe: {recipe.name}")


EMBEDDING_BATCH_SIZE = 6


def generate_recipe_embeddings_batch(recipes: list[Recipe]) -> None:
    if not recipes:
        return

    provider = get_ai_provider()
    if not provider:
        logger.warning("No AI provider configured")
        return

    store = VectorStore()

    all_items = []
    for i in range(0, len(recipes), EMBEDDING_BATCH_SIZE):
        batch = recipes[i : i + EMBEDDING_BATCH_SIZE]
        texts = [recipe_to_text(recipe) for recipe in batch]
        embeddings = provider.generate_embeddings_batch(texts, "RETRIEVAL_DOCUMENT")
        if not embeddings:
            continue

        items = [
            (str(recipe.id), embedding) for recipe, embedding in zip(batch, embeddings, strict=True)
        ]
        all_items.extend(items)

    if all_items:
        store.upsert_batch(all_items)

    recipe_names = ", ".join([r.name for r in recipes[:3]])
    suffix = "..." if len(recipes) > 3 else ""
    logger.info(f"Generated embeddings for {len(recipes)} recipes: {recipe_names}{suffix}")


def search_recipes(query: str, limit: int = 20) -> list[Recipe]:
    provider = get_ai_provider()
    if not provider:
        logger.warning("No AI provider configured")
        return []

    query_embedding = provider.generate_embedding(query, "RETRIEVAL_QUERY")
    if not query_embedding:
        return []

    store = VectorStore()

    results = store.search(query_embedding, limit=limit)

    recipe_ids = [r[0] for r in results]
    recipes_by_id = {
        str(r.id): r for r in Recipe.objects.filter(id__in=recipe_ids).select_related("book")
    }

    return [recipes_by_id[rid] for rid in recipe_ids if rid in recipes_by_id]


def find_similar_recipes(recipe: Recipe, limit: int = 8) -> list[tuple[Recipe, float]]:
    store = VectorStore()
    embedding = store.get_embedding(str(recipe.id))
    if not embedding:
        logger.debug(f"No embedding found for recipe: {recipe.name}")
        return []

    results = store.search_excluding(embedding, str(recipe.id), limit=limit)

    recipe_ids = [r[0] for r in results]
    distances = {r[0]: r[1] for r in results}
    recipes_by_id = {
        str(r.id): r for r in Recipe.objects.filter(id__in=recipe_ids).select_related("book")
    }

    return [(recipes_by_id[rid], distances[rid]) for rid in recipe_ids if rid in recipes_by_id]
