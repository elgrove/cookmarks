"""Rebuild the FTS5 recipe search index from source data.

The index is created and backfilled by the migration, and kept current by triggers
after that, so this is the recovery path — if the index ever drifts, or after
restoring a database, run it to rebuild every row in one pass.

    cd backend && uv run python -m scripts.reindex_search
"""

import logging

from app.db import SessionLocal
from app.services.search_index import reindex_all


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with SessionLocal() as session:
        count = reindex_all(session)
    print(f"Indexed {count} recipe(s) into the search index.")


if __name__ == "__main__":
    main()
