from decimal import Decimal
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.models.enums import AIProvider, IngredientLineKind, RecipeEnrichmentStatus
from app.models.ingredient import IngredientLine, IngredientOccurrence
from app.models.recipe import Keyword, Recipe
from app.models.recipe_enrichment import RecipeEnrichmentState
from app.services.ai import ModelRole, Usage
from app.services.ai.anthropic import AnthropicProvider
from app.services.ai.gemini import GeminiProvider
from app.services.ai.registry import get_config, get_recipe_enrichment_providers
from app.services.ai.stub import StubProvider
from app.services.recipe_enrichment.prompt import (
    build_prompt,
    build_stage1_prompt,
    build_stage2_prompt,
)
from app.services.recipe_enrichment.schema import (
    ENRICHMENT_JSON_SCHEMA,
    GEMINI_ENRICHMENT_JSON_SCHEMA,
    SCHEMA_VERSION,
    EnrichmentResponse,
    Stage1Response,
    Stage2Response,
)
from app.services.recipe_enrichment.service import (
    EnrichmentValidationError,
    apply_enrichment,
    build_context,
    build_stage2_context,
    enrich_recipe,
    validate_stage1_response,
)
from app.services.recipe_facts import add_ingredient_alias, create_ingredient


def _recipe(session) -> Recipe:
    book_id = session.query(Recipe).first().book_id
    recipe = Recipe(book_id=book_id, order=99, name="Enriched", instructions=["Bake it."])
    recipe.ingredients_verbatim = [IngredientLine(position=0, text="salt")]
    recipe.enrichment_state = RecipeEnrichmentState(
        status=RecipeEnrichmentStatus.PENDING, source_fingerprint="current"
    )
    session.add(recipe)
    session.commit()
    return recipe


def _response(recipe: Recipe, **overrides) -> EnrichmentResponse:
    data = {
        "parsed_lines": [
            {
                "line_id": str(recipe.ingredients_verbatim[0].id),
                "occurrences": [{"canonical_name": "Sea Salt", "is_key": True}],
            }
        ],
        "cuisines": [],
        "methods": [{"value_id": "bake", "is_primary": True}],
        "courses": [],
        "keywords": ["Cosy", "Fresh", "Outdoor", "Party", "Summer"],
    }
    data.update(overrides)
    return EnrichmentResponse.model_validate(data)


def test_apply_enrichment_replaces_all_derived_facts_atomically(session) -> None:
    recipe = _recipe(session)
    create_ingredient(session, "Sea Salt")
    context = build_context(session, recipe)
    assert context["recipe"]["ai_parse_line_ids"] == [str(recipe.ingredients_verbatim[0].id)]
    result = apply_enrichment(
        session,
        recipe.id,
        _response(recipe),
        provider=StubProvider(""),
        model="stub-enrichment",
    )
    session.commit()
    session.refresh(recipe)
    assert result["occurrences"] == 1
    assert result["existing_ingredients"] == 1
    assert recipe.enrichment_state is not None
    assert recipe.enrichment_state.status is RecipeEnrichmentStatus.COMPLETE
    assert [item.ingredient.name for item in session.query(IngredientOccurrence).all()] == [
        "Sea Salt"
    ]
    assert [fact.facet_value.value_id for fact in recipe.facets] == ["bake"]
    assert {keyword.name for keyword in recipe.keywords} == {
        "Cosy",
        "Fresh",
        "Outdoor",
        "Party",
        "Summer",
    }


def test_apply_enrichment_resolves_an_ai_canonical_name_through_an_alias(session) -> None:
    recipe = _recipe(session)
    ingredient = create_ingredient(session, "Chickpea")
    add_ingredient_alias(session, ingredient, "Garbanzo Bean")
    response = _response(
        recipe,
        parsed_lines=[
            {
                "line_id": str(recipe.ingredients_verbatim[0].id),
                "occurrences": [{"canonical_name": "Garbanzo Bean", "is_key": True}],
            }
        ],
    )
    build_context(session, recipe)

    result = apply_enrichment(
        session,
        recipe.id,
        response,
        provider=StubProvider(""),
        model="stub-enrichment",
    )

    occurrence = session.query(IngredientOccurrence).one()
    assert result["existing_ingredients"] == 1
    assert occurrence.ingredient_id == ingredient.id


