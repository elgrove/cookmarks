import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings

EXPECTED_KEYS = {"id", "title", "author", "recipe_count", "has_cover", "pubdate"}
DETAIL_KEYS = {
    "id",
    "title",
    "author",
    "isbn",
    "pubdate",
    "description",
    "recipe_count",
    "has_cover",
    "has_epub",
    "added",
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
        assert set(row.keys()) == {"id", "name", "keywords"}
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
