"""AI-assisted keyword deduplication — merge near-duplicate tags down to one.

The shared keyword vocabulary (recipes and books both draw from it) accretes
variants over time: "Veggie"/"Vegetarian", "Stir Fry"/"Stir-fry", "Eggs"/"Egg".
This collapses them so search and filtering stay sharp. Two stages:

1. A deterministic pre-pass (no AI) folds the cheap, certain cases without restyling —
   whitespace and case variants of one term (keeping the most-used spelling), and a
   plural into its singular when both are present.
2. The AI proposes the semantic merges ("Shrimp" -> "Prawn") over what's left.

The two maps compose, chains are resolved to a single terminal canonical, and the
merges are applied across both `recipe_keywords` and `book_keywords` in the caller's
transaction — reassigning every association to the canonical row (recipes/books that
already carry it are left as-is) and deleting the merged-away keyword. Recipe and
list membership ride on the canonical row, so nothing a user curated is lost.
"""

import logging
from dataclasses import dataclass

import inflect
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.book import book_keywords
from app.models.recipe import Keyword, recipe_keywords
from app.services.ai import AIProvider, get_ai_provider
from app.services.keywords import get_or_create_keyword

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DedupResult:
    """What a dedup run did: how big the vocabulary was, how many merges applied, and
    how many keyword rows that removed (one per merged-away duplicate)."""

    keywords_in: int = 0
    merges_applied: int = 0
    keywords_removed: int = 0


def _normalise(name: str) -> str:
    """Trim and collapse internal whitespace — the only textual change the pre-pass
    makes (casing is preserved), so 'Stir  Fry' and 'Stir Fry' are seen as one."""
    return " ".join(name.split())


def pre_deduplicate(names: list[str]) -> tuple[list[str], dict[str, str]]:
    """Deterministic, no-AI merges over `names` (passed most-used first). Returns
    (survivors, merge_map): the spellings that remain, and {duplicate -> canonical} for
    everything folded away. Folds two cases without ever restyling — whitespace/case
    variants of one term (keeping the first, i.e. most-used, spelling), and a plural
    whose singular is also present, mapped onto that existing singular ('Eggs' -> 'Egg')."""
    engine = inflect.engine()
    merge_map: dict[str, str] = {}
    # casefolded, whitespace-collapsed term -> the spelling we keep (the most-used one).
    canonical_by_key: dict[str, str] = {}

    for name in names:
        collapsed = _normalise(name)
        canonical = canonical_by_key.setdefault(collapsed.casefold(), collapsed)
        if name != canonical:
            merge_map[name] = canonical

    for key in list(canonical_by_key):
        singular = engine.singular_noun(key)
        if isinstance(singular, str) and singular in canonical_by_key:
            canonical = canonical_by_key[key]
            target = canonical_by_key[singular]
            if target != canonical:
                merge_map[canonical] = target
                del canonical_by_key[key]

    return list(canonical_by_key.values()), merge_map


def _resolve_chains(raw: dict[str, str]) -> dict[str, str]:
    """Follow each duplicate to its terminal canonical (A->B, B->C becomes A->C, B->C),
    dropping self-maps and breaking cycles. The result has no value that is also a key,
    so the merges can be applied in any order without an intermediate row vanishing."""
    resolved: dict[str, str] = {}
    for original in raw:
        target = original
        seen = {original}
        while target in raw and raw[target] not in seen:
            seen.add(raw[target])
            target = raw[target]
        if target != original:
            resolved[original] = target
    # A cycle (A->B, B->A) leaves a value that is also a key; drop those so we never
    # keep a canonical that another entry would delete. Plain chains are unaffected —
    # their terminal is never a key.
    return {original: target for original, target in resolved.items() if target not in resolved}


def propose_merges(provider: AIProvider, names: list[str]) -> dict[str, str]:
    """Build the final {duplicate -> canonical} map for `names`: the deterministic
    pre-pass plus the AI's semantic merges over the survivors, chains resolved. AI
    entries win on overlap. Empty when nothing should change."""
    survivors, pre_map = pre_deduplicate(names)
    ai_map, _usage = provider.deduplicate_keywords(survivors)
    return _resolve_chains({**pre_map, **ai_map})


def apply_merges(session: Session, merges: dict[str, str]) -> int:
    """Apply a resolved {duplicate -> canonical} map, returning the number applied.
    For each duplicate that still exists: reassign its recipe and book associations to
    the canonical row (skipping any already linked, which would collide on the PK), then
    delete the duplicate. Writes ride the caller's transaction — the caller commits."""
    applied = 0
    for original, canonical in merges.items():
        duplicate = session.scalar(
            select(Keyword)
            .where(Keyword.name == original)
            .options(selectinload(Keyword.recipes), selectinload(Keyword.books))
        )
        # A pre-pass canonical (e.g. a re-cased form) may never have had its own row;
        # there's nothing stored to move, so skip it.
        if duplicate is None:
            continue

        target = get_or_create_keyword(session, canonical)
        # Reassign each association to the canonical, dropping the duplicate. The
        # `target not in` guard handles a recipe/book that already carries both, which
        # would otherwise collide on the association PK. Iterate copies — removing the
        # duplicate mutates these very back-reference collections.
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
    """Every keyword name, most-used first (recipe links + book links, then name). The
    order is load-bearing: the pre-pass keeps the first spelling of any case-variant, so
    feeding the dominant spelling first makes it canonical rather than restyling."""
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


def deduplicate_keywords(session: Session) -> DedupResult:
    """Run a full dedup over the whole keyword vocabulary. A no-op (returns zeros) when
    no AI provider is configured or the vocabulary is empty. Writes ride the caller's
    transaction. Logs a one-line summary; there is no review step before applying."""
    provider = get_ai_provider(session)
    if provider is None:
        logger.debug("No AI provider configured; skipping keyword dedup")
        return DedupResult()

    names = _vocabulary_by_usage(session)
    if not names:
        return DedupResult()

    try:
        merges = propose_merges(provider, names)
    except Exception:
        logger.exception("Keyword-dedup proposal failed; applying no merges")
        return DedupResult(keywords_in=len(names))

    applied = apply_merges(session, merges)
    logger.info(
        f"Keyword dedup: applied {applied} merge(s), "
        f"removed {applied} keyword(s) from a vocabulary of {len(names)}"
    )
    return DedupResult(keywords_in=len(names), merges_applied=applied, keywords_removed=applied)
