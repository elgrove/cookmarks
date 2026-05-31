import uuid

from fastapi.testclient import TestClient

EXPECTED_KEYS = {"id", "title", "author", "recipe_count", "has_cover", "pubdate"}


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
