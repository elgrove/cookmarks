"""Sync Book rows live from the Calibre library.

Reads `<library>/metadata.db`, upserts books by `calibre_id`, and refreshes their
bibliographic fields and the `path` pointer. Recipe identity and organisation
(favourites, lists, AI keywords) are never touched for a book that survives. Books
gone from the library are deleted with their recipes (`--no-delete` to keep them);
books still in the library but outside the selection are reported. Re-runnable.

The selection (tag + format) is configured via COOKMARKS_CALIBRE_SYNC_TAG /
_FORMAT (default "Food"/EPUB); the library path via COOKMARKS_CALIBRE_LIBRARY_PATH
or the --library override.

    cd backend && uv run python -m scripts.sync_calibre [--library PATH]
"""

import argparse
import logging
from pathlib import Path

from app.config import settings
from app.db import SessionLocal
from app.services.calibre import read_calibre_books, read_library_book_ids, sync_calibre


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync books from the Calibre library.")
    parser.add_argument(
        "--library",
        type=Path,
        default=settings.calibre_library_path,
        help="Calibre library root (contains metadata.db). Defaults to the configured path.",
    )
    parser.add_argument(
        "--no-delete",
        action="store_true",
        help="Keep books that have left the Calibre library instead of deleting them.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    books = read_calibre_books(
        args.library, tag=settings.calibre_sync_tag, book_format=settings.calibre_sync_format
    )
    library_ids = None if args.no_delete else read_library_book_ids(args.library)
    with SessionLocal() as session:
        result = sync_calibre(session, books, library_ids=library_ids)

    print(
        f"{len(result.created)} created, {len(result.updated)} updated, "
        f"{len(result.orphaned)} orphaned, {len(result.deleted)} deleted, "
        f"{len(result.excluded)} excluded."
    )
    if result.orphaned:
        print("Orphaned (still in Calibre, outside the tag/format selection — left untouched):")
        for title in result.orphaned:
            print(f"  - {title}")
    if result.deleted:
        print("Deleted (gone from the Calibre library, removed with their recipes):")
        for title in result.deleted:
            print(f"  - {title}")


if __name__ == "__main__":
    main()
