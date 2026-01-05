import logging
import sqlite3
from pathlib import Path

import sqlite_vec

from core.models import Recipe
from core.services.ai import GeminiProvider, get_ai_provider

logger = logging.getLogger(__name__)


def recipe_to_text(recipe: Recipe) -> str:
    parts = [recipe.name]

    keywords = recipe.keywords.values_list("name", flat=True)
    if keywords:
        parts.append(f"Keywords: {', '.join(keywords)}")

    if recipe.ingredients:
        parts.append(f"Ingredients: {chr(10).join(recipe.ingredients)}")

    return "\n\n".join(parts)


def get_embedding_provider() -> GeminiProvider:
    provider = get_ai_provider()
    if provider is None:
        raise ValueError("No AI provider configured")
    if not isinstance(provider, GeminiProvider):
        raise ValueError("Embeddings require Gemini provider")
    return provider


class VectorStore:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            from django.conf import settings

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
                    embedding FLOAT[{GeminiProvider.EMBEDDING_DIMENSIONS}]
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


def generate_recipe_embedding(recipe: Recipe) -> None:
    provider = get_embedding_provider()
    text = recipe_to_text(recipe)
    embedding = provider.generate_embedding(text)
    store = VectorStore()
    store.upsert(str(recipe.id), embedding)
    logger.info(f"Generated embedding for recipe: {recipe.name}")


def search_recipes(query: str, limit: int = 20) -> list[Recipe]:
    provider = get_embedding_provider()
    query_embedding = provider.generate_embedding(query, task_type="RETRIEVAL_QUERY")
    store = VectorStore()

    results = store.search(query_embedding, limit=limit)

    recipe_ids = [r[0] for r in results]
    recipes_by_id = {
        str(r.id): r for r in Recipe.objects.filter(id__in=recipe_ids).select_related("book")
    }

    return [recipes_by_id[rid] for rid in recipe_ids if rid in recipes_by_id]