def test_empty_keywords_replace_previous_keywords(session) -> None:
    recipe = _recipe(session)
    recipe.keywords = [Keyword(name="Existing")]
    create_ingredient(session, "Sea Salt")
    session.commit()
    build_context(session, recipe)
    response = _response(recipe, keywords=[])
    apply_enrichment(
        session,
        recipe.id,
        response,
        provider=StubProvider(""),
        model="stub-enrichment",
    )
    session.commit()
    session.refresh(recipe)
    assert recipe.enrichment_state is not None
    assert recipe.enrichment_state.status is RecipeEnrichmentStatus.COMPLETE
    assert recipe.keywords == []
    assert recipe.ingredients_verbatim[0].kind is IngredientLineKind.INGREDIENT
    assert session.query(IngredientOccurrence).count() == 1


def test_response_rejects_more_than_five_keywords(session) -> None:
    recipe = _recipe(session)
    with pytest.raises(ValidationError, match="at most 5 items"):
        _response(recipe, keywords=["One", "Two", "Three", "Four", "Five", "Six"])


def test_stub_enrichment_is_separate_and_offline(session) -> None:
    recipe = _recipe(session)
    assert recipe.enrichment_state is not None
    recipe.enrichment_state.source_fingerprint = None  # migration-era row
    session.commit()
    result, usage = enrich_recipe(session, recipe.id, provider=StubProvider(""))
    session.refresh(recipe)
    assert result["occurrences"] == 1
    assert usage.input_tokens == 0
    assert recipe.enrichment_state is not None
    assert recipe.enrichment_state.status is RecipeEnrichmentStatus.COMPLETE
    assert recipe.enrichment_state.source_fingerprint is not None
    assert len(recipe.keywords) == 5


def test_only_methods_offer_primary_flag(session) -> None:
    recipe = _recipe(session)
    with pytest.raises(ValidationError, match="Input should be a valid string"):
        _response(recipe, courses=[{"value_id": "main", "is_primary": True}])
    definitions = ENRICHMENT_JSON_SCHEMA["$defs"]
    assert "MethodDecision" in definitions
    assert "p" in definitions["MethodDecision"]["properties"]


def test_gemini_enrichment_schema_omits_stateful_constraints() -> None:
    """Gemini receives a schema it can compile; local validation stays strict."""
    schema_text = str(GEMINI_ENRICHMENT_JSON_SCHEMA)

    assert "maxItems" not in schema_text
    assert "maxLength" not in schema_text
    assert "minItems" not in schema_text
    assert "minLength" not in schema_text
    assert "minimum" not in schema_text


def test_enrichment_prompt_requires_one_occurrence_resolution_and_central_methods() -> None:
    prompt = build_prompt(
        {
            "vocabulary": {"ingredients": [], "cuisines": [], "methods": [], "courses": []},
            "recipe": {
                "id": "recipe-id",
                "source_fingerprint": "fingerprint",
                "name": "Recipe",
                "description": None,
                "yield": None,
                "instructions": [],
                "lines": [],
                "deterministic_proposals": [],
                "ai_parse_line_ids": [],
            },
        }
    )

    assert "There is\nno ingredient ID field" in prompt
    assert "central, intentional cooking technique" in prompt
    assert "chopping, slicing, mixing" in prompt
    assert "Decide cuisines, methods and courses" in prompt


def test_response_rejects_ingredient_ids(session) -> None:
    recipe = _recipe(session)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _response(
            recipe,
            parsed_lines=[
                {
                    "line_id": str(recipe.ingredients_verbatim[0].id),
                    "occurrences": [
                        {"ingredient_id": "ingredient-id", "canonical_name": "Sea Salt"}
                    ],
                }
            ],
        )


def test_response_rejects_missing_ai_line_decision(session) -> None:
    recipe = _recipe(session)
    build_context(session, recipe)
    response = _response(
        recipe,
        parsed_lines=[],
    )
    with pytest.raises(EnrichmentValidationError, match="must decide every ingredient line"):
        apply_enrichment(
            session,
            recipe.id,
            response,
            provider=StubProvider(""),
            model="stub-enrichment",
        )


def test_schema_version_tracks_the_bounded_output_change() -> None:
    assert SCHEMA_VERSION == "v7"


def test_prompt_requires_ai_decisions_for_all_lines(session) -> None:
    recipe = _recipe(session)
    context = build_context(session, recipe)
    prompt = build_prompt(context)
    assert "ai_parse_line_ids" in prompt
    assert "no ingredient ID field" in prompt


