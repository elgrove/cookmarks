from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Book, BookReading, Recipe, User
from app.services.users import create_user

FEATURE_KEYS = {"id", "title", "author", "description", "recipe_count", "has_cover"}
CONTINUE_KEYS = {"id", "title", "author", "mode", "fraction", "resume_recipe_id", "has_cover"}
RECENT_KEYS = {"id", "name", "book_id", "book_title"}


def _book_id(client: TestClient, title: str = "With Recipes") -> str:
    return next(b["id"] for b in client.get("/api/books").json() if b["title"] == title)


def _recipe_ids(client: TestClient) -> list[str]:
    """The seeded book's recipes, in book order."""
    return [r["id"] for r in client.get(f"/api/books/{_book_id(client)}/recipe-index").json()]


def _read_pages_to(client: TestClient, book_id: str, recipe_id: str | None = None) -> None:
    """Open a book in the reader, its pages having carried past `recipe_id`."""
    body: dict[str, object] = {"mode": "book"}
    if recipe_id is not None:
        body["recipe_id"] = recipe_id
    assert client.put(f"/api/books/{book_id}/reading", json=body).status_code == 200


def _read_recipe(client: TestClient, book_id: str, recipe_id: str) -> None:
    """Read one of the book's recipes, in the book's own context."""
    body = {"mode": "recipes", "recipe_id": recipe_id}
    assert client.put(f"/api/books/{book_id}/reading", json=body).status_code == 200


def test_home_shape(client: TestClient) -> None:
    resp = client.get("/api/home")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["stats"].keys()) == {"books", "recipes", "keywords", "books_read"}
    # 3 distinct keywords in the shared vocabulary: "Pasta" + "Quick" on a recipe,
    # plus "Italian" carried only on the book.
    assert body["stats"] == {"books": 2, "recipes": 3, "keywords": 3, "books_read": 0}
    assert body["continue_reading"] == []
    assert body["recently_read"] == []


def test_home_book_of_the_day(client: TestClient) -> None:
    feature = client.get("/api/home").json()["book_of_the_day"]
    assert feature is not None
    assert set(feature.keys()) == FEATURE_KEYS
    # Only the recipe-bearing book is eligible to be featured.
    assert feature["title"] == "With Recipes"
    assert feature["recipe_count"] == 3
    assert feature["has_cover"] is False


def test_books_read_counts_books_finished(client: TestClient) -> None:
    """The library figure counts books read through, not recipes opened."""
    ids = _recipe_ids(client)
    client.post(f"/api/recipes/{ids[0]}/seen")
    assert client.get("/api/home").json()["stats"]["books_read"] == 0

    client.post(f"/api/books/{_book_id(client)}/seen")
    assert client.get("/api/home").json()["stats"]["books_read"] == 1


def test_continue_reading_lists_books_open_in_the_reader(client: TestClient) -> None:
    ids = _recipe_ids(client)
    _read_pages_to(client, _book_id(client), ids[0])

    strip = client.get("/api/home").json()["continue_reading"]
    assert len(strip) == 1
    assert set(strip[0].keys()) == CONTINUE_KEYS
    assert strip[0]["title"] == "With Recipes"
    assert strip[0]["mode"] == "book"
    # One of three recipes reached by the pages.
    assert strip[0]["fraction"] == 1 / 3
    assert strip[0]["resume_recipe_id"] == ids[0]


def test_continue_reading_ignores_recipes_read_outside_the_book(client: TestClient) -> None:
    """A recipe met through search is not a step through its book, so it starts nothing."""
    for recipe_id in _recipe_ids(client):
        client.post(f"/api/recipes/{recipe_id}/seen")
    assert client.get("/api/home").json()["continue_reading"] == []


