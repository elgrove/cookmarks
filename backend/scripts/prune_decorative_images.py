"""Clear recipe images that are page furniture rather than dish photos.

Extraction screens these out as it goes (`find_decorative_images`), so this only
cleans up books extracted before the screen existed. Re-runnable and idempotent.

    cd backend && uv run python -m scripts.prune_decorative_images [--dry-run]
"""

import argparse
import logging

from sqlalchemy import select

from app.db import SessionLocal
from app.epub import epub_path
from app.models.book import Book
from app.services.extraction.utils import find_decorative_images

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    pruned = 0
    with SessionLocal() as session:
        for book in session.scalars(select(Book).order_by(Book.title)):
            recipes = [r for r in book.recipes if r.image is not None]
            if not recipes:
                continue
            # An empty image reference serves nothing; v1 data carries a few hundred.
            hits = [r for r in recipes if not r.image]
            named = [r.image for r in recipes if r.image]
            epub = epub_path(book)
            if epub is None:
                logger.warning(f"No EPUB for {book.title}, skipping {len(named)} image(s)")
            else:
                decorative = find_decorative_images(epub, named)
                hits += [r for r in recipes if r.image and r.image in decorative]
            if not hits:
                continue
            pruned += len(hits)
            logger.info(f"{book.title}: {len(hits)}/{len(recipes)} image(s) decorative")
            if not args.dry_run:
                for recipe in hits:
                    recipe.image = None
        if args.dry_run:
            session.rollback()
        else:
            session.commit()

    verb = "would clear" if args.dry_run else "cleared"
    print(f"{verb.capitalize()} {pruned} decorative recipe image(s).")


if __name__ == "__main__":
    main()
