import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CalibreExclusion, Recipe, RecipeListItem, User
from app.services.users import create_user
from app.services.vector_store import EMBEDDING_DIMENSIONS, VectorStore

EXPECTED_KEYS = {
    "id",
    "title",
    "author",
    "recipe_count",
    "seen_count",
    "has_cover",
    "pubdate",
    "keywords",
}
DETAIL_KEYS = {
    "id",
    "title",
    "author",
    "isbn",
    "pubdate",
    "description",
    "recipe_count",
    "seen_count",
    "has_cover",
    "has_epub",
    "added",
    "keywords",
    "recipes",
}


def test_list_books_shape(client: TestClient) -> None:
    resp = client.get("/api/books")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2
    for item in body:
        assert set(item.keys()) == EXPECTED_KEYS


def test_recipe_counts(client: TestClient) -> None:
    books = {b["title"]: b for b in client.get("/api/books").json()}
    assert books["With Recipes"]["recipe_count"] == 3
    assert books["No Recipes Yet"]["recipe_count"] == 0


def test_default_sort_is_recent_first(client: TestClient) -> None:
    titles = [b["title"] for b in client.get("/api/books").json()]
    # created_at DESC: the 2021 book precedes the 2020 book.
    assert titles == ["No Recipes Yet", "With Recipes"]


def test_has_cover_false_for_missing_files(client: TestClient) -> None:
    assert all(b["has_cover"] is False for b in client.get("/api/books").json())


def test_cover_404_when_file_missing(client: TestClient) -> None:
    book_id = client.get("/api/books").json()[0]["id"]
    assert client.get(f"/api/books/{book_id}/cover").status_code == 404


def test_cover_404_for_unknown_book(client: TestClient) -> None:
    assert client.get(f"/api/books/{uuid.uuid4()}/cover").status_code == 404


def _book_id(client: TestClient, title: str) -> str:
    return next(b["id"] for b in client.get("/api/books").json() if b["title"] == title)


