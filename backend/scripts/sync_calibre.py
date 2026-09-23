"""Import Book rows live from the Calibre library.

Reads `<library>/metadata.db` and creates books by `calibre_id` only when unseen and
not excluded. Existing books are left unchanged — Cookmarks owns its metadata after
import. Re-runnable and idempotent.

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
from app.services.calibre import read_calibre_books, sync_calibre


def main() -> None:
    parser = argparse.ArgumentParser(description="Import books from the Calibre library.")
    parser.add_argument(
        "--library",
        type=Path,
        default=settings.calibre_library_path,
        help="Calibre library root (contains metadata.db). Defaults to the configured path.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    books = read_calibre_books(
        args.library, tag=settings.calibre_sync_tag, book_formats=settings.calibre_sync_formats
    )
    with SessionLocal() as session:
        result = sync_calibre(session, books)

    print(
        f"{len(result.created)} created, {len(result.skipped)} skipped, "
        f"{len(result.excluded)} excluded."
    )


if __name__ == "__main__":
    main()
