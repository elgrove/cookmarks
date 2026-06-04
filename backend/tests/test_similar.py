"""Similar-recipes endpoint: the embedding KNN path, the shared-keyword fallback,
and the edges (self-exclusion, no match, unknown recipe).

The seed (conftest) ships three recipes in "With Recipes" and no embeddings, so the
vector path is exercised by upserting vectors through the `VectorStore`, and the
fallback by leaving them absent.
"""

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Book, Keyword, Recipe
from app.services.vector_store import EMBEDDING_DIMENSIONS, VectorStore

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contract"


def _example() -> dict[str, Any]:
    return json.loads((CONTRACT_DIR / "similar.example.json").read_text())


def _recipes(session: Session) -> tuple[Recipe, Recipe, Recipe]:
    rows = list(
        session.scalars(
            select(Recipe)
            .join(Book, Recipe.book_id == Book.id)
            .where(Book.title == "With Recipes")
            .order_by(Recipe.order)
        ).all()
    )
    return rows[0], rows[1], rows[2]


def _vec(*nonzero: tuple[int, float]) -> list[float]:
    """A 3072-d vector with a few axes set — enough to fix a KNN ordering."""
    v = [0.0] * EMBEDDING_DIMENSIONS
    for idx, val in nonzero:
        v[idx] = val
    return v


def _seed_embeddings(session: Session) -> tuple[Recipe, Recipe, Recipe]:
    # r1 points almost exactly along r0; r2 is orthogonal — so r0's neighbours are
    # r1 then r2, unambiguously.
    r0, r1, r2 = _recipes(session)
    store = VectorStore(session)
    store.upsert(r0.id, _vec((0, 1.0)))
    store.upsert(r1.id, _vec((0, 1.0), (1, 0.5)))
    store.upsert(r2.id, _vec((1, 1.0)))
    session.commit()
    return r0, r1, r2


def test_similar_vector_path_orders_by_distance_and_excludes_self(
    client: TestClient, session: Session
) -> None:
    r0, r1, r2 = _seed_embeddings(session)
    body = client.get(f"/api/recipes/{r0.id}/similar").json()
    assert body["basis"] == "vector"
    ids = [item["id"] for item in body["items"]]
    assert str(r0.id) not in ids
    assert ids == [str(r1.id), str(r2.id)]


def test_similar_respects_limit(client: TestClient, session: Session) -> None:
    r0, _, _ = _seed_embeddings(session)
    body = client.get(f"/api/recipes/{r0.id}/similar", params={"limit": 1}).json()
    assert len(body["items"]) == 1


def test_similar_keyword_fallback_when_no_embedding(
    client: TestClient, session: Session
) -> None:
    r0, r1, _ = _recipes(session)
    # r0 carries "Pasta"; share it with r1 so the fallback links the two.
    pasta = session.scalar(select(Keyword).where(Keyword.name == "Pasta"))
    assert pasta is not None
    r1.keywords.append(pasta)
    session.commit()

    body = client.get(f"/api/recipes/{r0.id}/similar").json()
    assert body["basis"] == "keyword"
    assert [item["id"] for item in body["items"]] == [str(r1.id)]


def test_similar_empty_when_no_embedding_and_no_keywords(
    client: TestClient, session: Session
) -> None:
    # r2 has neither an embedding nor keywords: the fallback finds nothing.
    _, _, r2 = _recipes(session)
    body = client.get(f"/api/recipes/{r2.id}/similar").json()
    assert body["basis"] == "keyword"
    assert body["items"] == []


def test_similar_unknown_recipe_404(client: TestClient) -> None:
    assert client.get(f"/api/recipes/{uuid.uuid4()}/similar").status_code == 404


def test_similar_endpoint_keys_match_contract(client: TestClient, session: Session) -> None:
    example = _example()
    r0, _, _ = _seed_embeddings(session)
    body = client.get(f"/api/recipes/{r0.id}/similar").json()
    assert set(body.keys()) == set(example.keys())
    assert set(body["items"][0].keys()) == set(example["items"][0].keys())
