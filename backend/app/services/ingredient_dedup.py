"""AI-assisted canonical-ingredient deduplication.

The deterministic pre-pass folds only certain spelling variants. The semantic pass
asks the configured provider about one rotating candidate window, while the complete
vocabulary remains available as possible canonical targets. Merges move every linked
``RecipeIngredient`` to the surviving canonical row before the duplicate is deleted.
"""

import logging
from bisect import bisect_right
from dataclasses import dataclass, field, replace

import inflect
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.ingredient import CanonicalIngredient, RecipeIngredient
from app.services.ai import AIProvider, Usage, get_ai_provider
from app.services.recipe_facts import get_or_create_canonical_ingredient

logger = logging.getLogger(__name__)

DEDUP_CANDIDATE_WINDOW = 1000


@dataclass(frozen=True)
class DedupResult:
    """Metrics from one canonical-ingredient deduplication pass."""

    ingredients_in: int = 0
    merges_applied: int = 0
    ingredients_removed: int = 0
    pre_merges: int = 0
    ai_merges: int = 0
    ai_truncated: bool = False
    candidates: int = 0
    cursor_from: str | None = None
    cursor_to: str | None = None
    usage: Usage = field(default_factory=Usage)


def _normalise(name: str) -> str:
    """Trim and collapse internal whitespace without restyling a name."""
    return " ".join(name.split())


def pre_deduplicate(names: list[str]) -> tuple[list[str], dict[str, str]]:
    """Fold whitespace/case variants and existing singular/plural pairs.

    ``names`` must be ordered by usage. The first spelling for each normalised form
    is kept so the most referenced name becomes canonical rather than a new style.
    """
    engine = inflect.engine()
    merge_map: dict[str, str] = {}
    canonical_by_key: dict[str, str] = {}

    for name in names:
        collapsed = _normalise(name)
        canonical = canonical_by_key.setdefault(collapsed.casefold(), collapsed)
        if name != canonical:
            merge_map[name] = canonical

    for key in list(canonical_by_key):
        singular = engine.singular_noun(key)
        if isinstance(singular, str) and singular in canonical_by_key:
            duplicate = canonical_by_key[key]
            target = canonical_by_key[singular]
            if duplicate != target:
                merge_map[duplicate] = target
                del canonical_by_key[key]

    return list(canonical_by_key.values()), merge_map


def _resolve_chains(raw: dict[str, str]) -> dict[str, str]:
    """Resolve A -> B -> C into terminal targets and discard self maps/cycles."""
    resolved: dict[str, str] = {}
    for original in raw:
        target = original
        seen = {original}
        while target in raw and raw[target] not in seen:
            seen.add(raw[target])
            target = raw[target]
        if target != original:
            resolved[original] = target
    return {original: target for original, target in resolved.items() if target not in resolved}


def select_candidates(survivors: list[str], cursor: str | None) -> tuple[list[str], str | None]:
    """Select the next sorted candidate window and wrap after the vocabulary end."""
    names = sorted(survivors)
    if not names:
        return [], None
    start = 0 if cursor is None else bisect_right(names, cursor)
    if start >= len(names):
        start = 0
    window = (names[start:] + names[:start])[:DEDUP_CANDIDATE_WINDOW]
    return window, window[-1]


def propose_merges(
    provider: AIProvider, names: list[str], cursor: str | None = None
) -> tuple[dict[str, str], DedupResult]:
    """Combine deterministic and AI proposals into one validated merge map."""
    survivors, pre_map = pre_deduplicate(names)
    candidates, cursor_to = select_candidates(survivors, cursor)
    ai_map, usage, truncated = provider.deduplicate_ingredients(survivors, candidates)
    vocabulary = set(survivors)
    ai_map = {
        original: canonical for original, canonical in ai_map.items() if canonical in vocabulary
    }
    merges = _resolve_chains({**pre_map, **ai_map})
    ai_merges = sum(1 for original in merges if original in ai_map)
    stats = DedupResult(
        ingredients_in=len(names),
        pre_merges=len(merges) - ai_merges,
        ai_merges=ai_merges,
        ai_truncated=truncated,
        candidates=len(candidates),
        cursor_from=cursor,
        cursor_to=cursor_to,
        usage=usage,
    )
    return merges, stats


def apply_merges(session: Session, merges: dict[str, str]) -> int:
    """Repoint recipe ingredients, then delete each merged-away canonical row."""
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
    """Return every canonical name, most-linked first, then alphabetically."""
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
    """Run one tracked deduplication pass in the caller's transaction."""
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
    return replace(stats, merges_applied=applied, ingredients_removed=applied)
