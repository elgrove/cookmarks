from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Book, Recipe, RecipeView, User
from app.services.users import create_user

FEATURE_KEYS = {"id", "title", "author", "description", "recipe_count", "has_cover"}
CONTINUE_KEYS = {"id", "title", "author", "recipe_count", "seen_count", "has_cover"}


def _recipe_ids(client: TestClient) -> list[str]:
    """The seeded book's recipes, in book order."""
    book_id = next(b["id"] for b in client.get("/api/books").json() if b["title"] == "With Recipes")
    return [r["id"] for r in client.get(f"/api/books/{book_id}/recipe-index").json()]


def test_home_shape(client: TestClient) -> None:
    resp = client.get("/api/home")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["stats"].keys()) == {"books", "recipes", "keywords", "recipes_seen"}
    # 3 distinct keywords in the shared vocabulary: "Pasta" + "Quick" on a recipe,
    # plus "Italian" carried only on the book.
    assert body["stats"] == {"books": 2, "recipes": 3, "keywords": 3, "recipes_seen": 0}
    assert body["continue_reading"] == []


def test_home_book_of_the_day(client: TestClient) -> None:
    feature = client.get("/api/home").json()["book_of_the_day"]
    assert feature is not None
    assert set(feature.keys()) == FEATURE_KEYS
    # Only the recipe-bearing book is eligible to be featured.
    assert feature["title"] == "With Recipes"
    assert feature["recipe_count"] == 3
    assert feature["has_cover"] is False


def test_recipes_seen_counts_distinct_recipes(client: TestClient) -> None:
    ids = _recipe_ids(client)
    client.post(f"/api/recipes/{ids[0]}/seen")
    client.post(f"/api/recipes/{ids[0]}/seen")
    client.post(f"/api/recipes/{ids[1]}/seen")
    assert client.get("/api/home").json()["stats"]["recipes_seen"] == 2


def test_continue_reading_lists_part_read_books(client: TestClient) -> None:
    ids = _recipe_ids(client)
    client.post(f"/api/recipes/{ids[0]}/seen")

    strip = client.get("/api/home").json()["continue_reading"]
    assert len(strip) == 1
    assert set(strip[0].keys()) == CONTINUE_KEYS
    assert strip[0]["title"] == "With Recipes"
    assert (strip[0]["seen_count"], strip[0]["recipe_count"]) == (1, 3)


def test_continue_reading_drops_finished_books(client: TestClient) -> None:
    for recipe_id in _recipe_ids(client):
        client.post(f"/api/recipes/{recipe_id}/seen")
    # Every recipe seen — there is nothing left to continue.
    assert client.get("/api/home").json()["continue_reading"] == []


def test_home_progress_is_per_user(
    client: TestClient, session: Session, act_as: Callable[[str], User]
) -> None:
    """The strip and the read stat are one account's own — the user filter sits in the
    strip's join, so it is worth pinning."""
    create_user(session, "other", "other-password")
    client.post(f"/api/recipes/{_recipe_ids(client)[0]}/seen")

    act_as("other")
    body = client.get("/api/home").json()
    assert body["stats"]["recipes_seen"] == 0
    assert body["continue_reading"] == []

    act_as("tester")
    body = client.get("/api/home").json()
    assert body["stats"]["recipes_seen"] == 1
    assert [b["title"] for b in body["continue_reading"]] == ["With Recipes"]


def test_continue_reading_is_most_recent_first(client: TestClient, session: Session) -> None:
    # A second part-read book, so ordering has something to order.
    other = Book(
        calibre_id=3,
        title="Also Started",
        author="Author Three",
        path="Author Three/Also Started (3)",
    )
    session.add(other)
    session.flush()
    session.add_all(
        Recipe(book_id=other.id, order=i, name=f"Other {i}", ingredients=[], instructions=[])
        for i in range(2)
    )
    session.commit()

    first = _recipe_ids(client)[0]
    other_recipe = session.scalar(select(Recipe).where(Recipe.book_id == other.id))
    assert other_recipe is not None
    client.post(f"/api/recipes/{first}/seen")
    client.post(f"/api/recipes/{other_recipe.id}/seen")

    # Back-date the "With Recipes" view so "Also Started" is the more recent read.
    view = session.scalar(select(RecipeView).where(RecipeView.recipe_id == other_recipe.id))
    assert view is not None
    stale = session.scalar(select(RecipeView).where(RecipeView.recipe_id != other_recipe.id))
    assert stale is not None
    stale.last_viewed_at = datetime.now(UTC) - timedelta(days=2)
    session.commit()

    strip = client.get("/api/home").json()["continue_reading"]
    assert [b["title"] for b in strip] == ["Also Started", "With Recipes"]
