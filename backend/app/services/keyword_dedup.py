"""AI-assisted deduplication for the shared keyword vocabulary.

The generic vocabulary service prepares and validates merge maps. This module keeps
the keyword-specific vocabulary query, AI request, and association reassignment.
"""

import logging
from dataclasses import replace

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.book import book_keywords
from app.models.recipe import Keyword, recipe_keywords
from app.services.ai import AIProvider, get_ai_provider
from app.services.keywords import get_or_create_keyword
from app.services.vocabulary_dedup import (
    DEFAULT_CANDIDATE_WINDOW,
    VocabularyDedupResult,
)
from app.services.vocabulary_dedup import (
    propose_merges as propose_vocabulary_merges,
)

logger = logging.getLogger(__name__)

# This remains a keyword setting. A future vocabulary can choose a smaller window
# without copying the generic rotation implementation.
DEDUP_CANDIDATE_WINDOW = DEFAULT_CANDIDATE_WINDOW

DedupResult = VocabularyDedupResult


def propose_merges(
    provider: AIProvider, names: list[str], cursor: str | None = None
) -> tuple[dict[str, str], DedupResult]:
    """Ask the keyword model through the reusable vocabulary-deduplication flow."""
    return propose_vocabulary_merges(
        names,
        cursor,
        provider.deduplicate_keywords,
        candidate_window=DEDUP_CANDIDATE_WINDOW,
        target_is_valid=lambda _target, _vocabulary: True,
    )


def apply_merges(session: Session, merges: dict[str, str]) -> int:
    """Move recipe and book associations to each canonical keyword, then delete the
    duplicate rows. Writes stay in the caller's transaction."""
    applied = 0
    for original, canonical in merges.items():
        duplicate = session.scalar(
            select(Keyword)
            .where(Keyword.name == original)
            .options(selectinload(Keyword.recipes), selectinload(Keyword.books))
        )
        if duplicate is None:
            continue

        target = get_or_create_keyword(session, canonical)
        for recipe in list(duplicate.recipes):
            if target not in recipe.keywords:
                recipe.keywords.append(target)
            recipe.keywords.remove(duplicate)
        for book in list(duplicate.books):
            if target not in book.keywords:
                book.keywords.append(target)
            book.keywords.remove(duplicate)

        session.delete(duplicate)
        logger.info(f"Merged {original!r} into {canonical!r}")
        applied += 1

    session.flush()
    return applied


def _vocabulary_by_usage(session: Session) -> list[str]:
    """Return keyword names most-used first, then alphabetically."""
    uses: dict[str, int] = {}
    for table in (recipe_keywords, book_keywords):
        rows = session.execute(
            select(Keyword.name, func.count())
            .join(table, table.c.keyword_id == Keyword.id)
            .group_by(Keyword.id)
        ).all()
        for name, count in rows:
            uses[name] = uses.get(name, 0) + count
    names = session.scalars(select(Keyword.name)).all()
    return sorted(names, key=lambda name: (-uses.get(name, 0), name))


def deduplicate_keywords(session: Session, cursor: str | None = None) -> DedupResult:
    """Run one keyword pass in the caller's transaction."""
    provider = get_ai_provider(session)
    if provider is None:
        logger.debug("No AI provider configured; skipping keyword dedup")
        return DedupResult()

    names = _vocabulary_by_usage(session)
    if not names:
        return DedupResult()

    merges, stats = propose_merges(provider, names, cursor)
    applied = apply_merges(session, merges)
    logger.info(
        f"Keyword dedup: applied {applied} merge(s) "
        f"({stats.pre_merges} deterministic, {stats.ai_merges} semantic"
        f"{', reply truncated' if stats.ai_truncated else ''}), "
        f"removed {applied} keyword(s) from a vocabulary of {len(names)} "
        f"over {stats.candidates} candidate(s)"
    )
    return replace(stats, merges_applied=applied, vocabulary_removed=applied)