def test_continue_reading_tracks_the_recipes_mode(client: TestClient) -> None:
    """Reading a recipe in its book's context is reading the book, recipe by recipe."""
    ids = _recipe_ids(client)
    _read_recipe(client, _book_id(client), ids[0])

    strip = client.get("/api/home").json()["continue_reading"]
    assert len(strip) == 1
    assert strip[0]["mode"] == "recipes"
    assert strip[0]["fraction"] == 1 / 3
    # Resumes where it got to, not the one after: progress is where you are.
    assert strip[0]["resume_recipe_id"] == ids[0]


def test_continue_reading_drops_a_book_read_to_its_last_recipe(client: TestClient) -> None:
    ids = _recipe_ids(client)
    _read_recipe(client, _book_id(client), ids[-1])
    assert client.get("/api/home").json()["continue_reading"] == []


def test_reading_modes_share_one_position(client: TestClient) -> None:
    """One book, one reading: the pages carry on from where the recipes got to."""
    ids = _recipe_ids(client)
    book_id = _book_id(client)
    _read_recipe(client, book_id, ids[1])
    _read_pages_to(client, book_id)

    strip = client.get("/api/home").json()["continue_reading"]
    assert len(strip) == 1
    # The mode moves over; the position it inherits is the one the recipes reached.
    assert (strip[0]["mode"], strip[0]["fraction"]) == ("book", 2 / 3)
    assert strip[0]["resume_recipe_id"] == ids[1]


def test_continue_reading_drops_a_book_marked_read(client: TestClient) -> None:
    book_id = _book_id(client)
    _read_pages_to(client, book_id, _recipe_ids(client)[0])
    client.post(f"/api/books/{book_id}/seen")
    assert client.get("/api/home").json()["continue_reading"] == []


def test_recently_read_is_most_recent_first(client: TestClient) -> None:
    ids = _recipe_ids(client)
    for recipe_id in ids:
        client.post(f"/api/recipes/{recipe_id}/seen")

    recent = client.get("/api/home").json()["recently_read"]
    assert set(recent[0].keys()) == RECENT_KEYS
    assert [r["id"] for r in recent] == list(reversed(ids))
    assert recent[0]["book_title"] == "With Recipes"

    # Re-opening an earlier one brings it back to the front.
    client.post(f"/api/recipes/{ids[0]}/seen")
    assert client.get("/api/home").json()["recently_read"][0]["id"] == ids[0]


def test_recently_read_forgets_an_unmarked_recipe(client: TestClient) -> None:
    recipe_id = _recipe_ids(client)[0]
    client.post(f"/api/recipes/{recipe_id}/seen")
    client.delete(f"/api/recipes/{recipe_id}/seen")
    assert client.get("/api/home").json()["recently_read"] == []


def test_home_progress_is_per_user(
    client: TestClient, session: Session, act_as: Callable[[str], User]
) -> None:
    """The strip and the read stat are one account's own — the user filter sits in the
    strip's join, so it is worth pinning."""
    create_user(session, "other", "other-password")
    ids = _recipe_ids(client)
    client.post(f"/api/recipes/{ids[0]}/seen")
    _read_pages_to(client, _book_id(client), ids[0])

    act_as("other")
    body = client.get("/api/home").json()
    assert body["stats"]["books_read"] == 0
    assert body["continue_reading"] == []
    assert body["recently_read"] == []

    act_as("tester")
    body = client.get("/api/home").json()
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

    other_recipe = session.scalar(select(Recipe).where(Recipe.book_id == other.id))
    assert other_recipe is not None
    _read_pages_to(client, _book_id(client), _recipe_ids(client)[0])
    _read_pages_to(client, str(other.id), str(other_recipe.id))

    # Back-date the "With Recipes" reading so "Also Started" is the more recent one.
    stale = session.scalar(select(BookReading).where(BookReading.book_id != other.id))
    assert stale is not None
    stale.last_read_at = datetime.now(UTC) - timedelta(days=2)
    session.commit()

    strip = client.get("/api/home").json()["continue_reading"]
    assert [b["title"] for b in strip] == ["Also Started", "With Recipes"]
