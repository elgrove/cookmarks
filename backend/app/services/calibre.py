"""Read books live from a Calibre library and reconcile them into the v2 DB.

Calibre keeps its catalogue in `<library>/metadata.db`. We read it (never write),
select the cookbooks (a configurable tag plus a list of formats, defaulting to "Food"
and EPUB or PDF) and upsert `Book` rows by `calibre_id`. `path` is treated as a
refreshable pointer.
Recipe identity and organisation (favourites, lists, AI keywords) hang off stable
recipe UUIDs and are never touched for a book that is still in the library. A book
whose `calibre_id` has left the library altogether is deleted, cascading to its
recipes; one that is merely outside the tag/format selection is reported as orphaned
and left alone, so untagging a book can't silently destroy its recipes.

The read layer (`read_books`) takes an open connection so it runs against either a
real metadata.db or an in-memory fixture; `read_calibre_books` wraps it with the
file-open. The reconcile (`sync_calibre`) takes already-read records, so it is
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
    """Outcome of a sync, by book title. `deleted` books are gone from the Calibre
    library entirely (removed here too, recipes and all); `orphaned` ones are still in
    the library but outside the tag/format selection — reported and left untouched;
    `excluded` ones are on the exclusion list and were skipped."""

    created: list[str]
    updated: list[str]
    orphaned: list[str]
    deleted: list[str]
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
        # `IN ()` is false for every row, which would report the whole library orphaned.
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


def read_library_book_ids(library_path: Path) -> set[int]:
    """Every book id in the library, whatever its tags or formats. Sync uses this to
    tell "deleted from Calibre" (gone from here) apart from "no longer a cookbook"
    (still here, outside the tag/format selection)."""
    conn = open_calibre_db(library_path)
    try:
        return {row[0] for row in conn.execute("SELECT id FROM books")}
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
    *,
    library_ids: set[int] | None = None,
) -> SyncResult:
    """Upsert Calibre books by `calibre_id`, refreshing bibliographic fields and the
    `path` pointer. Recipes, list membership and keywords are never touched on a book
    that survives. Ids on the `CalibreExclusion` list are skipped entirely, so a book
    deleted-and-excluded in the app never comes back.

    Books in v2 but absent from `calibre_books` are reported as orphaned. Pass
    `library_ids` (every id in the library) to also delete the ones that have left
    Calibre entirely — they cascade to their recipes, whose embeddings are purged
    alongside since the vec0 table has no foreign key. Without it nothing is deleted."""
    existing = {book.calibre_id: book for book in session.scalars(select(Book)).all()}
    excluded_ids = set(session.scalars(select(CalibreExclusion.calibre_id)).all())
    created: list[str] = []
    updated: list[str] = []
    excluded: list[str] = []
    seen: set[int] = set()

    for cb in calibre_books:
        if cb.calibre_id in excluded_ids:
            excluded.append(cb.title)
            continue
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

    # An excluded id that somehow still has a row is reported as excluded, not orphaned.
    missing = [
        book for cid, book in existing.items() if cid not in seen and cid not in excluded_ids
    ]
    gone = [] if library_ids is None else [b for b in missing if b.calibre_id not in library_ids]
    gone_ids = {book.calibre_id for book in gone}
    orphaned = [book.title for book in missing if book.calibre_id not in gone_ids]

    delete_books(session, gone)
    deleted = [book.title for book in gone]

    session.commit()
    logger.info(
        "Calibre sync: %d created, %d updated, %d orphaned, %d deleted, %d excluded",
        len(created),
        len(updated),
        len(orphaned),
        len(deleted),
        len(excluded),
    )
    return SyncResult(
        created=created,
        updated=updated,
        orphaned=orphaned,
        deleted=deleted,
        excluded=excluded,
    )
