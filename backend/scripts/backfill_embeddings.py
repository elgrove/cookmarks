"""Embed any recipes that have no stored vector yet.

The import script carries v1's vectors across and extraction embeds as it goes, so
this only fills gaps — recipes extracted before a provider was configured, or any
left behind. Re-runnable; embeds only what's missing.

    cd backend && uv run python -m scripts.backfill_embeddings
"""

import logging

from app.db import SessionLocal
from app.services.embeddings import backfill


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with SessionLocal() as session:
        count = backfill(session)
    print(f"Embedded {count} recipe(s) that were missing a vector.")


if __name__ == "__main__":
    main()
