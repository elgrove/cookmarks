from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ReadingQueueItem, User
from app.services.users import create_user


def _book_id(client: TestClient, title: str = "With Recipes") -> str:
    books = client.get("/api/books").json()
    return next(b["id"] for b in books if b["title"] == title)


def _queue(client: TestClient, book_id: str) -> dict:
    resp = client.put(f"/api/books/{book_id}/queue")
    assert resp.status_code == 200
    return resp.json()


def test_queue_add_is_idempotent(client: TestClient, session: Session) -> None:
    book_id = _book_id(client)
    assert _queue(client, book_id) == {"queued": True}
    assert _queue(client, book_id) == {"queued": True}
    assert len(session.scalars(select(ReadingQueueItem)).all()) == 1


def test_queue_remove_is_idempotent(client: TestClient) -> None:
    book_id = _book_id(client)
    _queue(client, book_id)
    for _ in range(2):
        resp = client.delete(f"/api/books/{book_id}/queue")
        assert resp.status_code == 200
        assert resp.json() == {"queued": False}
    assert client.get("/api/reading-queue").json() == []


def test_queue_unknown_book_404s(client: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.put(f"/api/books/{missing}/queue").status_code == 404
    assert client.delete(f"/api/books/{missing}/queue").status_code == 404


def test_queue_is_newest_first(client: TestClient) -> None:
    first = _book_id(client)
    second = _book_id(client, "No Recipes Yet")
    _queue(client, first)
    _queue(client, second)
    titles = [b["title"] for b in client.get("/api/reading-queue").json()]
    assert titles == ["No Recipes Yet", "With Recipes"]


def test_queued_book_carries_its_shape(client: TestClient) -> None:
    _queue(client, _book_id(client))
    (entry,) = client.get("/api/reading-queue").json()
    assert entry["title"] == "With Recipes"
    assert entry["author"] == "Author One"
    assert entry["recipe_count"] == 3
    assert entry["has_cover"] is False


def test_finished_book_drops_out_of_queue_and_up_next(client: TestClient) -> None:
    book_id = _book_id(client)
    _queue(client, book_id)
    assert client.post(f"/api/books/{book_id}/seen").status_code == 200
    assert client.get("/api/reading-queue").json() == []
    assert client.get("/api/home").json()["up_next"] == []


def test_unfinishing_brings_a_queued_book_back(client: TestClient) -> None:
    """The finished filter is read-time, not a deletion — resetting progress restores
    the queue entry."""
    book_id = _book_id(client)
    _queue(client, book_id)
    client.post(f"/api/books/{book_id}/seen")
    client.delete(f"/api/books/{book_id}/seen")
    assert [b["id"] for b in client.get("/api/reading-queue").json()] == [book_id]


def test_in_progress_book_stays_queued_but_leaves_up_next(client: TestClient) -> None:
    """A started book shows on the Continue strip, so Up next hides it — but the queue
    page still lists it."""
    book_id = _book_id(client)
    _queue(client, book_id)
    index = client.get(f"/api/books/{book_id}/recipe-index").json()
    recipe_id = next(r["id"] for r in index if r["name"] == "Recipe 0")
    assert (
        client.put(
            f"/api/books/{book_id}/reading", json={"mode": "book", "recipe_id": recipe_id}
        ).status_code
        == 200
    )
    home = client.get("/api/home").json()
    assert [b["id"] for b in home["continue_reading"]] == [book_id]
    assert home["up_next"] == []
    assert [b["id"] for b in client.get("/api/reading-queue").json()] == [book_id]


def test_up_next_lists_queued_books(client: TestClient) -> None:
    book_id = _book_id(client, "No Recipes Yet")
    _queue(client, book_id)
    home = client.get("/api/home").json()
    assert [b["id"] for b in home["up_next"]] == [book_id]


def test_queue_is_per_user(
    client: TestClient, session: Session, act_as: Callable[[str], User]
) -> None:
    create_user(session, "other", "other-password")
    _queue(client, _book_id(client))
    act_as("other")
    assert client.get("/api/reading-queue").json() == []
    assert client.get("/api/home").json()["up_next"] == []


def test_book_detail_carries_queued_flag(client: TestClient) -> None:
    book_id = _book_id(client)
    assert client.get(f"/api/books/{book_id}").json()["queued"] is False
    _queue(client, book_id)
    assert client.get(f"/api/books/{book_id}").json()["queued"] is True