def test_stage1_prompt_requires_complete_alternative_groups() -> None:
    prompt = build_stage1_prompt(
        {
            "recipe": {
                "id": "recipe-1",
                "instructions": [],
                "lines": [
                    {
                        "id": "line-1",
                        "text": "Nonstick cooking spray or softened butter, for the pan",
                    }
                ],
                "ai_parse_line_ids": ["line-1"],
            }
        }
    )

    assert "one occurrence for EACH choice" in prompt
    assert "SAME non-null `a` value" in prompt
    assert "Detect a choice by its meaning, not by one word" in prompt
    assert "`↔` or `<->`" in prompt
    assert "fraction, measurement conversion, quantity range" in prompt
    assert "A substitute choice does not mean optional" in prompt
    assert "Final alternative check" in prompt
    assert "Do not decide which ingredients are key" in prompt


def test_stage1_schema_rejects_key_ingredient_decisions() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Stage1Response.model_validate(
            {
                "parsed_lines": [
                    {
                        "line_id": "line-1",
                        "occurrences": [{"canonical_name": "Apple", "is_key": True}],
                    }
                ]
            }
        )


def test_stage2_receives_structured_stage1_result_and_owns_key_selection(session) -> None:
    recipe = _recipe(session)
    line_id = str(recipe.ingredients_verbatim[0].id)
    stage1 = Stage1Response.model_validate(
        {
            "parsed_lines": [
                {
                    "line_id": line_id,
                    "occurrences": [{"canonical_name": "Sea Salt", "quantity": "1", "unit": "tsp"}],
                }
            ]
        }
    )
    context = build_stage2_context(session, recipe, stage1)
    ingredient_line = context["recipe"]["ingredient_lines"][0]
    assert ingredient_line["line_id"] == line_id
    assert ingredient_line["source"] == "salt"
    assert ingredient_line["occurrences"][0]["canonical_name"] == "Sea Salt"
    prompt = build_stage2_prompt(context)
    assert "Key ingredients (k)" in prompt

    response = EnrichmentResponse.from_stages(
        stage1,
        Stage2Response.model_validate(
            {"key_ingredients": [{"line_id": line_id, "occurrence_index": 0}]}
        ),
    )
    assert response.parsed_lines[0].occurrences[0].is_key is True

    with pytest.raises(ValueError, match="unknown Stage 1 ingredient occurrence"):
        EnrichmentResponse.from_stages(
            stage1,
            Stage2Response.model_validate(
                {"key_ingredients": [{"line_id": line_id, "occurrence_index": 9}]}
            ),
        )


def test_stage1_validation_rejects_ungrounded_quantity_and_unit() -> None:
    context = {
        "recipe": {
            "lines": [{"id": "line-1", "text": "2 tablespoons olive oil"}],
            "ai_parse_line_ids": ["line-1"],
        }
    }
    valid = Stage1Response.model_validate(
        {
            "parsed_lines": [
                {
                    "line_id": "line-1",
                    "occurrences": [
                        {"canonical_name": "Olive Oil", "quantity": "2", "unit": "tablespoon"}
                    ],
                }
            ]
        }
    )
    validate_stage1_response(context, valid)

    invalid = valid.model_copy(deep=True)
    invalid.parsed_lines[0].occurrences[0].quantity = "3"
    with pytest.raises(EnrichmentValidationError, match="quantity is not grounded"):
        validate_stage1_response(context, invalid)


@pytest.mark.parametrize("bad_line_id", ["line-1", "unknown-line"])
def test_stage1_validation_rejects_duplicate_or_unknown_line_ids(bad_line_id: str) -> None:
    context = {
        "recipe": {
            "lines": [{"id": "line-1", "text": "salt"}],
            "ai_parse_line_ids": ["line-1"],
        }
    }
    decisions = [{"line_id": bad_line_id, "occurrences": [{"canonical_name": "Salt"}]}]
    if bad_line_id == "line-1":
        decisions.append(decisions[0])
    response = Stage1Response.model_validate({"parsed_lines": decisions})

    with pytest.raises(EnrichmentValidationError, match=r"duplicate|exactly once"):
        validate_stage1_response(context, response)


