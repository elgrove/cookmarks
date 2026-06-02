"""Per-field fidelity scoring for a matched (gold, predicted) recipe pair.

Field scores are lexical and deterministic — set Jaccard over normalised lines, a
fuzzy name ratio, exact yield, image by filename. The composite is a weighted mean
renormalised over the fields actually present (image is skipped when gold has none).
"""

import re
from pathlib import PurePosixPath

from rapidfuzz import fuzz

from evals.config import Weights
from evals.data import EvalRecipe
from evals.matching import normalise_name
from evals.models import FieldScores

_WS = re.compile(r"\s+")


def _norm_line(line: str) -> str:
    return _WS.sub(" ", line.casefold().strip())


def _line_set(lines: list[str]) -> set[str]:
    return {_norm_line(line) for line in lines if line.strip()}


def jaccard(a: set[str], b: set[str]) -> float:
    """Intersection over union; two empty sets agree (1.0) rather than divide by zero."""
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def _yield_match(gold: str | None, predicted: str | None) -> float:
    g = (gold or "").casefold().strip()
    p = (predicted or "").casefold().strip()
    if not g and not p:
        return 1.0
    return 1.0 if g == p else 0.0


def _image_match(gold: str | None, predicted: str | None) -> float | None:
    """None when there is no gold image (excluded from the composite); otherwise a
    filename match — directory prefixes differ across EPUB editions, basenames don't."""
    if not gold:
        return None
    if not predicted:
        return 0.0
    return 1.0 if PurePosixPath(gold).name == PurePosixPath(predicted).name else 0.0


def _composite(
    name: float,
    ingredients: float,
    instructions: float,
    yields: float,
    image: float | None,
    weights: Weights,
) -> float:
    parts = [
        (weights.name, name),
        (weights.ingredients, ingredients),
        (weights.instructions, instructions),
        (weights.yields, yields),
    ]
    if image is not None:
        parts.append((weights.image, image))
    total = sum(weight for weight, _ in parts)
    return sum(weight * score for weight, score in parts) / total if total else 0.0


def score_pair(gold: EvalRecipe, predicted: EvalRecipe, weights: Weights) -> FieldScores:
    g_ing, p_ing = _line_set(gold.ingredients), _line_set(predicted.ingredients)
    g_ins, p_ins = _line_set(gold.instructions), _line_set(predicted.instructions)
    g_kw = {k.casefold().strip() for k in gold.keywords if k.strip()}
    p_kw = {k.casefold().strip() for k in predicted.keywords if k.strip()}

    name_similarity = (
        fuzz.token_set_ratio(normalise_name(gold.name), normalise_name(predicted.name)) / 100
    )
    ingredients_jaccard = jaccard(g_ing, p_ing)
    instructions_jaccard = jaccard(g_ins, p_ins)
    yield_match = _yield_match(gold.yields, predicted.yields)
    image_match = _image_match(gold.image, predicted.image)

    return FieldScores(
        name_similarity=name_similarity,
        ingredients_jaccard=ingredients_jaccard,
        ingredients_missing=len(g_ing - p_ing),
        ingredients_extra=len(p_ing - g_ing),
        instructions_jaccard=instructions_jaccard,
        instructions_missing=len(g_ins - p_ins),
        instructions_extra=len(p_ins - g_ins),
        yield_match=yield_match,
        image_match=image_match,
        keywords_jaccard=jaccard(g_kw, p_kw),
        composite=_composite(
            name_similarity, ingredients_jaccard, instructions_jaccard, yield_match,
            image_match, weights,
        ),
    )


def aggregate(scores: list[FieldScores]) -> dict[str, float]:
    """Mean of each field across matched pairs. image_match averages only over pairs
    where a gold image existed, so books without photos don't read as zero."""
    if not scores:
        return {}

    def mean(values: list[float]) -> float:
        return sum(values) / len(values)

    image_values = [s.image_match for s in scores if s.image_match is not None]
    return {
        "composite_mean": mean([s.composite for s in scores]),
        "name_similarity_mean": mean([s.name_similarity for s in scores]),
        "ingredients_jaccard_mean": mean([s.ingredients_jaccard for s in scores]),
        "instructions_jaccard_mean": mean([s.instructions_jaccard for s in scores]),
        "yield_match_mean": mean([s.yield_match for s in scores]),
        "image_match_mean": mean(image_values) if image_values else 0.0,
        "keywords_jaccard_mean": mean([s.keywords_jaccard for s in scores]),
        "ingredients_missing_mean": mean([float(s.ingredients_missing) for s in scores]),
        "ingredients_extra_mean": mean([float(s.ingredients_extra) for s in scores]),
        "instructions_missing_mean": mean([float(s.instructions_missing) for s in scores]),
        "instructions_extra_mean": mean([float(s.instructions_extra) for s in scores]),
    }
