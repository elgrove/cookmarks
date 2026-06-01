import uuid

from fastapi.testclient import TestClient

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
