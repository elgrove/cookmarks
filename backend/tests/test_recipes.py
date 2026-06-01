from fastapi.testclient import TestClient


def _book_id(client: TestClient, title: str) -> str:
    books = {b["title"]: b for b in client.get("/api/books").json()}
    return books[title]["id"]


def test_empty_until_a_query(client: TestClient) -> None:
    # No query and no filters → the resting (empty) state, not a full dump.
    body = client.get("/api/recipes").json()
    assert body == {"total": 0, "items": [], "facets": []}


def test_search_matches_name(client: TestClient) -> None:
    body = client.get("/api/recipes", params={"q": "recipe"}).json()
    assert body["total"] == 3
    assert {r["name"] for r in body["items"]} == {"Recipe 0", "Recipe 1", "Recipe 2"}


def test_search_matches_ingredients(client: TestClient) -> None:
    # "anchovy" only appears in Recipe 0's ingredient list.
    body = client.get("/api/recipes", params={"q": "anchovy"}).json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Recipe 0"


def test_search_matches_book_author(client: TestClient) -> None:
    body = client.get("/api/recipes", params={"q": "author one"}).json()
    assert body["total"] == 3


def test_keyword_filter(client: TestClient) -> None:
    body = client.get("/api/recipes", params={"keyword": "Pasta"}).json()
    assert body["total"] == 1
    assert body["items"][0]["keywords"] == ["Pasta", "Quick"]


def test_keyword_filter_unknown_is_empty(client: TestClient) -> None:
    body = client.get("/api/recipes", params={"keyword": "nope"}).json()
    assert body == {"total": 0, "items": [], "facets": []}


def test_book_filter(client: TestClient) -> None:
    with_recipes = _book_id(client, "With Recipes")
    without = _book_id(client, "No Recipes Yet")
    assert client.get("/api/recipes", params={"book_id": with_recipes}).json()["total"] == 3
    assert client.get("/api/recipes", params={"book_id": without}).json()["total"] == 0


def test_author_filter(client: TestClient) -> None:
    assert client.get("/api/recipes", params={"author": "Author One"}).json()["total"] == 3
    assert client.get("/api/recipes", params={"author": "Author Two"}).json()["total"] == 0


def test_query_and_filter_are_anded(client: TestClient) -> None:
    # "recipe" matches all three by name; the keyword narrows to Recipe 0.
    both = client.get("/api/recipes", params={"q": "recipe", "keyword": "Pasta"}).json()
    assert both["total"] == 1
    assert both["items"][0]["name"] == "Recipe 0"


def test_sort_name(client: TestClient) -> None:
    items = client.get("/api/recipes", params={"q": "recipe", "sort": "name"}).json()["items"]
    assert [r["name"] for r in items] == ["Recipe 0", "Recipe 1", "Recipe 2"]


def test_default_sort_is_random(client: TestClient) -> None:
    # The default returns the full set; order is the shuffle, so assert membership.
    body = client.get("/api/recipes", params={"q": "recipe"}).json()
    assert body["total"] == 3
    assert {r["name"] for r in body["items"]} == {"Recipe 0", "Recipe 1", "Recipe 2"}


def test_random_sort_is_stable_per_seed(client: TestClient) -> None:
    # Same seed → same ordering (so pagination is coherent); the full set returns.
    params = {"q": "recipe", "sort": "random", "seed": 12345}
    first = [r["name"] for r in client.get("/api/recipes", params=params).json()["items"]]
    again = [r["name"] for r in client.get("/api/recipes", params=params).json()["items"]]
    assert first == again
    assert set(first) == {"Recipe 0", "Recipe 1", "Recipe 2"}


def test_pagination(client: TestClient) -> None:
    base = {"q": "recipe", "sort": "name", "limit": 2}
    first = client.get("/api/recipes", params={**base, "offset": 0}).json()
    assert first["total"] == 3
    assert [r["name"] for r in first["items"]] == ["Recipe 0", "Recipe 1"]
    second = client.get("/api/recipes", params={**base, "offset": 2}).json()
    assert second["total"] == 3
    assert [r["name"] for r in second["items"]] == ["Recipe 2"]


def test_facets_rank_cooccurring_keywords(client: TestClient) -> None:
    # "recipe" matches all three; only Recipe 0 carries keywords, so the facets
    # are its keywords, counted over the matching set.
    body = client.get("/api/recipes", params={"q": "recipe"}).json()
    assert body["facets"] == [
        {"name": "Pasta", "recipe_count": 1},
        {"name": "Quick", "recipe_count": 1},
    ]


def test_facets_exclude_selected_keywords(client: TestClient) -> None:
    # With Pasta selected, the facet list offers what narrows *further* — Quick —
    # and drops the already-chosen Pasta.
    body = client.get("/api/recipes", params={"keyword": "Pasta"}).json()
    assert body["facets"] == [{"name": "Quick", "recipe_count": 1}]


def test_facets_respect_the_query(client: TestClient) -> None:
    # "anchovy" narrows to Recipe 0 alone; the facets are that recipe's keywords.
    body = client.get("/api/recipes", params={"q": "anchovy"}).json()
    assert body["facets"] == [
        {"name": "Pasta", "recipe_count": 1},
        {"name": "Quick", "recipe_count": 1},
    ]


def test_keywords_endpoint(client: TestClient) -> None:
    body = client.get("/api/keywords").json()
    assert body == [
        {"name": "Pasta", "recipe_count": 1},
        {"name": "Quick", "recipe_count": 1},
    ]
