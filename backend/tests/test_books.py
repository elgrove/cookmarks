import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CalibreExclusion, Recipe, RecipeListItem, User
from app.services.ingest import IngestError
from app.services.users import create_user
from app.services.vector_store import EMBEDDING_DIMENSIONS, VectorStore

EXPECTED_KEYS = {
    "id",
    "title",
    "author",
    "recipe_count",
    "progress",
    "has_cover",
    "pubdate",
    "keywords",
}
DETAIL_KEYS = {
    "id",
    "title",
    "author",
    "isbn",
    "pubdate",
    "description",
    "recipe_count",
    "has_cover",
    "has_epub",
    "has_pdf",
    "added",
    "keywords",
    "recipes",
    "queued",
    "reading",
    "resume_recipe",
}


def test_list_books_shape(client: TestClient) -> None:
    resp = client.get("/api/books")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2
    for item in body:
        assert set(item.keys()) == EXPECTED_KEYS


def test_list_books_etag_revalidation(client: TestClient) -> None:
    first = client.get("/api/books")
    etag = first.headers["ETag"]
    assert first.headers["Cache-Control"] == "private, no-cache"

    not_modified = client.get("/api/books", headers={"If-None-Match": etag})
    assert not_modified.status_code == 304
    assert not_modified.headers["ETag"] == etag

    book_id = first.json()[0]["id"]
    client.put(f"/api/books/{book_id}/reading", json={"mode": "book", "location": "epubcfi(/6/2)"})
    changed = client.get("/api/books", headers={"If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.headers["ETag"] != etag


def test_recipe_counts(client: TestClient) -> None:
    books = {b["title"]: b for b in client.get("/api/books").json()}
    assert books["With Recipes"]["recipe_count"] == 3
    assert books["No Recipes Yet"]["recipe_count"] == 0


def test_default_sort_is_recent_first(client: TestClient) -> None:
    titles = [b["title"] for b in client.get("/api/books").json()]
    # created_at DESC: the 2021 book precedes the 2020 book.
    assert titles == ["No Recipes Yet", "With Recipes"]


def test_has_cover_false_for_missing_files(client: TestClient) -> None:
    assert all(b["has_cover"] is False for b in client.get("/api/books").json())


def test_cover_404_when_file_missing(client: TestClient) -> None:
    book_id = client.get("/api/books").json()[0]["id"]
    assert client.get(f"/api/books/{book_id}/cover").status_code == 404


def test_cover_404_for_unknown_book(client: TestClient) -> None:
    assert client.get(f"/api/books/{uuid.uuid4()}/cover").status_code == 404


def _book_id(client: TestClient, title: str) -> str:
    return next(b["id"] for b in client.get("/api/books").json() if b["title"] == title)


def test_book_detail_shape(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    resp = client.get(f"/api/books/{book_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == DETAIL_KEYS
    assert body["title"] == "With Recipes"
    assert body["recipe_count"] == 3


def test_book_detail_recipes_capped_and_shaped(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    recipes = client.get(f"/api/books/{book_id}").json()["recipes"]
    assert 0 < len(recipes) <= 10
    for row in recipes:
        assert set(row.keys()) == {"id", "name", "keywords"}
        assert isinstance(row["keywords"], list)
    # The seeded "Recipe 0" carries two keywords, sorted.
    keyworded = next((r for r in recipes if r["name"] == "Recipe 0"), None)
    if keyworded is not None:
        assert keyworded["keywords"] == ["Pasta", "Quick"]


def test_book_detail_empty_recipes(client: TestClient) -> None:
    book_id = _book_id(client, "No Recipes Yet")
    body = client.get(f"/api/books/{book_id}").json()
    assert body["recipe_count"] == 0
    assert body["recipes"] == []


def test_progress_reports_how_far_through_the_book(client: TestClient) -> None:
    """Progress is measured in recipes: reaching the second of three is two thirds in."""
    book_id = _book_id(client, "With Recipes")
    ids = [r["id"] for r in client.get(f"/api/books/{book_id}/recipe-index").json()]
    client.put(f"/api/books/{book_id}/reading", json={"mode": "recipes", "recipe_id": ids[1]})

    assert client.get(f"/api/books/{book_id}").json()["reading"]["fraction"] == 2 / 3
    summaries = {b["title"]: b for b in client.get("/api/books").json()}
    assert summaries["With Recipes"]["progress"] == 2 / 3
    # A book never opened reports no progress at all, rather than 0%.
    assert summaries["No Recipes Yet"]["progress"] is None


def test_progress_only_moves_forwards(client: TestClient) -> None:
    """Re-reading an earlier recipe doesn't undo the reading that got past it."""
    book_id = _book_id(client, "With Recipes")
    ids = [r["id"] for r in client.get(f"/api/books/{book_id}/recipe-index").json()]
    client.put(f"/api/books/{book_id}/reading", json={"mode": "recipes", "recipe_id": ids[2]})
    client.put(f"/api/books/{book_id}/reading", json={"mode": "recipes", "recipe_id": ids[0]})

    reading = client.get(f"/api/books/{book_id}").json()["reading"]
    assert reading["fraction"] == 1.0
    assert reading["anchor"]["id"] == ids[2]


def test_progress_is_per_user(
    client: TestClient, session: Session, act_as: Callable[[str], User]
) -> None:
    """Each account sees its own reading and nothing of anyone else's."""
    create_user(session, "other", "other-password")

    book_id = _book_id(client, "With Recipes")
    ids = [r["id"] for r in client.get(f"/api/books/{book_id}/recipe-index").json()]
    client.put(f"/api/books/{book_id}/reading", json={"mode": "recipes", "recipe_id": ids[1]})

    act_as("other")
    assert client.get(f"/api/books/{book_id}").json()["reading"] is None
    client.put(f"/api/books/{book_id}/reading", json={"mode": "recipes", "recipe_id": ids[0]})
    assert client.get(f"/api/books/{book_id}").json()["reading"]["fraction"] == 1 / 3

    # The first account's position is untouched by the second's reading.
    act_as("tester")
    assert client.get(f"/api/books/{book_id}").json()["reading"]["fraction"] == 2 / 3


def test_resume_recipe_is_the_furthest_reached_or_the_first(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    ids = [r["id"] for r in client.get(f"/api/books/{book_id}/recipe-index").json()]
    # Never opened: the recipes start at the beginning.
    assert client.get(f"/api/books/{book_id}").json()["resume_recipe"]["id"] == ids[0]

    client.put(f"/api/books/{book_id}/reading", json={"mode": "book", "recipe_id": ids[1]})
    assert client.get(f"/api/books/{book_id}").json()["resume_recipe"]["id"] == ids[1]


def test_reading_a_recipe_alone_moves_nothing(client: TestClient) -> None:
    """Opening a recipe is recorded, but only reading it as part of the book is reading
    the book — so a recipe met through search starts nothing."""
    book_id = _book_id(client, "With Recipes")
    recipe_id = client.get(f"/api/books/{book_id}/recipe-index").json()[0]["id"]
    client.post(f"/api/recipes/{recipe_id}/seen")
    assert client.get(f"/api/books/{book_id}").json()["reading"] is None


def test_mark_book_read_and_reset(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    total = client.get(f"/api/books/{book_id}").json()["recipe_count"]

    marked = client.post(f"/api/books/{book_id}/seen")
    assert marked.status_code == 200
    assert marked.json()["recipe_count"] == total
    assert marked.json()["reading"] == {
        "mode": "book",
        "fraction": 1.0,
        "anchor": None,
        "location": None,
        "finished": True,
    }

    # Marking a book already read changes nothing — no duplicate view rows.
    assert client.post(f"/api/books/{book_id}/seen").json()["reading"]["finished"] is True

    reset = client.delete(f"/api/books/{book_id}/seen")
    assert reset.status_code == 200
    assert reset.json() == {"recipe_count": total, "reading": None}
    assert client.get(f"/api/books/{book_id}").json()["reading"] is None


def test_mark_book_read_keeps_an_existing_sitting_count(client: TestClient) -> None:
    """A recipe already read isn't re-read by marking the book: its record stands."""
    book_id = _book_id(client, "With Recipes")
    recipe_id = client.get(f"/api/books/{book_id}").json()["recipes"][0]["id"]
    first = client.post(f"/api/recipes/{recipe_id}/seen").json()

    client.post(f"/api/books/{book_id}/seen")
    after = client.post(f"/api/recipes/{recipe_id}/seen").json()
    assert after["first_viewed_at"] == first["first_viewed_at"]


def test_mark_book_read_is_per_user(
    client: TestClient, session: Session, act_as: Callable[[str], User]
) -> None:
    create_user(session, "other", "other-password")
    book_id = _book_id(client, "With Recipes")
    client.post(f"/api/books/{book_id}/seen")

    act_as("other")
    assert client.get(f"/api/books/{book_id}").json()["reading"] is None
    # Resetting one account's progress leaves the other's reading intact.
    client.delete(f"/api/books/{book_id}/seen")
    act_as("tester")
    assert client.get(f"/api/books/{book_id}").json()["reading"]["finished"] is True


def test_book_read_state_404s_for_unknown_book(client: TestClient) -> None:
    assert client.post(f"/api/books/{uuid.uuid4()}/seen").status_code == 404
    assert client.delete(f"/api/books/{uuid.uuid4()}/seen").status_code == 404


def test_reading_is_saved_and_returned(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    ids = [r["id"] for r in client.get(f"/api/books/{book_id}/recipe-index").json()]
    assert client.get(f"/api/books/{book_id}").json()["reading"] is None

    saved = client.put(
        f"/api/books/{book_id}/reading",
        json={"mode": "book", "recipe_id": ids[0], "location": "epubcfi(/6/4!/2)"},
    )
    assert saved.status_code == 200
    assert saved.json() == {
        "mode": "book",
        "fraction": 1 / 3,
        "anchor": {"id": ids[0], "name": "Recipe 0"},
        "location": "epubcfi(/6/4!/2)",
        "finished": False,
    }

    # A second report moves the position rather than adding a row.
    client.put(
        f"/api/books/{book_id}/reading",
        json={"mode": "book", "recipe_id": ids[1], "location": "epubcfi(/6/8)"},
    )
    reading = client.get(f"/api/books/{book_id}").json()["reading"]
    assert (reading["anchor"]["id"], reading["location"]) == (ids[1], "epubcfi(/6/8)")


def test_the_two_modes_share_one_position(client: TestClient) -> None:
    """Recipes read in the app carry the reader forwards, and vice versa."""
    book_id = _book_id(client, "With Recipes")
    ids = [r["id"] for r in client.get(f"/api/books/{book_id}/recipe-index").json()]

    client.put(f"/api/books/{book_id}/reading", json={"mode": "recipes", "recipe_id": ids[1]})
    body = client.get(f"/api/books/{book_id}").json()
    # Opening the pages resumes at the recipe the walk reached.
    assert body["reading"]["mode"] == "recipes"
    assert body["resume_recipe"]["id"] == ids[1]

    client.put(
        f"/api/books/{book_id}/reading",
        json={"mode": "book", "recipe_id": ids[2], "location": "epubcfi(/6/8)"},
    )
    body = client.get(f"/api/books/{book_id}").json()
    assert body["reading"]["mode"] == "book"
    assert body["resume_recipe"]["id"] == ids[2]


def test_reading_records_a_view_of_the_recipe_reached(client: TestClient) -> None:
    """The record of what has been looked at keeps being collected, unshown."""
    book_id = _book_id(client, "With Recipes")
    ids = [r["id"] for r in client.get(f"/api/books/{book_id}/recipe-index").json()]
    client.put(f"/api/books/{book_id}/reading", json={"mode": "book", "recipe_id": ids[0]})
    assert client.get("/api/home").json()["recently_read"][0]["id"] == ids[0]


def test_marking_a_book_read_finishes_its_reading(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    ids = [r["id"] for r in client.get(f"/api/books/{book_id}/recipe-index").json()]
    client.put(f"/api/books/{book_id}/reading", json={"mode": "book", "recipe_id": ids[0]})
    client.post(f"/api/books/{book_id}/seen")
    reading = client.get(f"/api/books/{book_id}").json()["reading"]
    assert (reading["fraction"], reading["finished"]) == (1.0, True)

    # Resetting the book forgets where reading got to as well.
    client.delete(f"/api/books/{book_id}/seen")
    assert client.get(f"/api/books/{book_id}").json()["reading"] is None


def test_reading_rejects_a_recipe_from_another_book(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    other_id = _book_id(client, "No Recipes Yet")
    recipe_id = client.get(f"/api/books/{book_id}/recipe-index").json()[0]["id"]
    resp = client.put(f"/api/books/{other_id}/reading", json={"recipe_id": recipe_id})
    assert resp.status_code == 404
    assert (
        client.put(f"/api/books/{uuid.uuid4()}/reading", json={"mode": "book"}).status_code == 404
    )


def test_book_detail_404_for_unknown_book(client: TestClient) -> None:
    assert client.get(f"/api/books/{uuid.uuid4()}").status_code == 404


def _library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *files: str) -> Path:
    """A temp Calibre root holding these files for the seeded "With Recipes" book."""
    book_dir = tmp_path / "Author One" / "With Recipes (1)"
    book_dir.mkdir(parents=True, exist_ok=True)
    for name in files:
        (book_dir / name).write_bytes(b"not a real book, just bytes")
    monkeypatch.setattr(settings, "calibre_library_path", tmp_path)
    return tmp_path


@pytest.fixture
def library_with_epub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _library(tmp_path, monkeypatch, "book.epub")


@pytest.fixture
def library_with_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _library(tmp_path, monkeypatch, "book.pdf")


@pytest.fixture
def library_with_both(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _library(tmp_path, monkeypatch, "book.epub", "book.pdf")


def test_has_epub_false_without_files(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    assert client.get(f"/api/books/{book_id}").json()["has_epub"] is False


def test_has_epub_true_when_present(client: TestClient, library_with_epub: Path) -> None:
    book_id = _book_id(client, "With Recipes")
    assert client.get(f"/api/books/{book_id}").json()["has_epub"] is True


def test_has_pdf_false_without_files(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    assert client.get(f"/api/books/{book_id}").json()["has_pdf"] is False


def test_has_pdf_true_when_present(client: TestClient, library_with_pdf: Path) -> None:
    body = client.get(f"/api/books/{_book_id(client, 'With Recipes')}").json()
    assert (body["has_pdf"], body["has_epub"]) == (True, False)


def test_file_served_when_epub_present(client: TestClient, library_with_epub: Path) -> None:
    book_id = _book_id(client, "With Recipes")
    resp = client.get(f"/api/books/{book_id}/file")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/epub+zip"


def test_file_served_when_pdf_present(client: TestClient, library_with_pdf: Path) -> None:
    book_id = _book_id(client, "With Recipes")
    resp = client.get(f"/api/books/{book_id}/file")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_file_prefers_the_epub_when_a_book_holds_both(
    client: TestClient, library_with_both: Path
) -> None:
    book_id = _book_id(client, "With Recipes")
    resp = client.get(f"/api/books/{book_id}/file")
    assert resp.headers["content-type"] == "application/epub+zip"


def test_file_404_when_no_readable_format(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    assert client.get(f"/api/books/{book_id}/file").status_code == 404


def test_file_404_for_unknown_book(client: TestClient) -> None:
    assert client.get(f"/api/books/{uuid.uuid4()}/file").status_code == 404


def test_recipe_index_lists_all_in_order(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    idx = client.get(f"/api/books/{book_id}/recipe-index").json()
    assert [e["name"] for e in idx] == ["Recipe 0", "Recipe 1", "Recipe 2"]
    assert all(e["is_favourite"] is False for e in idx)
    assert set(idx[0].keys()) == {"id", "name", "is_favourite", "epub_cfi"}


def test_recipe_index_reflects_favourite(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    rid = client.get(f"/api/books/{book_id}/recipe-index").json()[0]["id"]
    assert client.post(f"/api/recipes/{rid}/favourite").json()["is_favourite"] is True
    idx = {
        e["id"]: e["is_favourite"] for e in client.get(f"/api/books/{book_id}/recipe-index").json()
    }
    assert idx[rid] is True


def test_recipe_index_empty_for_bookless(client: TestClient) -> None:
    book_id = _book_id(client, "No Recipes Yet")
    assert client.get(f"/api/books/{book_id}/recipe-index").json() == []


def test_recipe_index_404_for_unknown_book(client: TestClient) -> None:
    assert client.get(f"/api/books/{uuid.uuid4()}/recipe-index").status_code == 404


def test_delete_book_removes_recipes_and_list_items(client: TestClient, session: Session) -> None:
    book_id = _book_id(client, "With Recipes")
    rid = client.get(f"/api/books/{book_id}/recipe-index").json()[0]["id"]
    client.post(f"/api/recipes/{rid}/favourite")
    store = VectorStore(session)
    store.upsert(uuid.UUID(rid), [0.1] * EMBEDDING_DIMENSIONS)

    assert client.delete(f"/api/books/{book_id}").status_code == 204

    assert client.get(f"/api/books/{book_id}").status_code == 404
    assert session.get(Recipe, uuid.UUID(rid)) is None
    assert session.scalars(select(RecipeListItem)).all() == []
    assert VectorStore(session).embedded_ids() == set()


def test_delete_book_404_for_unknown_book(client: TestClient) -> None:
    assert client.delete(f"/api/books/{uuid.uuid4()}").status_code == 404


def test_delete_book_without_exclude_records_no_exclusion(
    client: TestClient, session: Session
) -> None:
    assert client.delete(f"/api/books/{_book_id(client, 'With Recipes')}").status_code == 204
    assert session.scalars(select(CalibreExclusion)).all() == []


def test_delete_book_with_exclude_records_the_calibre_id(
    client: TestClient, session: Session
) -> None:
    book_id = _book_id(client, "With Recipes")
    assert client.delete(f"/api/books/{book_id}?exclude=true").status_code == 204

    exclusion = session.scalars(select(CalibreExclusion)).one()
    assert exclusion.calibre_id == 1
    assert exclusion.title == "With Recipes"


def test_delete_from_library_removes_the_calibre_entry_and_needs_no_exclusion(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    removed: list[int] = []
    monkeypatch.setattr("app.api.books.remove_from_library", removed.append)
    book_id = _book_id(client, "With Recipes")

    assert client.delete(f"/api/books/{book_id}?from_library=true").status_code == 204

    assert removed == [1]
    assert client.get(f"/api/books/{book_id}").status_code == 404
    # Nothing is left in Calibre to re-sync, so an exclusion would be noise.
    assert session.scalars(select(CalibreExclusion)).all() == []


def test_delete_from_library_keeps_the_book_when_calibre_refuses(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _refuse(_calibre_id: int) -> None:
        raise IngestError("calibredb failed: library is locked")

    monkeypatch.setattr("app.api.books.remove_from_library", _refuse)
    book_id = _book_id(client, "With Recipes")

    assert client.delete(f"/api/books/{book_id}?from_library=true").status_code == 502
    # A half-done delete is worse than none: the book survives intact.
    assert client.get(f"/api/books/{book_id}").status_code == 200


def test_delete_cannot_both_exclude_and_remove_from_the_library(client: TestClient) -> None:
    book_id = _book_id(client, "With Recipes")
    res = client.delete(f"/api/books/{book_id}?exclude=true&from_library=true")

    assert res.status_code == 422
    assert client.get(f"/api/books/{book_id}").status_code == 200
