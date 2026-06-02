"""Match predicted recipes to gold by name.

Order in a book is not reliable across an extraction (a missed or split recipe shifts
everything after it), so matching is by name: an exact normalised-name pass, then a
greedy best-first fuzzy pass over the remainder. What stays unmatched on each side is
the signal v1's order-based matching could not produce — gold misses (false negatives)
and predicted hallucinations (false positives).
"""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from evals.data import EvalRecipe

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalise_name(name: str) -> str:
    """Casefold, drop punctuation, collapse whitespace — so 'Mac & Cheese' and
    'mac and cheese' do not match but 'Mac & Cheese' and 'Mac &  Cheese' do."""
    text = _PUNCT.sub(" ", name.casefold())
    return _WS.sub(" ", text).strip()


@dataclass(frozen=True)
class Match:
    gold_index: int
    predicted_index: int
    score: float  # name similarity, 0-100 (100 for the exact pass)


@dataclass
class MatchResult:
    matches: list[Match]
    unmatched_gold: list[int]
    unmatched_predicted: list[int]

    @property
    def true_positives(self) -> int:
        return len(self.matches)

    @property
    def precision(self) -> float:
        predicted = self.true_positives + len(self.unmatched_predicted)
        return self.true_positives / predicted if predicted else 0.0

    @property
    def recall(self) -> float:
        gold = self.true_positives + len(self.unmatched_gold)
        return self.true_positives / gold if gold else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def match_recipes(
    gold: list[EvalRecipe], predicted: list[EvalRecipe], fuzzy_threshold: float = 85.0
) -> MatchResult:
    gold_names = [normalise_name(r.name) for r in gold]
    pred_names = [normalise_name(r.name) for r in predicted]

    gold_open = set(range(len(gold)))
    pred_open = set(range(len(predicted)))
    matches: list[Match] = []

    # Exact pass: pair identical normalised names first. Duplicate names are consumed
    # in order, so two gold "Pancakes" match two predicted "Pancakes".
    by_name: dict[str, list[int]] = {}
    for j in pred_open:
        by_name.setdefault(pred_names[j], []).append(j)
    for i in sorted(gold_open):
        bucket = by_name.get(gold_names[i])
        if bucket:
            j = bucket.pop(0)
            matches.append(Match(i, j, 100.0))
            gold_open.discard(i)
            pred_open.discard(j)

    # Fuzzy pass: score every remaining cross pair, then take the best non-conflicting
    # ones greedily down to the threshold.
    candidates: list[tuple[float, int, int]] = []
    for i in gold_open:
        for j in pred_open:
            score = fuzz.token_set_ratio(gold_names[i], pred_names[j])
            if score >= fuzzy_threshold:
                candidates.append((score, i, j))

    for score, i, j in sorted(candidates, key=lambda c: c[0], reverse=True):
        if i in gold_open and j in pred_open:
            matches.append(Match(i, j, score))
            gold_open.discard(i)
            pred_open.discard(j)

    matches.sort(key=lambda m: m.gold_index)
    return MatchResult(
        matches=matches,
        unmatched_gold=sorted(gold_open),
        unmatched_predicted=sorted(pred_open),
    )
