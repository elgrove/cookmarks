"""The lists API: the default Favourites, custom named lists, membership and the
favourite toggle. The DB is reseeded per test (conftest) so each starts clean."""

from fastapi.testclient import TestClient


def _recipe_ids(client: TestClient) -> list[str]:
    book = next(b for b in client.get("/api/books").json() if b["title"] == "With Recipes")
    return [r["id"] for r in client.get(f"/api/books/{book['id']}").json()["recipes"]]


def _favourites(client: TestClient) -> dict:
    return next(lst for lst in client.get("/api/lists").json() if lst["is_default"])


def test_lists_seeds_favourites(client: TestClient) -> None:
    lists = client.get("/api/lists").json()
    favourites = [lst for lst in lists if lst["is_default"]]
    assert len(favourites) == 1
    assert favourites[0]["name"] == "Favourites"
    # The default is pinned first.
    assert lists[0]["is_default"] is True


def test_create_list(client: TestClient) -> None:
    created = client.post("/api/lists", json={"name": "  Weeknight  "})
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Weeknight"  # trimmed
    assert body["is_default"] is False
    assert body["recipe_count"] == 0
    names = {lst["name"] for lst in client.get("/api/lists").json()}
    assert "Weeknight" in names


def test_create_list_blank_rejected(client: TestClient) -> None:
    assert client.post("/api/lists", json={"name": "   "}).status_code == 422


def test_rename_list(client: TestClient) -> None:
    list_id = client.post("/api/lists", json={"name": "Old"}).json()["id"]
    renamed = client.patch(f"/api/lists/{list_id}", json={"name": "New"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "New"
    assert client.get(f"/api/lists/{list_id}").json()["name"] == "New"


def test_rename_default_rejected(client: TestClient) -> None:
    favourites = _favourites(client)
    resp = client.patch(f"/api/lists/{favourites['id']}", json={"name": "Nope"})
    assert resp.status_code == 409


def test_rename_blank_rejected(client: TestClient) -> None:
    list_id = client.post("/api/lists", json={"name": "Old"}).json()["id"]
    assert client.patch(f"/api/lists/{list_id}", json={"name": ""}).status_code == 422


def test_delete_list(client: TestClient) -> None:
    list_id = client.post("/api/lists", json={"name": "Doomed"}).json()["id"]
    assert client.delete(f"/api/lists/{list_id}").status_code == 204
    assert client.get(f"/api/lists/{list_id}").status_code == 404


def test_delete_default_rejected(client: TestClient) -> None:
    favourites = _favourites(client)
    assert client.delete(f"/api/lists/{favourites['id']}").status_code == 409


def test_delete_missing_list(client: TestClient) -> None:
    missing = "00000000-0000-4000-8000-000000000000"
    assert client.delete(f"/api/lists/{missing}").status_code == 404


def test_add_and_remove_recipe(client: TestClient) -> None:
    recipe_id = _recipe_ids(client)[0]
    list_id = client.post("/api/lists", json={"name": "Dinner"}).json()["id"]

    assert client.post(f"/api/lists/{list_id}/recipes", json={"recipe_id": recipe_id}).status_code == 204
    detail = client.get(f"/api/lists/{list_id}").json()
    assert detail["recipe_count"] == 1
    assert detail["recipes"][0]["id"] == recipe_id

    assert client.delete(f"/api/lists/{list_id}/recipes/{recipe_id}").status_code == 204
    assert client.get(f"/api/lists/{list_id}").json()["recipe_count"] == 0


def test_add_recipe_idempotent(client: TestClient) -> None:
    recipe_id = _recipe_ids(client)[0]
    list_id = client.post("/api/lists", json={"name": "Dinner"}).json()["id"]
    client.post(f"/api/lists/{list_id}/recipes", json={"recipe_id": recipe_id})
    client.post(f"/api/lists/{list_id}/recipes", json={"recipe_id": recipe_id})
    assert client.get(f"/api/lists/{list_id}").json()["recipe_count"] == 1


def test_add_to_missing_list(client: TestClient) -> None:
    recipe_id = _recipe_ids(client)[0]
    missing = "00000000-0000-4000-8000-000000000000"
    resp = client.post(f"/api/lists/{missing}/recipes", json={"recipe_id": recipe_id})
    assert resp.status_code == 404


def test_add_missing_recipe(client: TestClient) -> None:
    list_id = client.post("/api/lists", json={"name": "Dinner"}).json()["id"]
    missing = "00000000-0000-4000-8000-000000000000"
    resp = client.post(f"/api/lists/{list_id}/recipes", json={"recipe_id": missing})
    assert resp.status_code == 404


def test_remove_non_member_is_noop(client: TestClient) -> None:
    recipe_id = _recipe_ids(client)[0]
    list_id = client.post("/api/lists", json={"name": "Dinner"}).json()["id"]
    # Never added — removing is a clean no-op, not a 404.
    assert client.delete(f"/api/lists/{list_id}/recipes/{recipe_id}").status_code == 204


def test_list_detail_missing(client: TestClient) -> None:
    missing = "00000000-0000-4000-8000-000000000000"
    assert client.get(f"/api/lists/{missing}").status_code == 404


def test_favourite_toggle(client: TestClient) -> None:
    recipe_id = _recipe_ids(client)[0]
    on = client.post(f"/api/recipes/{recipe_id}/favourite")
    assert on.status_code == 200
    assert on.json()["is_favourite"] is True
    favourites = _favourites(client)
    detail = client.get(f"/api/lists/{favourites['id']}").json()
    assert [r["id"] for r in detail["recipes"]] == [recipe_id]

    off = client.post(f"/api/recipes/{recipe_id}/favourite")
    assert off.json()["is_favourite"] is False
    assert client.get(f"/api/lists/{favourites['id']}").json()["recipe_count"] == 0


def test_favourite_missing_recipe(client: TestClient) -> None:
    missing = "00000000-0000-4000-8000-000000000000"
    assert client.post(f"/api/recipes/{missing}/favourite").status_code == 404


def test_recipe_detail_reflects_favourite(client: TestClient) -> None:
    recipe_id = _recipe_ids(client)[0]
    assert client.get(f"/api/recipes/{recipe_id}").json()["is_favourite"] is False
    client.post(f"/api/recipes/{recipe_id}/favourite")
    assert client.get(f"/api/recipes/{recipe_id}").json()["is_favourite"] is True


def test_recipe_lists_membership(client: TestClient) -> None:
    recipe_id = _recipe_ids(client)[0]
    list_id = client.post("/api/lists", json={"name": "Dinner"}).json()["id"]
    client.post(f"/api/lists/{list_id}/recipes", json={"recipe_id": recipe_id})

    memberships = client.get(f"/api/recipes/{recipe_id}/lists").json()
    by_id = {m["id"]: m for m in memberships}
    assert by_id[list_id]["contains"] is True
    favourites = _favourites(client)
    # Favourites always appears, here not containing the recipe.
    assert by_id[favourites["id"]]["contains"] is False
    # Default pinned first.
    assert memberships[0]["is_default"] is True


def test_recipe_lists_missing_recipe(client: TestClient) -> None:
    missing = "00000000-0000-4000-8000-000000000000"
    assert client.get(f"/api/recipes/{missing}/lists").status_code == 404
