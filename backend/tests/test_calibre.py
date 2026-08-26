import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Book, CalibreExclusion, Recipe
from app.services.calibre import CalibreBook, read_books, read_calibre_books, sync_calibre
from app.services.vector_store import EMBEDDING_DIMENSIONS, VectorStore

FIXTURE_SQL = Path(__file__).parent / "fixtures" / "calibre_metadata.sql"
FOOD = "Food"
EPUB = ["EPUB"]
EPUB_PDF = ["EPUB", "PDF"]


@pytest.fixture
def calibre_conn() -> Iterator[sqlite3.Connection]:
    """An in-memory Calibre metadata.db loaded from the SQL fixture."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(FIXTURE_SQL.read_text())
    yield conn
    conn.close()


def _make_book(calibre_id: int, title: str, **overrides: object) -> CalibreBook:
    defaults: dict[str, object] = {
        "author": "An Author",
        "isbn": "",
        "pubdate": None,
        "description": "",
        "path": f"An Author/{title} ({calibre_id})",
        "calibre_added_at": None,
    }
    defaults.update(overrides)
    return CalibreBook(calibre_id=calibre_id, title=title, **defaults)  # type: ignore[arg-type]


# --- read layer -----------------------------------------------------------------


def test_read_books_selects_only_matching_tag_and_format(calibre_conn: sqlite3.Connection) -> None:
    books = read_books(calibre_conn, tag=FOOD, book_formats=EPUB)
    # 300 is tagged Fiction; 400 has only a PDF format — both excluded.
    assert {b.calibre_id for b in books} == {100, 200, 500, 600}


def test_read_books_parses_full_metadata(calibre_conn: sqlite3.Connection) -> None:
    by_id = {b.calibre_id: b for b in read_books(calibre_conn, tag=FOOD, book_formats=EPUB)}
    book = by_id[100]
    assert book.title == "Salt, Fat, Acid, Heat"
    assert book.author == "Samin Nosrat"
    assert book.isbn == "9781476753836"
    assert book.pubdate == date(2017, 4, 25)
    assert book.description == "Mastering the elements of good cooking."
    assert book.path == "Samin Nosrat/Salt, Fat, Acid, Heat (100)"
    assert book.calibre_added_at is not None and book.calibre_added_at.year == 2020


def test_read_books_joins_multiple_authors_and_defaults_blanks(
    calibre_conn: sqlite3.Connection,
) -> None:
    by_id = {b.calibre_id: b for b in read_books(calibre_conn, tag=FOOD, book_formats=EPUB)}
    book = by_id[200]
    assert book.author == "Neelam Batra & Jeyashri Suresh"
    assert book.isbn == ""  # no isbn identifier
    assert book.description == ""  # no comments row
    assert book.pubdate is None  # NULL pubdate


def test_read_books_tolerates_unparsable_pubdate(calibre_conn: sqlite3.Connection) -> None:
    by_id = {b.calibre_id: b for b in read_books(calibre_conn, tag=FOOD, book_formats=EPUB)}
    assert by_id[500].pubdate is None  # 'not-a-real-date' degrades to None, not a crash


def test_read_books_filter_is_configurable(calibre_conn: sqlite3.Connection) -> None:
    fiction = read_books(calibre_conn, tag="Fiction", book_formats=EPUB)
    assert {b.calibre_id for b in fiction} == {300}
    assert read_books(calibre_conn, tag=FOOD, book_formats=["MOBI"]) == []


def test_read_books_selects_every_wanted_format(calibre_conn: sqlite3.Connection) -> None:
    books = read_books(calibre_conn, tag=FOOD, book_formats=EPUB_PDF)
    # 400 is PDF-only and 600 holds both; 300 is still Fiction.
    assert {b.calibre_id for b in books} == {100, 200, 400, 500, 600}


def test_a_book_in_several_formats_is_read_once(calibre_conn: sqlite3.Connection) -> None:
    ids = [b.calibre_id for b in read_books(calibre_conn, tag=FOOD, book_formats=EPUB_PDF)]
    assert ids.count(600) == 1


def test_read_calibre_books_from_file(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "metadata.db")
    conn.executescript(FIXTURE_SQL.read_text())
    conn.commit()
    conn.close()
    books = read_calibre_books(tmp_path, tag=FOOD, book_formats=EPUB)
    assert {b.calibre_id for b in books} == {100, 200, 500, 600}


def test_read_calibre_books_missing_db_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_calibre_books(tmp_path, tag=FOOD, book_formats=EPUB)


# --- reconcile layer (seeded session has books calibre_id 1 and 2) ---------------


def test_sync_creates_new_books(session: Session) -> None:
    result = sync_calibre(session, [_make_book(100, "Brand New", path="x/Brand New (100)")])
    assert result.created == ["Brand New"]
    created = session.scalars(select(Book).where(Book.calibre_id == 100)).one()
    assert created.path == "x/Brand New (100)"


def test_sync_updates_in_place_preserving_recipes_and_keywords(session: Session) -> None:
    before = session.scalars(select(Book).where(Book.calibre_id == 1)).one()
    book_id, recipe_count, keyword_count = before.id, len(before.recipes), len(before.keywords)
    assert recipe_count == 3 and keyword_count == 2  # guard the fixture's premise

    result = sync_calibre(
        session,
        [_make_book(1, "With Recipes, 2nd ed.", author="Revised Author", path="new/path (1)")],
    )
    assert result.updated == ["With Recipes, 2nd ed."]
    assert result.created == []

    after = session.scalars(select(Book).where(Book.calibre_id == 1)).one()
    assert after.id == book_id  # same row — stable UUID, not wipe-and-recreate
    assert after.title == "With Recipes, 2nd ed."
    assert after.author == "Revised Author"
    assert after.path == "new/path (1)"
    assert len(after.recipes) == recipe_count  # recipes/favourites survive
    assert len(after.keywords) == keyword_count  # AI keywords untouched


def test_sync_reports_orphans_without_deleting(session: Session) -> None:
    # A selection that omits both seeded books — they orphan but must survive intact.
    result = sync_calibre(session, [_make_book(999, "Unrelated")])
    assert set(result.orphaned) == {"With Recipes", "No Recipes Yet"}

    orphan = session.scalars(select(Book).where(Book.calibre_id == 1)).one()
    assert len(orphan.recipes) == 3  # nothing cascaded


def test_sync_deletes_books_gone_from_the_library(session: Session) -> None:
    """A book whose calibre_id has left the library goes with its recipes and their
    embeddings; one that is merely outside the tag/format selection is only reported."""
    doomed = session.scalars(select(Book).where(Book.calibre_id == 1)).one()
    recipe_ids = [recipe.id for recipe in doomed.recipes]
    assert len(recipe_ids) == 3  # guard the fixture's premise
    store = VectorStore(session)
    for recipe_id in recipe_ids:
        store.upsert(recipe_id, [0.1] * EMBEDDING_DIMENSIONS)

    # Book 1 is gone from Calibre; book 2 is still there, just outside the selection.
    result = sync_calibre(session, [_make_book(999, "Unrelated")], library_ids={2, 999})

    assert result.deleted == ["With Recipes"]
    assert result.orphaned == ["No Recipes Yet"]
    assert session.scalars(select(Book).where(Book.calibre_id == 1)).all() == []
    assert session.scalars(select(Recipe).where(Recipe.id.in_(recipe_ids))).all() == []
    assert VectorStore(session).embedded_ids().isdisjoint(recipe_ids)
    assert session.scalars(select(Book).where(Book.calibre_id == 2)).one().title == "No Recipes Yet"


def test_sync_skips_excluded_books(session: Session) -> None:
    """An excluded Calibre id is never re-created, however many times the sync runs."""
    session.add(CalibreExclusion(calibre_id=100, title="Brand New"))
    session.commit()

    result = sync_calibre(session, [_make_book(100, "Brand New"), _make_book(101, "Allowed")])

    assert result.excluded == ["Brand New"]
    assert result.created == ["Allowed"]
    assert session.scalars(select(Book).where(Book.calibre_id == 100)).all() == []


def test_sync_is_idempotent(session: Session) -> None:
    books = [_make_book(1, "With Recipes"), _make_book(2, "No Recipes Yet")]
    sync_calibre(session, books)
    second = sync_calibre(session, books)
    assert second.created == []
    assert sorted(second.updated) == ["No Recipes Yet", "With Recipes"]
    assert second.orphaned == []
    assert len(session.scalars(select(Book).where(Book.calibre_id == 1)).all()) == 1


def test_read_then_sync_end_to_end(calibre_conn: sqlite3.Connection, session: Session) -> None:
    books = read_books(calibre_conn, tag=FOOD, book_formats=EPUB)
    result = sync_calibre(session, books)
    assert set(result.created) == {
        "Salt, Fat, Acid, Heat",
        "1,000 Indian Recipes",
        "Cooking With Bad Dates",
        "Cookbook (Both Formats)",
    }
    assert set(result.orphaned) == {"With Recipes", "No Recipes Yet"}
    assert len(session.scalars(select(Book).where(Book.calibre_id == 1)).one().recipes) == 3
