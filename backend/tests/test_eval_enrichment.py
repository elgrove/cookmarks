"""Unit tests for the recipe enrichment evaluation suite."""

import uuid

import pytest

from app.services.recipe_enrichment.schema import (
    EnrichmentResponse,
)
from evals.enrichment import (
    ENRICHMENT_GOLD_PATH,
    GoldFact,
    GoldLine,
    GoldOccurrence,
    GoldRecipe,
    build_gold_context,
    load_gold_recipes,
    score_enrichment_response,
    score_facets,
    score_ingredient_identity,
    score_line_kinds,
    score_residual_keywords,
)


def _sample_gold_recipe() -> GoldRecipe:
    return GoldRecipe(
        id=str(uuid.uuid4()),
        slug="test-salad",
        name="Test Salad",
        archetype="simple",
        yields="Serves 2",
        instructions=["Toss everything together."],
        lines=[
            GoldLine(
                position=0,
                text="1 apple, sliced",
                kind="ingredient",
                occurrences=[
                    GoldOccurrence(
                        canonical_name="Apple",
                        quantity="1",
                        unit=None,
                        preparation="sliced",
                        optional=False,
                        alternative_group=None,
                        is_key=True,
                    )
                ],
            ),
            GoldLine(
                position=1,
                text="For the dressing:",
                kind="heading",
                occurrences=[],
            ),
            GoldLine(
                position=2,
                text="1 tbsp olive oil",
                kind="ingredient",
                occurrences=[
                    GoldOccurrence(
                        canonical_name="Olive Oil",
                        quantity="1",
                        unit="tbsp",
                        preparation=None,
                        optional=False,
                        alternative_group=None,
                        is_key=False,
                    )
                ],
            ),
        ],
        cuisines=[GoldFact(value_id="british", source="inferred")],
        methods=[],
        courses=[GoldFact(value_id="starter", source="inferred")],
        accepted_courses=["starter", "side"],
        residual_keywords=["Salad", "Fresh", "No Cook", "Raw", "Summer"],
    )


def test_gold_dataset_loads_three_contrasting_recipes() -> None:
    recipes = load_gold_recipes(ENRICHMENT_GOLD_PATH)
    assert len(recipes) == 3
    archetypes = {r.archetype for r in recipes}
    assert archetypes == {"simple", "multi_step_compound", "heading_and_alternative_heavy"}
    slugs = [r.slug for r in recipes]
    assert "teriyaki-yellowtail" in slugs
    assert "aubergine-borani" in slugs
    assert "curry-udon" in slugs



def test_score_ingredient_identity_exact_and_misses() -> None:
    gold = _sample_gold_recipe()
    line0_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{gold.lines[0].position}:{gold.lines[0].text}"))
    line2_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{gold.lines[2].position}:{gold.lines[2].text}"))

    # Perfect match
    resp_perfect = EnrichmentResponse.model_validate(
        {
            "recipe_id": gold.id,
            "source_fingerprint": "fp",
            "parsed_lines": [
                {
                    "line_id": line0_id,
                    "occurrences": [{"canonical_name": "Apple"}],
                },
                {
                    "line_id": line2_id,
                    "occurrences": [{"canonical_name": "Olive Oil"}],
                },
            ],
            "non_ingredient_lines": [],
            "cuisines": [],
            "methods": [],
            "courses": [],
            "keywords": ["One", "Two", "Three", "Four", "Five"],
        }
    )
    p, r, f1 = score_ingredient_identity(gold.lines, resp_perfect)
    assert p == pytest.approx(1.0)
    assert r == pytest.approx(1.0)
    assert f1 == pytest.approx(1.0)

    # Partial match
    resp_partial = EnrichmentResponse.model_validate(
        {
            "recipe_id": gold.id,
            "source_fingerprint": "fp",
            "parsed_lines": [
                {
                    "line_id": line0_id,
                    "occurrences": [{"canonical_name": "Apple"}],
                },
                {
                    "line_id": line2_id,
                    "occurrences": [{"canonical_name": "Butter"}],
                },
            ],
            "non_ingredient_lines": [],
            "cuisines": [],
            "methods": [],
            "courses": [],
            "keywords": ["One", "Two", "Three", "Four", "Five"],
        }
    )
    p, r, f1 = score_ingredient_identity(gold.lines, resp_partial)
    assert p == pytest.approx(0.5)
    assert r == pytest.approx(0.5)
    assert f1 == pytest.approx(0.5)


