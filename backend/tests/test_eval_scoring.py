"""Unit tests for the eval scoring layer: gold/predicted normalisation, name-based
matching with set retrieval metrics, and per-field fidelity scoring. All deterministic
— no AI, no database."""

import pytest

from evals.config import Weights
from evals.data import EvalRecipe, to_eval_recipe
from evals.matching import match_recipes, normalise_name
from evals.metrics import aggregate, jaccard, score_pair

WEIGHTS = Weights(name=0.20, ingredients=0.30, instructions=0.30, yields=0.15, image=0.05)


def _recipe(
    name: str,
    *,
    ingredients: list[str] | None = None,
    instructions: list[str] | None = None,
    yields: str | None = None,
    image: str | None = None,
    keywords: list[str] | None = None,
) -> EvalRecipe:
    return EvalRecipe(
        name=name,
        ingredients=ingredients or [],
        instructions=instructions or [],
        yields=yields,
        image=image,
        keywords=keywords or [],
    )


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #


def test_to_eval_recipe_accepts_gold_keys() -> None:
    r = to_eval_recipe(
        {
            "name": "Dal",
            "ingredients": ["lentils", "water"],
            "instructions": ["boil"],
            "yields": "Serves 4",
            "image": "EPUB/images/p1.jpg",
            "keywords": ["Indian"],
        }
    )
    assert r.ingredients == ["lentils", "water"]
    assert r.instructions == ["boil"]
    assert r.yields == "Serves 4"


def test_to_eval_recipe_accepts_predicted_aliases() -> None:
    r = to_eval_recipe(
        {
            "name": "Dal",
            "recipeIngredients": [{"text": "lentils"}, {"text": "water"}],
            "recipeInstructions": ["boil"],
            "recipeYield": "Serves 4",
        }
    )
    assert r.ingredients == ["lentils", "water"]
    assert r.instructions == ["boil"]
    assert r.yields == "Serves 4"


# --------------------------------------------------------------------------- #
# matching
# --------------------------------------------------------------------------- #


def test_normalise_name_drops_punctuation_and_case() -> None:
    assert normalise_name("Mac & Cheese") == "mac cheese"
    assert normalise_name("Mac &  Cheese") == normalise_name("MAC & CHEESE")


def test_match_exact_names() -> None:
    gold = [_recipe("Pancakes"), _recipe("Waffles")]
    pred = [_recipe("waffles"), _recipe("PANCAKES")]
    result = match_recipes(gold, pred)
    assert len(result.matches) == 2
    assert all(m.score == 100.0 for m in result.matches)
    assert result.precision == 1.0 and result.recall == 1.0 and result.f1 == 1.0


def test_match_fuzzy_above_threshold() -> None:
    gold = [_recipe("Spaghetti Bolognese")]
    pred = [_recipe("Spaghetti Bolognaise")]
    result = match_recipes(gold, pred, fuzzy_threshold=70)
    assert len(result.matches) == 1
    assert 70 <= result.matches[0].score < 100


def test_match_reports_misses_and_hallucinations() -> None:
    gold = [_recipe("Apple Pie"), _recipe("Beef Stew")]
    pred = [_recipe("Apple Pie"), _recipe("Cloud Bread")]
    result = match_recipes(gold, pred, fuzzy_threshold=85)
    assert len(result.matches) == 1
    assert result.unmatched_gold == [1]  # Beef Stew missed
    assert result.unmatched_predicted == [1]  # Cloud Bread hallucinated
    assert result.precision == 0.5 and result.recall == 0.5
    assert result.f1 == pytest.approx(0.5)


def test_match_consumes_duplicate_names() -> None:
    gold = [_recipe("Pancakes"), _recipe("Pancakes")]
    pred = [_recipe("Pancakes")]
    result = match_recipes(gold, pred)
    assert len(result.matches) == 1
    assert len(result.unmatched_gold) == 1


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #


def test_jaccard() -> None:
    assert jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)
    assert jaccard(set(), set()) == 1.0
    assert jaccard({"a"}, set()) == 0.0


def test_score_pair_identical_is_perfect() -> None:
    r = _recipe(
        "Dal",
        ingredients=["100g lentils", "500ml water"],
        instructions=["Boil", "Simmer"],
        yields="Serves 4",
        image="EPUB/images/p1.jpg",
        keywords=["Indian", "Vegan"],
    )
    scores = score_pair(r, r, WEIGHTS)
    assert scores.composite == pytest.approx(1.0)
    assert scores.ingredients_missing == 0 and scores.ingredients_extra == 0
    assert scores.image_match == 1.0


def test_score_pair_partial_ingredients() -> None:
    gold = _recipe("Dal", ingredients=["a", "b", "c"], instructions=["x"])
    pred = _recipe("Dal", ingredients=["a", "b"], instructions=["x"])
    scores = score_pair(gold, pred, WEIGHTS)
    assert scores.ingredients_jaccard == pytest.approx(2 / 3)
    assert scores.ingredients_missing == 1
    assert scores.ingredients_extra == 0


def test_score_pair_image_match_by_basename() -> None:
    gold = _recipe("Dal", ingredients=["a"], instructions=["x"], image="EPUB/images/p1.jpg")
    pred = _recipe("Dal", ingredients=["a"], instructions=["x"], image="OEBPS/img/p1.jpg")
    assert score_pair(gold, pred, WEIGHTS).image_match == 1.0


def test_score_pair_no_gold_image_excluded_from_composite() -> None:
    gold = _recipe("Dal", ingredients=["a"], instructions=["x"], yields="Serves 2")
    pred = _recipe("Dal", ingredients=["a"], instructions=["x"], yields="Serves 2")
    scores = score_pair(gold, pred, WEIGHTS)
    assert scores.image_match is None
    assert scores.composite == pytest.approx(1.0)  # renormalised over present fields


def test_aggregate_image_mean_ignores_none() -> None:
    with_image = score_pair(
        _recipe("A", ingredients=["a"], instructions=["x"], image="p1.jpg"),
        _recipe("A", ingredients=["a"], instructions=["x"], image="p1.jpg"),
        WEIGHTS,
    )
    without_image = score_pair(
        _recipe("B", ingredients=["a"], instructions=["x"]),
        _recipe("B", ingredients=["a"], instructions=["x"]),
        WEIGHTS,
    )
    agg = aggregate([with_image, without_image])
    assert agg["image_match_mean"] == 1.0  # only the one with a gold image counted
    assert agg["composite_mean"] == pytest.approx(1.0)
