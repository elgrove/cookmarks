"""Book-level keyword generation — the AI layer that tags a whole cookbook.

A book's keywords (cuisine/theme/style) are AI-generated from a digest of the book's
metadata and the recipes already extracted from it, then drawn from the same shared
`Keyword` vocabulary as recipes. The extraction task generates them as a best-effort
step once recipes are saved; `scripts/backfill_book_keywords.py` fills any gaps.
"""

import logging
import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.book import Book
from app.models.recipe import Recipe
from app.services.ai import get_ai_provider
from app.services.keywords import get_or_create_keyword

logger = logging.getLogger(__name__)

# Digest bounds — keep the prompt focused and cheap regardless of book size.
_MAX_DESCRIPTION_CHARS = 1500
_MAX_RECIPE_NAMES = 60
_MAX_RECIPE_TAGS = 30

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _plain_text(html: str) -> str:
    """Calibre descriptions are HTML; flatten to readable text for the prompt."""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", html)).strip()


def book_keyword_digest(session: Session, book: Book) -> str:
    """Build the AI input describing the whole book: its metadata plus a sample of
    recipe names and the most common recipe-level tags — enough signal to infer the
    book's cuisine, theme and style even when the blurb is thin."""
    recipes = session.scalars(
        select(Recipe)
        .where(Recipe.book_id == book.id)
        .order_by(Recipe.order)
        .options(selectinload(Recipe.keywords))
    ).all()

    lines = [f"Title: {book.title}", f"Author: {book.author}"]
    description = _plain_text(book.description)
    if description:
        lines.append(f"About: {description[:_MAX_DESCRIPTION_CHARS]}")

    if recipes:
        names = [r.name for r in recipes[:_MAX_RECIPE_NAMES]]
        lines.append(f"Recipes ({len(recipes)} total), a sample: {'; '.join(names)}")

        tag_counts = Counter(k.name for r in recipes for k in r.keywords)
        if tag_counts:
            top = "; ".join(f"{name} ({n})" for name, n in tag_counts.most_common(_MAX_RECIPE_TAGS))
            lines.append(f"Most common recipe tags: {top}")

    return "\n".join(lines)


def generate_book_keywords(session: Session, book: Book) -> list[str]:
    """Generate and assign this book's keywords, replacing any it already has. A
    no-op (returns []) when no AI provider is configured or the model gives nothing
    usable, so it never wipes good tags on a transient empty response. Writes ride
    the caller's transaction — the caller commits."""
    provider = get_ai_provider(session)
    if provider is None:
        logger.debug("No AI provider configured; skipping book-keyword generation")
        return []

    digest = book_keyword_digest(session, book)
    try:
        names, _usage = provider.generate_book_keywords(digest)
    except Exception:
        logger.exception(f"Book-keyword generation failed for {book.title}")
        return []

    if not names:
        logger.info(f"No book keywords generated for {book.title}")
        return []

    book.keywords = [get_or_create_keyword(session, name) for name in names]
    session.flush()
    logger.info(f"Generated {len(names)} book keyword(s) for {book.title}")
    return names
