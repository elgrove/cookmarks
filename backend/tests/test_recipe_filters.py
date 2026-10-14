"""Advanced filters operate on the full result set and keep navigation consistent."""

import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.recipes import _clear_keyword_cache
from app.models import Keyword, Recipe, User
from app.models.enums import KeywordCategory
from app.schemas.recipe_filters import RecipeFilters


def query(client: TestClient, *rules: dict[str, Any], match: str = "all", **params: Any):
    return client.get(
        "/api/recipes",
        params={"filters": json.dumps({"version": 1, "match": match, "rules": rules}), **params},
    )


def rule(field: str, operator: str, value: Any = None) -> dict[str, Any]:
    return {"field": field, "operator": operator, "value": value}


@pytest.mark.parametrize(
    ("field", "operator", "value", "count"),
    [
        ("name", "eq", "RECIPE 0", 1),
        ("name", "neq", "Recipe 0", 2),
        ("name", "contains", "recipe", 3),
        ("name", "starts_with", "RECIPE", 3),
        ("name", "ends_with", "0", 1),
        ("name", "not_contains", "0", 2),
        ("description", "contains", "weeknight", 1),
        ("description", "not_contains", "pasta", 2),
        ("description", "is_empty", None, 2),
        ("description", "is_not_empty", None, 1),
        ("alternate_name", "is_empty", None, 3),
        ("summary", "is_empty", None, 3),
        ("ingredients", "contains", "anchovy", 1),
        ("ingredients", "neq", "200g pasta", 2),
        ("ingredients", "not_contains", "pasta", 2),
        ("ingredients", "is_empty", None, 2),
        ("instructions", "contains", "boil", 1),
        ("instructions", "not_contains", "boil", 2),
        ("instructions", "is_not_empty", None, 1),
        ("instructions", "is_empty", None, 2),
        ("keyword", "eq", "pasta", 1),
        ("keyword", "neq", "pasta", 2),
        ("author", "contains", "ONE", 3),
        ("book", "contains", "with", 3),
        ("has_image", "eq", True, 1),
        ("has_image", "eq", False, 2),
        ("favourite", "eq", True, 0),
        ("favourite", "eq", False, 3),
    ],
)
def test_fields(client: TestClient, field: str, operator: str, value: Any, count: int) -> None:
    response = query(client, rule(field, operator, value))
    assert response.status_code == 200, response.text
    assert response.json()["total"] == count


def test_categories_and_negative_collection(client: TestClient, session: Session) -> None:
    pasta = session.scalar(select(Keyword).where(Keyword.name == "pasta"))
    assert pasta is not None
    pasta.category = KeywordCategory.KEY_INGREDIENT
    session.commit()
    assert query(client, rule("key_ingredient", "contains", "past")).json()["total"] == 1
    assert query(client, rule("method", "contains", "past")).json()["total"] == 0
    assert query(client, rule("key_ingredient", "neq", "pasta")).json()["total"] == 2
    assert query(client, rule("method", "is_empty")).json()["total"] == 3
    assert (
        query(client, rule("key_ingredient", "eq", "pasta")).json()["facets"][0]["category"]
        == "key_ingredient"
    )


def test_all_any_and_existing_criteria(client: TestClient) -> None:
    rules = [rule("name", "ends_with", "0"), rule("name", "ends_with", "1")]
    assert query(client, *rules).json()["total"] == 0
    assert query(client, *rules, match="any").json()["total"] == 2
    assert query(client, *rules, match="any", keyword="pasta").json()["total"] == 1
    assert query(client, rule("name", "ends_with", "1"), q="anchovy").json()["total"] == 0


def test_literal_wildcards_and_unicode(client: TestClient, session: Session) -> None:
    recipe = session.scalars(select(Recipe).order_by(Recipe.order)).first()
    assert recipe is not None
    recipe.summary = "CRÈME 10%_sweet"
    session.commit()
    assert query(client, rule("summary", "contains", "crème")).json()["total"] == 1
    assert query(client, rule("summary", "contains", "%_")).json()["total"] == 1
    assert query(client, rule("name", "contains", "%")).json()["total"] == 0


@pytest.mark.parametrize(
    "filters",
    [
        "{",
        "null",
    {"version": True, "match": "all", "rules": []},
        {"version": 2, "match": "all", "rules": []},
        {"version": 1, "match": "all", "rules": [rule("unknown", "eq", "a")]},
        {"version": 1, "match": "all", "rules": [rule("name", "contains", "")]},
        {"version": 1, "match": "all", "rules": [rule("favourite", "contains", "true")]},
        {"version": 1, "match": "all", "rules": [rule("list", "in_list", "x")]},
        {"version": 1, "match": "all", "rules": [rule("name", "eq", "x" * 501)]},
        {"version": 1, "match": "all", "rules": [rule("name", "eq", "x")] * 21},
        {"version": 1, "match": "all", "rules": [rule("name", "is_empty", "x")]},
    ],
)
def test_invalid(client: TestClient, filters: Any) -> None:
    raw = filters if isinstance(filters, str) else json.dumps(filters)
    assert client.get("/api/recipes", params={"filters": raw}).status_code == 422


