"""Read books live from a Calibre library and reconcile them into the v2 DB.

Calibre keeps its catalogue in `<library>/metadata.db`. We read it (never write),
select the cookbooks (a configurable tag + format, defaulting to v1's "Food"/EPUB)
and upsert `Book` rows by `calibre_id`. `path` is treated as a refreshable pointer.
Recipe identity and organisation (favourites, lists, AI keywords) hang off stable
recipe UUIDs and are never touched; books that have left the Calibre selection are
reported, not deleted.

The read layer (`read_books`) takes an open connection so it runs against either a
real metadata.db or an in-memory fixture; `read_calibre_books` wraps it with the
file-open. The reconcile (`sync_calibre`) takes already-read records, so it is
decoupled from sqlite entirely. The later operator endpoint reuses both.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Book

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
    WHERE t.name = ? AND d.format = ?
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
    """Outcome of a sync, by book title. Orphans are books present in v2 whose
    `calibre_id` is absent from the current Calibre selection — left untouched."""

    created: list[str]
    updated: list[str]
    orphaned: list[str]


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


def read_books(conn: sqlite3.Connection, *, tag: str, book_format: str) -> list[CalibreBook]:
    """Run the selection query over an open Calibre connection."""
    rows = conn.execute(_SELECT_BOOKS, (tag, book_format)).fetchall()
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
    logger.info("Read %d book(s) from Calibre (tag=%r, format=%r)", len(books), tag, book_format)
    return books


def read_calibre_books(library_path: Path, *, tag: str, book_format: str) -> list[CalibreBook]:
    """Open the library's metadata.db read-only and read the selected books."""
    conn = open_calibre_db(library_path)
    try:
        return read_books(conn, tag=tag, book_format=book_format)
    finally:
        conn.close()


def sync_calibre(session: Session, calibre_books: list[CalibreBook]) -> SyncResult:
    """Upsert Calibre books by `calibre_id`, refreshing bibliographic fields and the
    `path` pointer. Recipes, list membership and keywords are never touched. Books in
    v2 but absent from `calibre_books` are reported as orphaned, not deleted."""
    existing = {book.calibre_id: book for book in session.scalars(select(Book)).all()}
    created: list[str] = []
    updated: list[str] = []
    seen: set[int] = set()

    for cb in calibre_books:
        seen.add(cb.calibre_id)
        book = existing.get(cb.calibre_id)
        if book is None:
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
        else:
            book.title = cb.title
            book.author = cb.author
            book.isbn = cb.isbn
            book.pubdate = cb.pubdate
            book.description = cb.description
            book.path = cb.path
            book.calibre_added_at = cb.calibre_added_at
            updated.append(cb.title)

    orphaned = [book.title for cid, book in existing.items() if cid not in seen]
    session.commit()
    logger.info(
        "Calibre sync: %d created, %d updated, %d orphaned",
        len(created),
        len(updated),
        len(orphaned),
    )
    return SyncResult(created=created, updated=updated, orphaned=orphaned)
