from fastapi.testclient import TestClient

FEATURE_KEYS = {"id", "title", "author", "description", "recipe_count", "has_cover"}


def test_home_shape(client: TestClient) -> None:
    resp = client.get("/api/home")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["stats"].keys()) == {"books", "recipes", "keywords"}
    assert body["stats"] == {"books": 2, "recipes": 3, "keywords": 2}


def test_home_book_of_the_day(client: TestClient) -> None:
    feature = client.get("/api/home").json()["book_of_the_day"]
    assert feature is not None
    assert set(feature.keys()) == FEATURE_KEYS
    # Only the recipe-bearing book is eligible to be featured.
    assert feature["title"] == "With Recipes"
    assert feature["recipe_count"] == 3
    assert feature["has_cover"] is False
