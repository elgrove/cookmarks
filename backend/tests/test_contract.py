"""Backend half of the API wire contract (see /contract/README.md).

Pins each response model to the shared `contract/*.example.json`: the model must
serialise to exactly the example, and the live endpoint must emit the same keys.
A field rename on the backend fails here instead of only breaking in the browser.
"""

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.schemas.book import BookSummary
from app.schemas.home import HomeData
from app.schemas.recipe import KeywordSummary, RecipeSearchResults

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


def test_books_endpoint_keys_match_contract(client: TestClient) -> None:
    example = _example("books.example.json")
    item = client.get("/api/books").json()[0]
    assert set(item.keys()) == set(example.keys())


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