def test_book_detail_shape(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    resp = client.get(f"/api/books/{book_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == DETAIL_KEYS
    assert body["title"] == "With Recipes"
    assert body["recipe_count"] == 3


def test_book_detail_recipes_capped_and_shaped(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    recipes = client.get(f"/api/books/{book_id}").json()["recipes"]
    assert 0 < len(recipes) <= 10
    for row in recipes:
        assert set(row.keys()) == {"id", "name", "keywords", "is_seen"}
        assert isinstance(row["keywords"], list)
    # The seeded "Recipe 0" carries two keywords, sorted.
    keyworded = next((r for r in recipes if r["name"] == "Recipe 0"), None)
    if keyworded is not None:
        assert keyworded["keywords"] == ["Pasta", "Quick"]


def test_book_detail_empty_recipes(client: TestClient) -> None:
    book_id = _book_id(client, "No Recipes Yet")
    body = client.get(f"/api/books/{book_id}").json()
    assert body["recipe_count"] == 0
    assert body["recipes"] == []


def test_seen_counts_report_recipes_opened(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    recipes = client.get(f"/api/books/{book_id}").json()["recipes"]
    for recipe in recipes[:2]:
        client.post(f"/api/recipes/{recipe['id']}/seen")
    # Re-opening one of them doesn't double-count: the percentage counts distinct recipes.
    client.post(f"/api/recipes/{recipes[0]['id']}/seen")

    assert client.get(f"/api/books/{book_id}").json()["seen_count"] == 2
    summaries = {b["title"]: b for b in client.get("/api/books").json()}
    assert summaries["With Recipes"]["seen_count"] == 2
    assert summaries["No Recipes Yet"]["seen_count"] == 0


def test_seen_counts_are_per_user(
    client: TestClient, session: Session, act_as: Callable[[str], User]
) -> None:
    """Each account sees its own reading and nothing of anyone else's."""
    create_user(session, "other", "other-password")

    book_id = _book_id(client, "With Recipes")
    recipes = client.get(f"/api/books/{book_id}").json()["recipes"]
    for recipe in recipes[:2]:
        client.post(f"/api/recipes/{recipe['id']}/seen")

    act_as("other")
    assert client.get(f"/api/books/{book_id}").json()["seen_count"] == 0
    client.post(f"/api/recipes/{recipes[0]['id']}/seen")
    assert client.get(f"/api/books/{book_id}").json()["seen_count"] == 1

    # The first account's figure is untouched by the second's reading.
    act_as("tester")
    assert client.get(f"/api/books/{book_id}").json()["seen_count"] == 2


def test_recipe_rows_report_their_own_read_state(client: TestClient) -> None:
    """The index marks *which* recipes make up the percentage, not just how many."""
    book_id = _book_id(client, "With Recipes")
    recipes = client.get(f"/api/books/{book_id}").json()["recipes"]
    assert all(r["is_seen"] is False for r in recipes)

    client.post(f"/api/recipes/{recipes[0]['id']}/seen")
    rows = {r["id"]: r for r in client.get(f"/api/books/{book_id}").json()["recipes"]}
    assert rows[recipes[0]["id"]]["is_seen"] is True
    assert all(r["is_seen"] is False for rid, r in rows.items() if rid != recipes[0]["id"])


def test_mark_book_read_and_reset(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    total = client.get(f"/api/books/{book_id}").json()["recipe_count"]

    marked = client.post(f"/api/books/{book_id}/seen")
    assert marked.status_code == 200
    assert marked.json() == {"recipe_count": total, "seen_count": total}
    assert all(r["is_seen"] for r in client.get(f"/api/books/{book_id}").json()["recipes"])

    # Marking a book already read changes nothing — no duplicate view rows.
    assert client.post(f"/api/books/{book_id}/seen").json()["seen_count"] == total

    reset = client.delete(f"/api/books/{book_id}/seen")
    assert reset.status_code == 200
    assert reset.json() == {"recipe_count": total, "seen_count": 0}
    assert client.get(f"/api/books/{book_id}").json()["seen_count"] == 0


def test_mark_book_read_keeps_an_existing_sitting_count(client: TestClient) -> None:
    """A recipe already read isn't re-read by marking the book: its record stands."""
    book_id = _book_id(client, "With Recipes")
    recipe_id = client.get(f"/api/books/{book_id}").json()["recipes"][0]["id"]
    first = client.post(f"/api/recipes/{recipe_id}/seen").json()

    client.post(f"/api/books/{book_id}/seen")
    after = client.post(f"/api/recipes/{recipe_id}/seen").json()
    assert after["first_viewed_at"] == first["first_viewed_at"]


def test_mark_book_read_is_per_user(
    client: TestClient, session: Session, act_as: Callable[[str], User]
) -> None:
    create_user(session, "other", "other-password")
    book_id = _book_id(client, "With Recipes")
    client.post(f"/api/books/{book_id}/seen")

    act_as("other")
    assert client.get(f"/api/books/{book_id}").json()["seen_count"] == 0
    # Resetting one account's progress leaves the other's reading intact.
    client.delete(f"/api/books/{book_id}/seen")
    act_as("tester")
    body = client.get(f"/api/books/{book_id}").json()
    assert body["seen_count"] == body["recipe_count"]


def test_book_read_state_404s_for_unknown_book(client: TestClient) -> None:
    assert client.post(f"/api/books/{uuid.uuid4()}/seen").status_code == 404
    assert client.delete(f"/api/books/{uuid.uuid4()}/seen").status_code == 404


def test_book_detail_404_for_unknown_book(client: TestClient) -> None:
    assert client.get(f"/api/books/{uuid.uuid4()}").status_code == 404


@pytest.fixture
def library_with_epub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temp Calibre root holding an .epub for the seeded "With Recipes" book."""
    book_dir = tmp_path / "Author One" / "With Recipes (1)"
    book_dir.mkdir(parents=True)
    (book_dir / "book.epub").write_bytes(b"PK\x03\x04 not a real epub, just bytes")
    monkeypatch.setattr(settings, "calibre_library_path", tmp_path)
    return tmp_path


def test_has_epub_false_without_files(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    assert client.get(f"/api/books/{book_id}").json()["has_epub"] is False


def test_has_epub_true_when_present(client: TestClient, library_with_epub: Path) -> None:
    book_id = _book_id(client, "With Recipes")
    assert client.get(f"/api/books/{book_id}").json()["has_epub"] is True


def test_epub_served_when_present(client: TestClient, library_with_epub: Path) -> None:
    book_id = _book_id(client, "With Recipes")
    resp = client.get(f"/api/books/{book_id}/epub")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/epub+zip"


def test_epub_404_when_file_missing(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    assert client.get(f"/api/books/{book_id}/epub").status_code == 404


def test_epub_404_for_unknown_book(client: TestClient) -> None:
    assert client.get(f"/api/books/{uuid.uuid4()}/epub").status_code == 404


def test_recipe_index_lists_all_in_order(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    idx = client.get(f"/api/books/{book_id}/recipe-index").json()
    assert [e["name"] for e in idx] == ["Recipe 0", "Recipe 1", "Recipe 2"]
    assert all(e["is_favourite"] is False for e in idx)
    assert set(idx[0].keys()) == {"id", "name", "is_favourite"}


def test_recipe_index_reflects_favourite(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    rid = client.get(f"/api/books/{book_id}/recipe-index").json()[0]["id"]
    assert client.post(f"/api/recipes/{rid}/favourite").json()["is_favourite"] is True
    idx = {e["id"]: e["is_favourite"] for e in client.get(f"/api/books/{book_id}/recipe-index").json()}
    assert idx[rid] is True


def test_recipe_index_empty_for_bookless(client: TestClient) -> None:
    book_id = _book_id(client, "No Recipes Yet")
    assert client.get(f"/api/books/{book_id}/recipe-index").json() == []


def test_recipe_index_404_for_unknown_book(client: TestClient) -> None:
    assert client.get(f"/api/books/{uuid.uuid4()}/recipe-index").status_code == 404


def test_delete_book_removes_recipes_and_list_items(
    client: TestClient, session: Session
) -> None:
    book_id = _book_id(client, "With Recipes")
    rid = client.get(f"/api/books/{book_id}/recipe-index").json()[0]["id"]
    client.post(f"/api/recipes/{rid}/favourite")
    store = VectorStore(session)
    store.upsert(uuid.UUID(rid), [0.1] * EMBEDDING_DIMENSIONS)

    assert client.delete(f"/api/books/{book_id}").status_code == 204

    assert client.get(f"/api/books/{book_id}").status_code == 404
    assert session.get(Recipe, uuid.UUID(rid)) is None
    assert session.scalars(select(RecipeListItem)).all() == []
    assert VectorStore(session).embedded_ids() == set()


def test_delete_book_404_for_unknown_book(client: TestClient) -> None:
    assert client.delete(f"/api/books/{uuid.uuid4()}").status_code == 404


def test_delete_book_without_exclude_records_no_exclusion(
    client: TestClient, session: Session
) -> None:
    assert client.delete(f"/api/books/{_book_id(client, 'With Recipes')}").status_code == 204
    assert session.scalars(select(CalibreExclusion)).all() == []


def test_delete_book_with_exclude_records_the_calibre_id(
    client: TestClient, session: Session
) -> None:
    book_id = _book_id(client, "With Recipes")
    assert client.delete(f"/api/books/{book_id}?exclude=true").status_code == 204

    exclusion = session.scalars(select(CalibreExclusion)).one()
    assert exclusion.calibre_id == 1
    assert exclusion.title == "With Recipes"
