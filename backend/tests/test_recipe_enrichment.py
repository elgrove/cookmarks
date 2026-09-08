from decimal import Decimal
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.models.enums import AIProvider, RecipeEnrichmentStatus
from app.models.ingredient import CanonicalIngredient, RecipeIngredient
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
    Stage1LineDecision,
    Stage1Response,
    Stage2Response,
)
from app.services.recipe_enrichment.service import (
    EnrichmentValidationError,
    apply_enrichment,
    build_stage2_context,
    enrich_recipe,
    validate_stage1_response,
)
from app.services.recipe_facts import create_canonical_ingredient


def _recipe(session) -> Recipe:
    book_id = session.query(Recipe).first().book_id
    recipe = Recipe(book_id=book_id, order=99, name="Enriched", instructions=["Bake it."])
    recipe.ingredients = [RecipeIngredient(position=0, text="salt")]
    recipe.enrichment_state = RecipeEnrichmentState(
        status=RecipeEnrichmentStatus.PENDING, source_fingerprint="current"
    )
    session.add(recipe)
    session.commit()
    return recipe


def _response(recipe: Recipe | None = None, **overrides) -> EnrichmentResponse:
    fields = {
        "ingredients": [
            {"id": "01", "name": "olive oil", "is_key": True}
        ],
        "cuisines": [],
        "methods": [{"value_id": "bake", "is_primary": True}],
        "courses": [],
        "keywords": ["Cosy", "Fresh", "Outdoor", "Party", "Summer"],
    }
    alias_map = {
        "i": "ingredients",
        "c": "cuisines",
        "m": "methods",
        "o": "courses",
        "w": "keywords",
    }
    for k, v in overrides.items():
        fields[alias_map.get(k, k)] = v
    return EnrichmentResponse.model_validate(fields)


def test_apply_enrichment_replaces_all_derived_facts_atomically(session) -> None:
    recipe = _recipe(session)
    create_canonical_ingredient(session, "olive oil")
    result = apply_enrichment(
        session,
        recipe.id,
        _response(),
        provider=StubProvider(""),
        model="stub-enrichment",
    )
    session.commit()
    session.refresh(recipe)
    assert result["canonical_ingredients"] == 1
    assert result["key_ingredients"] == 1
    assert result["existing_ingredients"] == 1
    assert recipe.enrichment_state is not None
    assert recipe.enrichment_state.status is RecipeEnrichmentStatus.COMPLETE
    assert [item.canonical_name for item in recipe.ingredients if item.canonical_name] == ["olive oil"]
    assert [fact.facet_value.value_id for fact in recipe.facets] == ["bake"]
    assert {keyword.name for keyword in recipe.keywords} == {
        "Cosy",
        "Fresh",
        "Outdoor",
        "Party",
        "Summer",
    }


def test_empty_keywords_replace_previous_keywords(session) -> None:
    recipe = _recipe(session)
    recipe.keywords = [Keyword(name="Existing")]
    create_canonical_ingredient(session, "olive oil")
    session.commit()
    response = _response(keywords=[])
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
    assert len(recipe.canonical_ingredients) == 1


def test_response_normalises_prunes_and_truncates_residual_keywords(session) -> None:
    recipe = _recipe(session)
    response = _response(
        recipe,
        cuisines=["arabian-peninsula"],
        keywords=[
            "hakka-style",
            "olive oil",
            "bake",
            "Arabian Peninsula",
            "cosy",
            "Cosy",
            "One",
            "Two",
            "Three",
            "Four",
            "Five",
            "123",
        ],
    )

    apply_enrichment(session, recipe.id, response, provider=StubProvider(""), model="stub")

    assert response.keywords == ["Hakka-Style", "Cosy", "One", "Two", "Three"]


def test_stub_enrichment_is_separate_and_offline(session) -> None:
    recipe = _recipe(session)
    assert recipe.enrichment_state is not None
    recipe.enrichment_state.source_fingerprint = None  # migration-era row
    session.commit()
    result, usage = enrich_recipe(session, recipe.id, provider=StubProvider(""))
    session.refresh(recipe)
    assert result["canonical_ingredients"] >= 1
    assert usage.input_tokens == 0
    assert recipe.enrichment_state is not None
    assert recipe.enrichment_state.status is RecipeEnrichmentStatus.COMPLETE
    assert recipe.enrichment_state.source_fingerprint is not None
    assert len(recipe.keywords) <= 5


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


