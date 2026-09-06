"""Unit tests for the recipe enrichment evaluation suite."""

import uuid
from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.services.ai import AIResponseError, Usage
from app.services.recipe_enrichment.schema import (
    EnrichmentResponse,
    Stage1LineDecision,
    Stage1Response,
    Stage2Response,
)
from evals.enrichment import (
    ENRICHMENT_GOLD_PATH,
    GoldFact,
    GoldLine,
    GoldRecipe,
    build_gold_context,
    build_gold_stage1_context,
    build_gold_stage2_context,
    evaluate_enrichment_recipe,
    load_gold_recipes,
    score_canonical_ingredients,
    score_enrichment_response,
    score_facets,
    score_key_ingredients,
    score_residual_keywords,
    validate_enrichment_response,
)
from evals.models import CandidateModel


def _sample_gold_recipe() -> GoldRecipe:
    return GoldRecipe(
        id=str(uuid.uuid4()),
        slug="test-salad",
        name="Test Salad",
        archetype="simple",
        yields="Serves 2",
        instructions=["Toss everything together."],
        lines=[
            GoldLine(position=0, text="1 apple, sliced"),
            GoldLine(position=1, text="For the dressing:"),
            GoldLine(position=2, text="1 tbsp olive oil"),
        ],
        canonical_ingredients=["apple", "olive oil"],
        key_ingredients=["apple"],
        cuisines=[GoldFact(value_id="british")],
        methods=[],
        courses=[GoldFact(value_id="starter")],
        accepted_courses=["starter", "side"],
        residual_keywords=["Salad", "Fresh", "No Cook", "Raw", "Summer"],
    )


def test_gold_dataset_loads_five_contrasting_recipes() -> None:
    recipes = load_gold_recipes(ENRICHMENT_GOLD_PATH)
    assert len(recipes) == 5
    archetypes = {r.archetype for r in recipes}
    assert archetypes == {
        "simple",
        "multi_step_compound",
        "heading_and_alternative_heavy",
        "stir_fry_with_optional_and_alternative_ingredients",
        "baked_cake_with_sections_and_alternatives",
    }
    slugs = [r.slug for r in recipes]
    assert "teriyaki-yellowtail" in slugs
    assert "aubergine-borani" in slugs
    assert "curry-udon" in slugs
    assert "pad-thai" in slugs
    assert "brown-butter-buttermilk-cake" in slugs


def test_score_canonical_ingredients_exact_and_misses() -> None:
    gold = _sample_gold_recipe()

    # Perfect match
    resp_perfect = EnrichmentResponse.model_validate(
        {
            "canonical_ingredients": [
                {"name": "apple", "is_key": True},
                {"name": "olive oil", "is_key": False},
            ],
            "cuisines": [],
            "methods": [],
            "courses": [],
            "keywords": ["One", "Two", "Three", "Four", "Five"],
        }
    )
    p, r, f1 = score_canonical_ingredients(gold.canonical_ingredients, resp_perfect)
    assert p == pytest.approx(1.0)
    assert r == pytest.approx(1.0)
    assert f1 == pytest.approx(1.0)

    # Partial match
    resp_partial = EnrichmentResponse.model_validate(
        {
            "canonical_ingredients": [
                {"name": "apple", "is_key": True},
                {"name": "butter", "is_key": False},
            ],
            "cuisines": [],
            "methods": [],
            "courses": [],
            "keywords": ["One", "Two", "Three", "Four", "Five"],
        }
    )
    p, r, f1 = score_canonical_ingredients(gold.canonical_ingredients, resp_partial)
    assert p == pytest.approx(0.5)
    assert r == pytest.approx(0.5)
    assert f1 == pytest.approx(0.5)


def test_score_key_ingredients() -> None:
    gold = _sample_gold_recipe()

    resp_correct = EnrichmentResponse.model_validate(
        {
            "canonical_ingredients": [
                {"name": "apple", "is_key": True},
                {"name": "olive oil", "is_key": False},
            ],
            "cuisines": [],
            "methods": [],
            "courses": [],
            "keywords": [],
        }
    )
    p, r, f1 = score_key_ingredients(gold.key_ingredients, resp_correct)
    assert p == pytest.approx(1.0)
    assert r == pytest.approx(1.0)
    assert f1 == pytest.approx(1.0)

    resp_wrong = EnrichmentResponse.model_validate(
        {
            "canonical_ingredients": [
                {"name": "apple", "is_key": False},
                {"name": "olive oil", "is_key": True},
            ],
            "cuisines": [],
            "methods": [],
            "courses": [],
            "keywords": [],
        }
    )
    p, r, f1 = score_key_ingredients(gold.key_ingredients, resp_wrong)
    assert p == pytest.approx(0.0)
    assert r == pytest.approx(0.0)
    assert f1 == pytest.approx(0.0)


