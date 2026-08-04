"""Backend half of the API wire contract (see /contract/README.md).

Pins each response model to the shared `contract/*.example.json`: the model must
serialise to exactly the example, and the live endpoint must emit the same keys.
A field rename on the backend fails here instead of only breaking in the browser.
"""

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.schemas.auth import AuthMe, UserRead
from app.schemas.book import BookFilter, BookSummary, RecipeIndexEntry
from app.schemas.config import ConfigRead
from app.schemas.extraction import ReviewQuestion
from app.schemas.home import HomeData
from app.schemas.recipe import (
    KeywordSummary,
    RecipeDetail,
    RecipeSearchResults,
    SemanticSearchResults,
    SimilarRecipes,
)
from app.schemas.recipe_list import ListDetail, ListMembership, ListSummary
from app.schemas.task_run import TaskRunRead
from app.schemas.tasks import TaskRunAck

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contract"


def _example(name: str) -> dict[str, Any]:
    return json.loads((CONTRACT_DIR / name).read_text())


def test_book_summary_model_matches_contract() -> None:
    example = _example("books.example.json")
    dumped = BookSummary.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_home_model_matches_contract() -> None:
    example = _example("home.example.json")
    dumped = HomeData.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_recipe_detail_model_matches_contract() -> None:
    example = _example("recipe.example.json")
    dumped = RecipeDetail.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_book_filter_model_matches_contract() -> None:
    example = _example("bookfilters.example.json")
    dumped = BookFilter.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_recipe_index_entry_model_matches_contract() -> None:
    example = _example("recipeindex.example.json")
    dumped = RecipeIndexEntry.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_books_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("books.example.json")
    item = client.get("/api/books").json()[0]
    assert set(item.keys()) == set(example.keys())


def test_book_filters_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("bookfilters.example.json")
    item = client.get("/api/books/filters").json()[0]
    assert set(item.keys()) == set(example.keys())


def test_recipe_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("recipe.example.json")
    book = next(b for b in client.get("/api/books").json() if b["title"] == "With Recipes")
    recipe_id = client.get(f"/api/books/{book['id']}").json()["recipes"][0]["id"]
    body = client.get(f"/api/recipes/{recipe_id}").json()
    assert set(body.keys()) == set(example.keys())


def test_home_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("home.example.json")
    body = client.get("/api/home").json()
    assert set(body.keys()) == set(example.keys())
    assert set(body["stats"].keys()) == set(example["stats"].keys())
    assert set(body["book_of_the_day"].keys()) == set(example["book_of_the_day"].keys())


def test_recipe_search_model_matches_contract() -> None:
    example = _example("recipes.example.json")
    dumped = RecipeSearchResults.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_similar_recipes_model_matches_contract() -> None:
    example = _example("similar.example.json")
    dumped = SimilarRecipes.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_keyword_summary_model_matches_contract() -> None:
    example = _example("keywords.example.json")
    dumped = KeywordSummary.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_recipes_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("recipes.example.json")
    body = client.get("/api/recipes", params={"q": "recipe"}).json()
    assert set(body.keys()) == set(example.keys())
    assert set(body["items"][0].keys()) == set(example["items"][0].keys())


def test_keywords_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("keywords.example.json")
    item = client.get("/api/keywords").json()[0]
    assert set(item.keys()) == set(example.keys())


def test_semantic_search_model_matches_contract() -> None:
    example = _example("semanticsearch.example.json")
    dumped = SemanticSearchResults.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_semantic_endpoint_keys_match_contract(client: TestClient) -> None:
    # No provider is configured in tests, so this returns the unavailable shape — but
    # the top-level keys are the contract regardless; item keys are pinned by the
    # model round-trip above and exercised live in test_semantic_search.
    example = _example("semanticsearch.example.json")
    body = client.get("/api/recipes/semantic", params={"q": "pasta"}).json()
    assert set(body.keys()) == set(example.keys())


def test_list_summary_model_matches_contract() -> None:
    example = _example("listsummary.example.json")
    dumped = ListSummary.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_list_detail_model_matches_contract() -> None:
    example = _example("listdetail.example.json")
    dumped = ListDetail.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_list_membership_model_matches_contract() -> None:
    example = _example("listmembership.example.json")
    dumped = ListMembership.model_validate(example).model_dump(mode="json")
    assert dumped == example


def _a_recipe_id(client: TestClient) -> str:
    book = next(b for b in client.get("/api/books").json() if b["title"] == "With Recipes")
    return client.get(f"/api/books/{book['id']}").json()["recipes"][0]["id"]


def test_lists_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("listsummary.example.json")
    item = client.get("/api/lists").json()[0]
    assert set(item.keys()) == set(example.keys())


def test_list_detail_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("listdetail.example.json")
    recipe_id = _a_recipe_id(client)
    list_id = client.post("/api/lists", json={"name": "Test"}).json()["id"]
    client.post(f"/api/lists/{list_id}/recipes", json={"recipe_id": recipe_id})
    body = client.get(f"/api/lists/{list_id}").json()
    assert set(body.keys()) == set(example.keys())
    assert set(body["recipes"][0].keys()) == set(example["recipes"][0].keys())


def test_recipe_lists_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("listmembership.example.json")
    recipe_id = _a_recipe_id(client)
    item = client.get(f"/api/recipes/{recipe_id}/lists").json()[0]
    assert set(item.keys()) == set(example.keys())


def test_task_run_model_matches_contract() -> None:
    example = _example("taskrun.example.json")
    dumped = TaskRunRead.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_extract_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("taskrun.example.json")
    book = next(b for b in client.get("/api/books").json() if b["title"] == "No Recipes Yet")
    body = client.post(f"/api/books/{book['id']}/extract").json()
    assert set(body.keys()) == set(example.keys())


def test_task_runs_index_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("taskrun.example.json")
    book = next(b for b in client.get("/api/books").json() if b["title"] == "No Recipes Yet")
    client.post(f"/api/books/{book['id']}/extract")
    item = client.get("/api/task-runs").json()[0]
    assert set(item.keys()) == set(example.keys())


def test_review_question_model_matches_contract() -> None:
    example = _example("reviewquestion.example.json")
    dumped = ReviewQuestion.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_review_question_current_matches_contract() -> None:
    # The question the graph actually raises (from the shared review constants) is the
    # one the UI is pinned to, so the operator can never be shown a stale question.
    example = _example("reviewquestion.example.json")
    assert ReviewQuestion.current().model_dump(mode="json") == example


def test_config_model_matches_contract() -> None:
    example = _example("config.example.json")
    dumped = ConfigRead.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_config_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("config.example.json")
    body = client.get("/api/config").json()
    assert set(body.keys()) == set(example.keys())
    assert set(body["providers"][0].keys()) == set(example["providers"][0].keys())


def test_task_run_ack_model_matches_contract() -> None:
    example = _example("taskrunack.example.json")
    dumped = TaskRunAck.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_book_keywords_task_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("taskrunack.example.json")
    body = client.post("/api/tasks/book-keywords", json={}).json()
    assert set(body.keys()) == set(example.keys())


def test_auth_me_model_matches_contract() -> None:
    example = _example("authme.example.json")
    dumped = AuthMe.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_auth_me_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("authme.example.json")
    body = client.get("/api/auth/me").json()
    assert set(body.keys()) == set(example.keys())


def test_user_model_matches_contract() -> None:
    example = _example("user.example.json")
    dumped = UserRead.model_validate(example).model_dump(mode="json")
    assert dumped == example


def test_users_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("user.example.json")
    item = client.get("/api/users").json()[0]
    assert set(item.keys()) == set(example.keys())