def test_stage1_validation_failure_retries_complete_recipe(session) -> None:
    recipe = _recipe(session)
    line_id = str(recipe.ingredients_verbatim[0].id)
    primary = Mock()
    primary.enrich_recipe_stage1.return_value = (
        Stage1Response.model_validate(
            {
                "parsed_lines": [
                    {
                        "line_id": line_id,
                        "occurrences": [{"canonical_name": "Salt", "quantity": "99"}],
                    }
                ]
            }
        ),
        Usage(cost_usd=Decimal("0.001")),
    )
    fallback = Mock()
    fallback.enrich_recipe_stage1.return_value = (
        Stage1Response.model_validate(
            {"parsed_lines": [{"line_id": line_id, "occurrences": [{"canonical_name": "Salt"}]}]}
        ),
        Usage(cost_usd=Decimal("0.002")),
    )
    semantic = Mock()
    semantic.name = "ANTHROPIC"
    semantic.enrich_recipe_stage2.return_value = (
        Stage2Response.model_validate(
            {"key_ingredients": [{"line_id": line_id, "occurrence_index": 0}]}
        ),
        Usage(cost_usd=Decimal("0.003")),
    )

    result, usage = enrich_recipe(
        session,
        recipe.id,
        provider=StubProvider(""),
        stage1_provider=primary,
        stage1_fallback_provider=fallback,
        stage2_provider=semantic,
        stage1_model="flash-lite",
        stage1_fallback_model="haiku",
        stage2_model="haiku",
    )

    assert result["ai_parsed_lines"] == 1
    assert usage.cost_usd == Decimal("0.006")
    assert primary.enrich_recipe_stage1.call_count == 1
    assert fallback.enrich_recipe_stage1.call_count == 1
    assert (
        primary.enrich_recipe_stage1.call_args.args[0]
        == fallback.enrich_recipe_stage1.call_args.args[0]
    )
    stage2_context = semantic.enrich_recipe_stage2.call_args.args[0]
    assert (
        stage2_context["recipe"]["ingredient_lines"][0]["occurrences"][0]["canonical_name"]
        == "Salt"
    )


def test_explicit_enrichment_provider_settings_route_flash_lite_and_haiku(session) -> None:
    config = get_config(session)
    config.enrichment_stage1_provider = AIProvider.GEMINI
    config.enrichment_stage1_api_key = "gemini-key"
    config.enrichment_stage2_provider = AIProvider.ANTHROPIC
    config.enrichment_stage2_api_key = "anthropic-key"
    session.commit()

    stage1, stage2 = get_recipe_enrichment_providers(session)

    assert isinstance(stage1, GeminiProvider)
    assert isinstance(stage2, AnthropicProvider)
    assert stage1.model_for(ModelRole.RECIPE_INGREDIENTS) == "gemini-2.5-flash-lite"
    assert stage2.model_for(ModelRole.RECIPE_SEMANTICS) == "claude-haiku-4-5-20251001"


def test_configured_enrichment_provider_without_key_does_not_switch_silently(session) -> None:
    config = get_config(session)
    config.enrichment_stage1_provider = AIProvider.GEMINI
    config.enrichment_stage1_api_key = None
    session.commit()

    with pytest.raises(RuntimeError, match="configured without an API key"):
        get_recipe_enrichment_providers(session)


def test_repeated_new_canonical_ingredient_resolves_to_one_identity(session) -> None:
    recipe = _recipe(session)
    recipe.ingredients_verbatim.append(IngredientLine(position=1, text="more seaweed"))
    assert recipe.enrichment_state is not None
    recipe.enrichment_state.source_fingerprint = "current"
    session.commit()
    build_context(session, recipe)
    response = EnrichmentResponse.model_validate(
        {
            "parsed_lines": [
                {
                    "line_id": str(line.id),
                    "occurrences": [{"canonical_name": "Seaweed", "is_key": True}],
                }
                for line in recipe.ingredients_verbatim
            ],
            "cuisines": [],
            "methods": [],
            "courses": [],
            "keywords": ["Cosy", "Fresh", "Outdoor", "Party", "Summer"],
        }
    )
    apply_enrichment(
        session,
        recipe.id,
        response,
        provider=StubProvider(""),
        model="stub-enrichment",
    )
    session.commit()
    occurrences = session.query(IngredientOccurrence).order_by(IngredientOccurrence.position).all()
    assert len(occurrences) == 2
    assert occurrences[0].ingredient_id == occurrences[1].ingredient_id