def test_enrichment_prompt_requires_central_methods() -> None:
    prompt = build_prompt(
        {
            "vocabulary": {"cuisines": [], "methods": [], "courses": []},
            "recipe": {
                "id": "recipe-id",
                "name": "Recipe",
                "instructions": [],
                "ingredients": [],
            },
        }
    )

    assert "central, intentional cooking technique" in prompt
    assert "Decide cuisines, methods and courses" in prompt


def test_response_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EnrichmentResponse.model_validate({"extra_field": "disallowed"})


def test_schema_version_tracks_the_bounded_output_change() -> None:
    assert SCHEMA_VERSION == "v8"


def test_stage1_prompt_requires_singular_uk_english() -> None:
    prompt = build_stage1_prompt(
        {
            "recipe": {
                "id": "recipe-1",
                "name": "Recipe",
                "ingredients": ["1 apple, sliced"],
            }
        }
    )

    assert "Singular UK-English canonical food name" in prompt
    assert "chilli" in prompt
    assert "Strip redundant nationality and regional prefixes" in prompt
    assert "Do not decide which ingredients are key" in prompt
    assert "Never extract salt or pepper" in prompt


def test_stage1_normalizer_excludes_salt_and_pepper() -> None:
    assert Stage1LineDecision(id="01", n="sea salt").name is None
    assert Stage1LineDecision(id="02", n="kosher salt").name is None
    assert Stage1LineDecision(id="03", n="table salt").name is None
    assert Stage1LineDecision(id="04", n="flaked sea salt").name is None
    assert Stage1LineDecision(id="05", n="black pepper").name is None
    assert Stage1LineDecision(id="06", n="white pepper").name is None
    assert Stage1LineDecision(id="07", n="freshly ground black pepper").name is None
    assert Stage1LineDecision(id="08", n="peppercorn").name is None
    assert Stage1LineDecision(id="09", n="salt and black pepper").name is None
    assert Stage1LineDecision(id="10", n="Maldon salt").name is None
    assert Stage1LineDecision(id="11", n="Himalayan pink salt").name is None
    assert Stage1LineDecision(id="12", n="pink Himalayan salt").name is None
    assert Stage1LineDecision(id="13", n="Himalayan rock salt").name is None
    assert Stage1LineDecision(id="14", n="pink salt").name is None
    assert Stage1LineDecision(id="15", n="fleur de sel").name is None
    assert Stage1LineDecision(id="16", n="Sichuan pepper").name == "Sichuan pepper"
    assert Stage1LineDecision(id="17", n="bell pepper").name == "bell pepper"
    assert Stage1LineDecision(id="18", n="chilli").name == "chilli"
    assert Stage1LineDecision(id="19", n="cayenne pepper").name == "cayenne pepper"
    assert Stage1LineDecision(id="20", n="kala namak").name == "kala namak"
    assert Stage1LineDecision(id="21", n="black salt").name == "black salt"
    assert Stage1LineDecision(id="22", n="smoked salt").name == "smoked salt"
    assert Stage1LineDecision(id="23", n="celery salt").name == "celery salt"


def test_stage1_schema_rejects_key_ingredient_decisions() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Stage1Response.model_validate({"k": ["apple"]})


def test_stage2_receives_structured_stage1_result_and_owns_key_selection(session) -> None:
    recipe = _recipe(session)
    stage1 = Stage1Response.model_validate(
        {"i": [{"id": "01", "n": "olive oil"}, {"id": "02", "n": "garlic"}]}
    )
    ingredients = ["olive oil", "garlic"]
    context = build_stage2_context(session, recipe, ingredients)
    assert context["recipe"]["ingredients"] == ingredients
    prompt = build_stage2_prompt(context)
    assert "Key ingredients (k)" in prompt

    response = EnrichmentResponse.from_stages(
        stage1,
        Stage2Response.model_validate(
            {"key_ingredients": ["garlic"]}
        ),
    )
    assert response.canonical_ingredients[1].is_key is True

    with pytest.raises(ValueError, match="unknown Stage 1 ingredient"):
        EnrichmentResponse.from_stages(
            stage1,
            Stage2Response.model_validate(
                {"key_ingredients": ["unknown-ingredient"]}
            ),
        )


def test_stage1_validation_rejects_empty_ingredients() -> None:
    context = {
        "recipe": {
            "id": "recipe-1",
            "lines": [{"id": "01", "text": "salt"}],
        }
    }
    with pytest.raises(EnrichmentValidationError, match="extracted no ingredient decisions"):
        validate_stage1_response(context, Stage1Response(i=[]))


