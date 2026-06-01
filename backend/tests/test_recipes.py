import uuid

from fastapi.testclient import TestClient

RECIPE_KEYS = {
    "id",
    "book_id",
    "book_title",
    "book_author",
    "book_has_cover",
    "name",
    "description",
    "ingredients",
    "instructions",
    "yields",
    "keywords",
    "has_image",
}


def _recipe_id(client: TestClient, name: str = "Recipe 0") -> str:
    book = next(b for b in client.get("/api/books").json() if b["title"] == "With Recipes")
    recipes = client.get(f"/api/books/{book['id']}").json()["recipes"]
    return next(r["id"] for r in recipes if r["name"] == name)


def test_recipe_detail_shape(client: TestClient) -> None:
    resp = client.get(f"/api/recipes/{_recipe_id(client)}")
    assert resp.status_code == 200
    assert set(resp.json().keys()) == RECIPE_KEYS


def test_recipe_detail_content(client: TestClient) -> None:
    body = client.get(f"/api/recipes/{_recipe_id(client)}").json()
    assert body["name"] == "Recipe 0"
    assert body["description"] == "A quick weeknight pasta."
    assert body["yields"] == "Serves 2"
    assert body["ingredients"] == ["200g pasta", "2 tbsp olive oil"]
    assert body["instructions"] == ["Boil the pasta.", "Toss with the oil and serve."]
    # Keywords come back sorted by name.
    assert body["keywords"] == ["Pasta", "Quick"]
    assert body["has_image"] is True


def test_recipe_detail_provenance(client: TestClient) -> None:
    body = client.get(f"/api/recipes/{_recipe_id(client)}").json()
    book = next(b for b in client.get("/api/books").json() if b["title"] == "With Recipes")
    assert body["book_id"] == book["id"]
    assert body["book_title"] == "With Recipes"
    assert body["book_author"] == "Author One"
    assert body["book_has_cover"] is False


def test_recipe_optional_fields_when_absent(client: TestClient) -> None:
    # "Recipe 1" carries no description/yields/image/keywords.
    body = client.get(f"/api/recipes/{_recipe_id(client, 'Recipe 1')}").json()
    assert body["description"] is None
    assert body["yields"] is None
    assert body["has_image"] is False
    assert body["ingredients"] == []
    assert body["instructions"] == []
    assert body["keywords"] == []


def test_recipe_404_for_unknown_id(client: TestClient) -> None:
    assert client.get(f"/api/recipes/{uuid.uuid4()}").status_code == 404
