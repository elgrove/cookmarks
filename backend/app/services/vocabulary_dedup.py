"""Reusable mechanics for deduplicating a named vocabulary.

Vocabulary types differ in how they are read, how the AI is prompted, and how a
merge changes the database. The deterministic pre-pass, candidate rotation, and
merge-map validation are the same for every vocabulary type, so they live here.
"""

from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field

import inflect

from app.services.ai import Usage

DEFAULT_CANDIDATE_WINDOW = 1000

Proposal = Callable[[list[str], list[str]], tuple[dict[str, str], Usage, bool]]
TargetValidator = Callable[[str, set[str]], bool]


@dataclass(frozen=True)
class VocabularyDedupResult:
    """Metrics from one pass over a named vocabulary."""

    vocabulary_in: int = 0
    merges_applied: int = 0
    vocabulary_removed: int = 0
    pre_merges: int = 0
    ai_merges: int = 0
    ai_truncated: bool = False
    candidates: int = 0
    cursor_from: str | None = None
    cursor_to: str | None = None
    usage: Usage = field(default_factory=Usage)


def _normalise(name: str) -> str:
    """Trim and collapse internal whitespace without changing a name's style."""
    return " ".join(name.split())


def pre_deduplicate(names: list[str]) -> tuple[list[str], dict[str, str]]:
    """Fold certain spelling variants before the AI semantic pass.

    ``names`` must be ordered by use. The first spelling of each case-insensitive,
    whitespace-normalised name survives. A plural also merges into an existing
    singular spelling. No new spelling is created.
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


def resolve_chains(raw: dict[str, str]) -> dict[str, str]:
    """Resolve chains to terminal targets and discard self-maps and cycles."""
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


def select_candidates(
    survivors: list[str], cursor: str | None, candidate_window: int = DEFAULT_CANDIDATE_WINDOW
) -> tuple[list[str], str | None]:
    """Return the next name-sorted candidate window and its resume cursor."""
    names = sorted(survivors)
    if not names:
        return [], None
    start = 0 if cursor is None else bisect_right(names, cursor)
    if start >= len(names):
        start = 0
    window = (names[start:] + names[:start])[:candidate_window]
    return window, window[-1]


def propose_merges(
    names: list[str],
    cursor: str | None,
    propose: Proposal,
    candidate_window: int = DEFAULT_CANDIDATE_WINDOW,
    target_is_valid: TargetValidator | None = None,
) -> tuple[dict[str, str], VocabularyDedupResult]:
    """Build one safe merge map from deterministic and AI-assisted proposals.

    The caller supplies the vocabulary-specific AI proposal function. Only a current
    candidate may be removed, and targets must pass the vocabulary's rule. By
    default, targets must be current survivors. This keeps the database merge layer
    independent from untrusted model output.
    """
    survivors, pre_map = pre_deduplicate(names)
    candidates, cursor_to = select_candidates(survivors, cursor, candidate_window)
    raw_ai_map, usage, truncated = propose(survivors, candidates)
    vocabulary = set(survivors)
    target_is_valid = target_is_valid or (lambda target, vocabulary: target in vocabulary)
    candidate_set = set(candidates)
    ai_map = {
        original: canonical
        for original, canonical in raw_ai_map.items()
        if original in candidate_set and target_is_valid(canonical, vocabulary)
    }
    merges = resolve_chains({**pre_map, **ai_map})
    ai_merges = sum(1 for original in merges if original in ai_map)
    return merges, VocabularyDedupResult(
        vocabulary_in=len(names),
        pre_merges=len(merges) - ai_merges,
        ai_merges=ai_merges,
        ai_truncated=truncated,
        candidates=len(candidates),
        cursor_from=cursor,
        cursor_to=cursor_to,
        usage=usage,
    )