def test_pagination_and_navigation(client: TestClient) -> None:
    filters = {"version": 1, "match": "all", "rules": [rule("name", "neq", "Recipe 1")]}
    params = {"filters": json.dumps(filters), "sort": "name"}
    first = client.get("/api/recipes", params={**params, "limit": 1}).json()
    second = client.get("/api/recipes", params={**params, "limit": 1, "offset": 1}).json()
    assert first["total"] == second["total"] == 2
    assert first["items"][0]["name"] == "Recipe 0"
    assert second["items"][0]["name"] == "Recipe 2"
    detail = client.get(
        f"/api/recipes/{first['items'][0]['id']}", params={**params, "context": "search"}
    ).json()
    assert detail["next"]["id"] == second["items"][0]["id"]
    assert detail["previous"] is None


def test_lists_favourites_user_isolation_and_live_pager(
    client: TestClient, session: Session, act_as: Callable[[str], User]
) -> None:
    recipes = client.get("/api/recipes", params={"all": True, "sort": "name"}).json()["items"]
    listing = client.post("/api/lists", json={"name": "Dinner"}).json()
    for recipe in recipes[:2]:
        response = client.post(
            f"/api/lists/{listing['id']}/recipes", json={"recipe_id": recipe["id"]}
        )
        assert response.status_code < 300, response.text
    filters = {"version": 1, "match": "all", "rules": [rule("list", "in_list", listing["id"])]}
    params = {"filters": json.dumps(filters), "context": "search", "sort": "name"}
    url = f"/api/recipes/{recipes[0]['id']}"
    assert client.get(url, params=params).json()["next"]["id"] == recipes[1]["id"]
    client.delete(f"/api/lists/{listing['id']}/recipes/{recipes[1]['id']}")
    assert client.get(url, params=params).json()["next"] is None
    assert query(client, rule("list", "not_in_list", listing["id"])).json()["total"] == 2
    session.add(User(username="other", password_hash="unused"))
    session.commit()
    act_as("other")
    assert query(client, rule("list", "in_list", listing["id"])).status_code == 404
    assert query(client, rule("list", "not_in_list", str(uuid.uuid4()))).status_code == 404
    assert query(client, rule("favourite", "eq", True)).json()["total"] == 0


def test_keyword_exact_lookup_bypasses_popular_pool(client: TestClient, session: Session) -> None:
    assert client.get("/api/keywords", params={"limit": 1}).json()[0]["name"] == "pasta"
    quick = session.scalar(select(Keyword).where(Keyword.name == "quick"))
    assert quick is not None
    quick.category = KeywordCategory.METHOD
    session.commit()
    data = client.get(
        "/api/keywords", params=[("name", "QUICK"), ("name", "italian"), ("name", "unknown")]
    ).json()
    assert data == [{"name": "quick", "recipe_count": 1, "category": "method"}]
    _clear_keyword_cache()
    assert client.get("/api/keywords", params=[("name", "a")] * 101).status_code == 422


def test_request_contract() -> None:
    example = json.loads(
        (Path(__file__).resolve().parents[2] / "contract/recipefilters.example.json").read_text()
    )
    assert RecipeFilters.model_validate(example).model_dump(mode="json") == example


def test_category_changes_refresh_recipe_neighbours(client: TestClient, session: Session) -> None:
    recipes = list(session.scalars(select(Recipe).order_by(Recipe.order)))
    # Italian is already a book-only term in the seeded vocabulary.
    first = session.scalar(select(Keyword).where(Keyword.name == "italian"))
    assert first is not None
    first.category = KeywordCategory.CUISINE_REGION
    second = Keyword(name="roman", category=KeywordCategory.CUISINE_REGION)
    recipes[0].keywords.append(first)
    recipes[1].keywords.append(second)
    session.commit()
    filters = {"version": 1, "match": "all", "rules": [rule("cuisine_region", "is_not_empty")]}
    params = {"filters": json.dumps(filters), "context": "search", "sort": "name"}
    url = f"/api/recipes/{recipes[0].id}"
    assert client.get(url, params=params).json()["next"]["id"] == str(recipes[1].id)
    second.category = None
    session.commit()
    assert client.get("/api/recipes", params=params).json()["total"] == 1
    assert client.get(url, params=params).json()["next"] is None