def test_stage1_validation_failure_retries_complete_recipe(session) -> None:
    recipe = _recipe(session)
    primary = Mock()
    primary.enrich_recipe_stage1.return_value = (
        Stage1Response(i=[]),
        Usage(cost_usd=Decimal("0.001")),
    )
    fallback = Mock()
    fallback.enrich_recipe_stage1.return_value = (
        Stage1Response(i=[Stage1LineDecision(id="01", n="olive oil")]),
        Usage(cost_usd=Decimal("0.002")),
    )
    semantic = Mock()
    semantic.name = "ANTHROPIC"
    semantic.enrich_recipe_stage2.return_value = (
        Stage2Response.model_validate(
            {"key_ingredients": ["olive oil"]}
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

    assert result["canonical_ingredients"] == 1
    assert usage.cost_usd == Decimal("0.006")
    assert primary.enrich_recipe_stage1.call_count == 1
    assert fallback.enrich_recipe_stage1.call_count == 1
    assert (
        primary.enrich_recipe_stage1.call_args.args[0]
        == fallback.enrich_recipe_stage1.call_args.args[0]
    )
    stage2_context = semantic.enrich_recipe_stage2.call_args.args[0]
    assert stage2_context["recipe"]["ingredients"] == ["olive oil"]


def test_unknown_stage2_ingredient_retries_stage1_with_fallback(session) -> None:
    recipe = _recipe(session)
    recipe.ingredients.append(RecipeIngredient(position=1, text="garlic"))
    session.commit()
    primary = Mock()
    primary.enrich_recipe_stage1.return_value = (
        Stage1Response.model_validate(
            {"i": [{"id": "01", "n": "olive oil"}, {"id": "02", "n": None}]}
        ),
        Usage(cost_usd=Decimal("0.001")),
    )
    fallback = Mock()
    fallback.enrich_recipe_stage1.return_value = (
        Stage1Response.model_validate(
            {"i": [{"id": "01", "n": "olive oil"}, {"id": "02", "n": "garlic"}]}
        ),
        Usage(cost_usd=Decimal("0.002")),
    )
    semantic = Mock()
    semantic.name = "ANTHROPIC"
    semantic.enrich_recipe_stage2.side_effect = [
        (
            Stage2Response.model_validate({"key_ingredients": ["garlic"]}),
            Usage(cost_usd=Decimal("0.003")),
        ),
        (
            Stage2Response.model_validate({"key_ingredients": ["garlic"]}),
            Usage(cost_usd=Decimal("0.003")),
        ),
    ]

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

    assert result["stage1_fallback_used"] == 1
    assert usage.cost_usd == Decimal("0.009")
    assert primary.enrich_recipe_stage1.call_count == 1
    assert fallback.enrich_recipe_stage1.call_count == 1
    assert semantic.enrich_recipe_stage2.call_count == 2
    assert semantic.enrich_recipe_stage2.call_args_list[0].args[0]["recipe"]["ingredients"] == [
        "olive oil"
    ]
    assert semantic.enrich_recipe_stage2.call_args_list[1].args[0]["recipe"]["ingredients"] == [
        "olive oil",
        "garlic",
    ]


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
    recipe1 = _recipe(session)
    recipe2 = Recipe(book_id=recipe1.book_id, order=100, name="Enriched 2", instructions=["Bake."])
    recipe2.ingredients = [RecipeIngredient(position=0, text="seaweed")]
    recipe2.enrichment_state = RecipeEnrichmentState(
        status=RecipeEnrichmentStatus.PENDING, source_fingerprint="current2"
    )
    session.add(recipe2)
    session.commit()

    response1 = _response(i=[{"id": "01", "n": "Seaweed", "k": True}])
    response2 = _response(i=[{"id": "01", "n": "seaweed", "k": True}])

    apply_enrichment(session, recipe1.id, response1, provider=StubProvider(""), model="stub")
    session.commit()

    apply_enrichment(session, recipe2.id, response2, provider=StubProvider(""), model="stub")
    session.commit()
    session.refresh(recipe1)
    session.refresh(recipe2)

    ingredients = session.query(CanonicalIngredient).filter_by(name_folded="seaweed").all()
    assert len(ingredients) == 1
    assert recipe1.ingredients[0].canonical_ingredient_id == recipe2.ingredients[0].canonical_ingredient_id