def test_score_line_kinds_detects_headings() -> None:
    gold = _sample_gold_recipe()
    line1_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{gold.lines[1].position}:{gold.lines[1].text}"))

    resp_correct = EnrichmentResponse.model_validate(
        {
            "recipe_id": gold.id,
            "source_fingerprint": "fp",
            "parsed_lines": [],
            "non_ingredient_lines": [{"line_id": line1_id, "kind": "heading"}],
            "cuisines": [],
            "methods": [],
            "courses": [],
            "keywords": ["One", "Two", "Three", "Four", "Five"],
        }
    )
    acc = score_line_kinds(gold.lines, resp_correct)
    assert acc == pytest.approx(1.0)

    resp_wrong = EnrichmentResponse.model_validate(
        {
            "recipe_id": gold.id,
            "source_fingerprint": "fp",
            "parsed_lines": [],
            "non_ingredient_lines": [],
            "cuisines": [],
            "methods": [],
            "courses": [],
            "keywords": ["One", "Two", "Three", "Four", "Five"],
        }
    )
    acc_wrong = score_line_kinds(gold.lines, resp_wrong)
    assert acc_wrong == pytest.approx(2 / 3)


def test_score_facets() -> None:
    gold = _sample_gold_recipe()
    resp = EnrichmentResponse.model_validate(
        {
            "recipe_id": gold.id,
            "source_fingerprint": "fp",
            "parsed_lines": [],
            "non_ingredient_lines": [],
            "cuisines": [{"value_id": "british", "source": "inferred"}],
            "methods": [],
            "courses": [{"value_id": "starter", "source": "inferred"}],
            "keywords": ["One", "Two", "Three", "Four", "Five"],
        }
    )
    scores = score_facets(gold, resp)
    assert scores["cuisine_score"] == 1.0
    assert scores["primary_method_score"] == 1.0
    assert scores["course_score"] == 1.0
    assert scores["facets_mean"] == 1.0


def test_score_residual_keywords_validity() -> None:
    gold = _sample_gold_recipe()
    resp = EnrichmentResponse.model_validate(
        {
            "recipe_id": gold.id,
            "source_fingerprint": "fp",
            "parsed_lines": [],
            "non_ingredient_lines": [],
            "cuisines": [],
            "methods": [],
            "courses": [],
            "keywords": ["Crispy", "Healthy", "Quick", "Summer", "Vegan"],
        }
    )
    scores = score_residual_keywords(resp.keywords, gold, resp)
    assert scores["keywords_validity"] == 1.0
    assert scores["keywords_count"] == 5
    assert scores["keywords_duplicates"] == 0
    assert scores["keywords_overlap"] == 0


def test_build_gold_context_structures_reusable_input() -> None:
    gold = _sample_gold_recipe()
    context = build_gold_context(gold)
    assert "vocabulary" in context
    assert "recipe" in context
    assert context["recipe"]["name"] == "Test Salad"
    assert len(context["recipe"]["lines"]) == 3
    assert len(context["recipe"]["ai_parse_line_ids"]) == 3


def test_score_enrichment_response_composite() -> None:
    gold = _sample_gold_recipe()
    line0_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{gold.lines[0].position}:{gold.lines[0].text}"))
    line1_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{gold.lines[1].position}:{gold.lines[1].text}"))
    line2_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{gold.lines[2].position}:{gold.lines[2].text}"))

    resp = EnrichmentResponse.model_validate(
        {
            "recipe_id": gold.id,
            "source_fingerprint": "fp",
            "parsed_lines": [
                {
                    "line_id": line0_id,
                    "occurrences": [
                        {
                            "canonical_name": "Apple",
                            "quantity": "1",
                            "preparation": "sliced",
                            "is_key": True,
                        }
                    ],
                },
                {
                    "line_id": line2_id,
                    "occurrences": [
                        {
                            "canonical_name": "Olive Oil",
                            "quantity": "1",
                            "unit": "tbsp",
                        }
                    ],
                },
            ],
            "non_ingredient_lines": [{"line_id": line1_id, "kind": "heading"}],
            "cuisines": [{"value_id": "british", "source": "inferred"}],
            "methods": [],
            "courses": [{"value_id": "starter", "source": "inferred"}],
            "keywords": ["Crispy", "Healthy", "Quick", "Summer", "Vegan"],
        }
    )
    scores = score_enrichment_response(gold, resp)
    assert scores.composite >= 0.95
    assert scores.line_kinds_accuracy == 1.0
    assert scores.ingredient_identity_f1 == 1.0
