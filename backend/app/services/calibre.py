"""Read books live from a Calibre library and import them into the v2 DB.

Calibre is a read-only source of new books: we read its catalogue
(`<library>/metadata.db`), select the cookbooks (a configurable tag plus a list of
formats, defaulting to "Food" and EPUB or PDF) and create `Book` rows by `calibre_id`
only when that id is not already present and not excluded. After import Cookmarks owns
its metadata and collection state — synchronisation never updates or deletes an
existing book, including its path and bibliographic fields.

The read layer (`read_books`) takes an open connection so it runs against either a
real metadata.db or an in-memory fixture; `read_calibre_books` wraps it with the
file-open. The import (`sync_calibre`) takes already-read records, so it is
decoupled from sqlite entirely. The later operator endpoint reuses both.
"""

import logging
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Book, CalibreExclusion
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

# v1's proven selection query, with the tag and format parameterised. Columns v2
# doesn't model (e.g. the EPUB filename) are dropped; `b.path` is library-relative.
_SELECT_BOOKS = """
    SELECT DISTINCT
        b.id,
        b.title,
        b.path,
        b.pubdate,
        b.timestamp,
        (SELECT val FROM identifiers WHERE book = b.id AND type = 'isbn' LIMIT 1) AS isbn,
        (SELECT GROUP_CONCAT(a.name, ' & ')
           FROM authors a
           JOIN books_authors_link bal ON a.id = bal.author
          WHERE bal.book = b.id) AS authors,
        (SELECT text FROM comments WHERE book = b.id) AS description
    FROM books b
    JOIN books_tags_link btl ON b.id = btl.book
    JOIN tags t ON btl.tag = t.id
    JOIN data d ON b.id = d.book
    WHERE t.name = ? AND d.format IN ({formats})
    ORDER BY b.title
"""


@dataclass(frozen=True)
class CalibreBook:
    """One cookbook as read from Calibre, parsed into v2's shape. `path` is relative
    to the library root, exactly as Calibre stores it."""

    calibre_id: int
    title: str
    author: str
    isbn: str
    pubdate: date | None
    description: str
    path: str
    calibre_added_at: datetime | None


@dataclass(frozen=True)
class SyncResult:
    """Outcome of an import, by book title. `created` books are new rows; `skipped`
    ones already existed and were left byte-for-byte unchanged; `excluded` ones are
    on the exclusion list and were skipped."""

    created: list[str]
    skipped: list[str]
    excluded: list[str]


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.split()[0], "%Y-%m-%d").date()
    except (ValueError, IndexError):
        logger.warning("Could not parse Calibre pubdate %r", value)
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Could not parse Calibre timestamp %r", value)
        return None


def open_calibre_db(library_path: Path) -> sqlite3.Connection:
    """Open `<library_path>/metadata.db` read-only. Raises FileNotFoundError if absent."""
    db_path = Path(library_path) / "metadata.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Calibre database not found at {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def read_books(conn: sqlite3.Connection, *, tag: str, book_formats: list[str]) -> list[CalibreBook]:
    """Run the selection query over an open Calibre connection. A book holding several
    of the wanted formats still yields one row — the query selects distinct books."""
    if not book_formats:
        # `IN ()` is false for every row, which would import nothing.
        raise ValueError("at least one book format must be selected")
    query = _SELECT_BOOKS.format(formats=", ".join("?" * len(book_formats)))
    rows = conn.execute(query, (tag, *book_formats)).fetchall()
    books = [
        CalibreBook(
            calibre_id=row["id"],
            title=row["title"],
            author=row["authors"] or "",
            isbn=row["isbn"] or "",
            pubdate=_parse_date(row["pubdate"]),
            description=row["description"] or "",
            path=row["path"],
            calibre_added_at=_parse_datetime(row["timestamp"]),
        )
        for row in rows
    ]
    logger.info("Read %d book(s) from Calibre (tag=%r, formats=%r)", len(books), tag, book_formats)
    return books


def read_calibre_books(
    library_path: Path, *, tag: str, book_formats: list[str]
) -> list[CalibreBook]:
    """Open the library's metadata.db read-only and read the selected books."""
    conn = open_calibre_db(library_path)
    try:
        return read_books(conn, tag=tag, book_formats=book_formats)
    finally:
        conn.close()


def delete_books(session: Session, books: Iterable[Book]) -> None:
    """Delete books and everything hanging off them. The row delete cascades to recipes,
    runs and link tables through the schema's foreign keys, but the vec0 embedding table
    has none — so this is the single place that purges those alongside. Does not commit."""
    books = list(books)
    if not books:
        return
    store = VectorStore(session)
    for book in books:
        store.delete(recipe.id for recipe in book.recipes)
        session.delete(book)


def sync_calibre(
    session: Session,
    calibre_books: list[CalibreBook],
) -> SyncResult:
    """Import Calibre books by `calibre_id`, creating only unseen, non-excluded ids.
    Existing books are reported as skipped and left byte-for-byte unchanged in
    Cookmarks — including path and bibliographic fields — so Cookmarks owns its
    metadata after import. Ids on the `CalibreExclusion` list are skipped entirely,
    so a deleted book never comes back. Books absent from `calibre_books` stay in
    Cookmarks untouched; repeated imports are idempotent."""
    existing_titles: dict[int, str] = {
        row[0]: row[1] for row in session.execute(select(Book.calibre_id, Book.title)).all()
    }
    existing_ids = set(existing_titles)
    excluded_ids = set(session.scalars(select(CalibreExclusion.calibre_id)).all())
    created: list[str] = []
    skipped: list[str] = []
    excluded: list[str] = []

    for cb in calibre_books:
        if cb.calibre_id in excluded_ids:
            excluded.append(cb.title)
            continue
        if cb.calibre_id in existing_ids:
            skipped.append(existing_titles.get(cb.calibre_id, cb.title))
            continue
        session.add(
            Book(
                calibre_id=cb.calibre_id,
                title=cb.title,
                author=cb.author,
                isbn=cb.isbn,
                pubdate=cb.pubdate,
                description=cb.description,
                path=cb.path,
                calibre_added_at=cb.calibre_added_at,
            )
        )
        created.append(cb.title)
        existing_ids.add(cb.calibre_id)

    session.commit()
    logger.info(
        "Calibre import: %d created, %d skipped, %d excluded",
        len(created),
        len(skipped),
        len(excluded),
    )
    return SyncResult(
        created=created,
        skipped=skipped,
        excluded=excluded,
    )
