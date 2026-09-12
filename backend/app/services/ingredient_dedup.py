"""AI-assisted deduplication for canonical ingredients.

The generic vocabulary service prepares and validates merge maps. This module keeps
the ingredient-specific vocabulary query, AI request, and recipe-fact reassignment.
"""

import logging
from dataclasses import replace

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.ingredient import CanonicalIngredient, RecipeIngredient
from app.services.ai import AIProvider, get_ai_provider
from app.services.recipe_facts import get_or_create_canonical_ingredient
from app.services.vocabulary_dedup import (
    DEFAULT_CANDIDATE_WINDOW,
    VocabularyDedupResult,
)
from app.services.vocabulary_dedup import (
    propose_merges as propose_vocabulary_merges,
)

logger = logging.getLogger(__name__)

# This remains an ingredient setting. A future vocabulary can choose a smaller window
# without copying the generic rotation implementation.
DEDUP_CANDIDATE_WINDOW = DEFAULT_CANDIDATE_WINDOW

DedupResult = VocabularyDedupResult


def propose_merges(
    provider: AIProvider, names: list[str], cursor: str | None = None
) -> tuple[dict[str, str], DedupResult]:
    """Ask the ingredient model through the reusable vocabulary-deduplication flow."""
    return propose_vocabulary_merges(
        names,
        cursor,
        provider.deduplicate_ingredients,
        candidate_window=DEDUP_CANDIDATE_WINDOW,
    )


def apply_merges(session: Session, merges: dict[str, str]) -> int:
    """Repoint recipe ingredients, then delete each duplicate canonical row."""
    applied = 0
    for original, canonical in merges.items():
        duplicate = session.scalar(
            select(CanonicalIngredient).where(CanonicalIngredient.name == original)
        )
        if duplicate is None:
            continue

        target = get_or_create_canonical_ingredient(session, canonical)
        if target.id == duplicate.id:
            continue
        session.execute(
            update(RecipeIngredient)
            .where(RecipeIngredient.canonical_ingredient_id == duplicate.id)
            .values(canonical_ingredient_id=target.id)
        )
        session.delete(duplicate)
        logger.info(f"Merged canonical ingredient {original!r} into {target.name!r}")
        applied += 1

    session.flush()
    return applied


def _vocabulary_by_usage(session: Session) -> list[str]:
    """Return canonical ingredient names most-linked first, then alphabetically."""
    rows = session.execute(
        select(CanonicalIngredient.name, func.count(RecipeIngredient.id))
        .outerjoin(
            RecipeIngredient,
            RecipeIngredient.canonical_ingredient_id == CanonicalIngredient.id,
        )
        .group_by(CanonicalIngredient.id)
    ).all()
    return [name for name, _count in sorted(rows, key=lambda row: (-row[1], row[0]))]


def deduplicate_ingredients(session: Session, cursor: str | None = None) -> DedupResult:
    """Run one canonical-ingredient pass in the caller's transaction."""
    provider = get_ai_provider(session)
    if provider is None:
        logger.debug("No AI provider configured; skipping ingredient dedup")
        return DedupResult()

    names = _vocabulary_by_usage(session)
    if not names:
        return DedupResult()

    merges, stats = propose_merges(provider, names, cursor)
    applied = apply_merges(session, merges)
    logger.info(
        f"Ingredient dedup: applied {applied} merge(s) "
        f"({stats.pre_merges} deterministic, {stats.ai_merges} semantic"
        f"{', reply truncated' if stats.ai_truncated else ''}) from {len(names)} ingredient(s) "
        f"over {stats.candidates} candidate(s)"
    )
    return replace(stats, merges_applied=applied, vocabulary_removed=applied)
