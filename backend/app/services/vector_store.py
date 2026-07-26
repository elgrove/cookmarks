"""Read/write access to the `recipe_embeddings` sqlite-vec virtual table.

The table sits outside the ORM (not in Alembic — see CLAUDE.md): it's a vec0
virtual table keyed by the **hyphenated** UUID string (`str(recipe.id)`), which is
how v1 wrote it and how the import script carries it across. The `recipes` table,
by contrast, stores ids un-hyphenated, so a raw join between the two silently
matches nothing. This store is the single place that bridges the two formats: every
public method takes/returns a real `uuid.UUID` and hyphenates internally, so no
caller ever touches a raw key.

KNN is a brute-force cosine scan over the 3072-d Gemini vectors (~150ms over the
full corpus); cheap enough for an on-demand lookup off the page's critical path.
"""

import struct
import uuid
from collections.abc import Iterable

import sqlite_vec
from sqlalchemy import text
from sqlalchemy.orm import Session

# v1's Gemini embedding width; the imported vectors are this wide.
EMBEDDING_DIMENSIONS = 3072


class VectorStore:
    """Thin wrapper over `recipe_embeddings`, bound to one ORM session/connection.

    Reuses the session's connection (which already has the sqlite-vec extension
    loaded by `app.db`), so there's no second connection pool. The vec0 table is
    created on demand (`IF NOT EXISTS`) so a fresh DB — a test DB, say — reads as an
    empty store rather than erroring on a missing table."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._session.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS recipe_embeddings USING vec0("
                f"recipe_id TEXT PRIMARY KEY, "
                f"embedding FLOAT[{EMBEDDING_DIMENSIONS}] distance_metric=cosine)"
            )
        )

    @staticmethod
    def _key(recipe_id: uuid.UUID) -> str:
        # The vec0 table is keyed by the hyphenated form; str(UUID) is hyphenated.
        return str(recipe_id)

    def get_embedding(self, recipe_id: uuid.UUID) -> list[float] | None:
        """The stored vector for a recipe, or None if it was never embedded."""
        row = self._session.execute(
            text("SELECT embedding FROM recipe_embeddings WHERE recipe_id = :rid"),
            {"rid": self._key(recipe_id)},
        ).first()
        if row is None:
            return None
        blob: bytes = row[0]
        count = len(blob) // 4
        return list(struct.unpack(f"{count}f", blob))

    def _knn(self, embedding: list[float], limit: int) -> list[tuple[str, float]]:
        rows = self._session.execute(
            text(
                "SELECT recipe_id, distance FROM recipe_embeddings "
                "WHERE embedding MATCH :emb ORDER BY distance LIMIT :lim"
            ),
            {"emb": sqlite_vec.serialize_float32(embedding), "lim": limit},
        ).all()
        return [(row[0], row[1]) for row in rows]

    def search(self, query_embedding: list[float], limit: int = 20) -> list[tuple[uuid.UUID, float]]:
        """The `limit` nearest recipes to an arbitrary query vector, nearest first."""
        return [(uuid.UUID(rid), dist) for rid, dist in self._knn(query_embedding, limit)]

    def search_excluding(
        self, embedding: list[float], exclude_id: uuid.UUID, limit: int = 12
    ) -> list[tuple[uuid.UUID, float]]:
        """The nearest recipes to `embedding`, with `exclude_id` dropped — a recipe is
        always its own nearest neighbour, so fetch one extra and filter it out."""
        exclude = self._key(exclude_id)
        results = [(rid, dist) for rid, dist in self._knn(embedding, limit + 1) if rid != exclude]
        return [(uuid.UUID(rid), dist) for rid, dist in results[:limit]]

    def upsert(self, recipe_id: uuid.UUID, embedding: list[float]) -> None:
        """Store (replacing any existing) one recipe's embedding."""
        key = self._key(recipe_id)
        self._session.execute(
            text("DELETE FROM recipe_embeddings WHERE recipe_id = :rid"), {"rid": key}
        )
        self._session.execute(
            text("INSERT INTO recipe_embeddings (recipe_id, embedding) VALUES (:rid, :emb)"),
            {"rid": key, "emb": sqlite_vec.serialize_float32(embedding)},
        )

    def delete(self, recipe_ids: Iterable[uuid.UUID]) -> None:
        """Drop the stored vectors for `recipe_ids`. The vec0 table has no foreign key to
        `recipes`, so deleting a recipe has to call this or its embedding lingers and
        keeps surfacing in search."""
        for recipe_id in recipe_ids:
            self._session.execute(
                text("DELETE FROM recipe_embeddings WHERE recipe_id = :rid"),
                {"rid": self._key(recipe_id)},
            )

    def embedded_ids(self) -> set[uuid.UUID]:
        """The ids of every recipe that already has a stored vector (for backfill)."""
        rows = self._session.execute(text("SELECT recipe_id FROM recipe_embeddings")).all()
        return {uuid.UUID(row[0]) for row in rows}