def test_score_facets() -> None:
    gold = _sample_gold_recipe()
    resp = EnrichmentResponse.model_validate(
        {
            "canonical_ingredients": [],
            "cuisines": ["british"],
            "methods": [],
            "courses": ["starter"],
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
            "canonical_ingredients": [],
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


def test_score_residual_keywords_allows_an_empty_list() -> None:
    gold = _sample_gold_recipe()
    resp = EnrichmentResponse.model_validate(
        {
            "canonical_ingredients": [],
            "cuisines": [],
            "methods": [],
            "courses": [],
            "keywords": [],
        }
    )

    scores = score_residual_keywords(resp.keywords, gold, resp)

    assert scores["keywords_validity"] == 1.0
    assert scores["keywords_count"] == 0


def test_validate_enrichment_response_rejects_a_course_in_cuisines() -> None:
    gold = _sample_gold_recipe()
    context = build_gold_context(gold)
    response = EnrichmentResponse.model_validate(
        {
            "canonical_ingredients": [{"name": "apple", "is_key": True}],
            "cuisines": ["starter"],
            "methods": [],
            "courses": [],
            "keywords": [],
        }
    )

    with pytest.raises(ValueError, match="unknown or duplicate cuisine"):
        validate_enrichment_response(context, response)


def test_validate_enrichment_response_rejects_unknown_course() -> None:
    gold = _sample_gold_recipe()
    context = build_gold_context(gold)
    response = EnrichmentResponse.model_validate(
        {
            "canonical_ingredients": [{"name": "apple", "is_key": True}],
            "cuisines": [],
            "methods": [],
            "courses": ["unknown-course"],
            "keywords": [],
        }
    )

    with pytest.raises(ValueError, match="unknown or duplicate course"):
        validate_enrichment_response(context, response)


def test_build_gold_stage1_and_stage2_contexts() -> None:
    gold = _sample_gold_recipe()
    ctx1 = build_gold_stage1_context(gold)
    assert "recipe" in ctx1
    assert ctx1["recipe"]["name"] == "Test Salad"
    assert len(ctx1["recipe"]["ingredients"]) == 3

    ctx2 = build_gold_stage2_context(gold, ["apple", "olive oil"])
    assert "vocabulary" in ctx2
    assert "recipe" in ctx2
    assert ctx2["recipe"]["ingredients"] == ["apple", "olive oil"]


def test_score_enrichment_response_composite() -> None:
    gold = _sample_gold_recipe()

    resp = EnrichmentResponse.model_validate(
        {
            "canonical_ingredients": [
                {"name": "apple", "is_key": True},
                {"name": "olive oil", "is_key": False},
            ],
            "cuisines": ["british"],
            "methods": [],
            "courses": ["starter"],
            "keywords": ["Crispy", "Healthy", "Quick", "Summer", "Vegan"],
        }
    )
    scores = score_enrichment_response(gold, resp)
    assert scores.composite >= 0.95
    assert scores.canonical_ingredients_f1 == 1.0
    assert scores.key_ingredients_f1 == 1.0


def test_mixed_model_eval_routes_stage_output_to_stage_two(tmp_path) -> None:
    gold = _sample_gold_recipe()
    stage1_provider = Mock()
    stage1_provider.enrich_recipe_stage1.return_value = (
        Stage1Response(
            i=[
                Stage1LineDecision(id="01", n="apple"),
                Stage1LineDecision(id="02", n=None),
                Stage1LineDecision(id="03", n="olive oil"),
            ]
        ),
        Usage(input_tokens=100, output_tokens=20, cost_usd=Decimal("0.001")),
    )
    stage2_provider = Mock()
    stage2_provider.enrich_recipe_stage2.return_value = (
        Stage2Response(k=["apple"], c=[], m=[], o=["starter"], w=["Fresh"]),
        Usage(input_tokens=50, output_tokens=10, cost_usd=Decimal("0.002")),
    )

    record = evaluate_enrichment_recipe(
        CandidateModel.parse("GEMINI:flash-lite"),
        stage1_provider,
        gold,
        run_id="test-run",
        timestamp="2026-09-06T00:00:00+00:00",
        sha="abc1234",
        run_dir=tmp_path,
        vocab={},
        stage2_candidate=CandidateModel.parse("ANTHROPIC:haiku"),
        stage2_provider=stage2_provider,
    )

    stage2_context = stage2_provider.enrich_recipe_stage2.call_args.args[0]
    assert stage2_context["recipe"]["ingredients"] == ["apple", "olive oil"]
    assert record.model_id == "GEMINI:flash-lite -> ANTHROPIC:haiku"
    assert record.deterministic_enabled is False
    assert record.stage1_input_tokens == 100
    assert record.stage2_input_tokens == 50
    assert record.cost_usd == pytest.approx(0.003)
    assert record.scores.canonical_ingredients_f1 == pytest.approx(1.0)
    assert record.scores.key_ingredients_f1 == pytest.approx(1.0)


def test_mixed_model_eval_keeps_stage_one_usage_when_stage_two_fails(tmp_path) -> None:
    gold = _sample_gold_recipe()
    stage1_provider = Mock()
    stage1_provider.enrich_recipe_stage1.return_value = (
        Stage1Response(
            i=[
                Stage1LineDecision(id="01", n="apple"),
                Stage1LineDecision(id="02", n=None),
                Stage1LineDecision(id="03", n="olive oil"),
            ]
        ),
        Usage(input_tokens=100, output_tokens=20, cost_usd=Decimal("0.001")),
    )
    stage2_provider = Mock()
    stage2_provider.enrich_recipe_stage2.side_effect = AIResponseError(
        "stage two failed",
        Usage(input_tokens=50, output_tokens=10, cost_usd=Decimal("0.002")),
    )

    record = evaluate_enrichment_recipe(
        CandidateModel.parse("GEMINI:flash-lite"),
        stage1_provider,
        gold,
        run_id="test-run",
        timestamp="2026-09-06T00:00:00+00:00",
        sha="abc1234",
        run_dir=tmp_path,
        stage2_candidate=CandidateModel.parse("ANTHROPIC:haiku"),
        stage2_provider=stage2_provider,
    )

    assert record.error == "stage two failed"
    assert record.stage1_cost_usd == pytest.approx(0.001)
    assert record.stage2_cost_usd == pytest.approx(0.002)
    assert record.cost_usd == pytest.approx(0.003)
