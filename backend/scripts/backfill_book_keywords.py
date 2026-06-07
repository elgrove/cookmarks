"""Generate book-level keywords for extracted books that don't have any yet.

Extraction tags each book as it finishes, so this only fills gaps — books extracted
before book keywords existed, or any left untagged. Re-runnable; by default it skips
books that already have keywords (pass --all to regenerate every extracted book).

    cd backend && uv run python -m scripts.backfill_book_keywords
"""

import argparse
import logging

from app.tasks.book_keywords import backfill_book_keywords


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill AI-generated book keywords.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="regenerate keywords even for books that already have some",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    tagged = backfill_book_keywords(regenerate=args.all)
    print(f"Tagged {tagged} book(s) with keywords.")


if __name__ == "__main__":
    main()
