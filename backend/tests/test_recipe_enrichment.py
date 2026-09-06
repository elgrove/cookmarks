import pytest
from pydantic import ValidationError

from app.models.enums import IngredientLineKind, RecipeEnrichmentStatus
from app.models.ingredient import IngredientLine, IngredientOccurrence
from app.models.recipe import Keyword, Recipe
from app.models.recipe_enrichment import RecipeEnrichmentState
from app.services.ai.stub import StubProvider
from app.services.recipe_enrichment.prompt import build_prompt, build_stage1_prompt
from app.services.recipe_enrichment.schema import (
    ENRICHMENT_JSON_SCHEMA,
    GEMINI_ENRICHMENT_JSON_SCHEMA,
    SCHEMA_VERSION,
    EnrichmentResponse,
)
from app.services.recipe_enrichment.service import (
    EnrichmentValidationError,
    apply_enrichment,
    build_context,
    enrich_recipe,
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
    context, proposals = build_context(session, recipe)
    assert context["recipe"]["ai_parse_line_ids"] == [str(recipe.ingredients_verbatim[0].id)]
    result = apply_enrichment(
        session,
        recipe.id,
        _response(recipe),
        proposals,
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
    _, proposals = build_context(session, recipe)

    result = apply_enrichment(
        session,
        recipe.id,
        response,
        proposals,
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
    _, proposals = build_context(session, recipe)
    response = _response(recipe, keywords=[])
    apply_enrichment(
        session,
        recipe.id,
        response,
        proposals,
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
    _, proposals = build_context(session, recipe)
    assert not proposals
    response = _response(
        recipe,
        parsed_lines=[],
    )
    with pytest.raises(EnrichmentValidationError, match="must decide every AI-parsed"):
        apply_enrichment(
            session,
            recipe.id,
            response,
            proposals,
            provider=StubProvider(""),
            model="stub-enrichment",
        )


def test_schema_version_tracks_the_bounded_output_change() -> None:
    assert SCHEMA_VERSION == "v6"


def test_prompt_distinguishes_deterministic_and_ai_line_decisions(session) -> None:
    recipe = _recipe(session)
    context, _ = build_context(session, recipe)
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


def test_repeated_new_canonical_ingredient_resolves_to_one_identity(session) -> None:
    recipe = _recipe(session)
    recipe.ingredients_verbatim.append(IngredientLine(position=1, text="more seaweed"))
    assert recipe.enrichment_state is not None
    recipe.enrichment_state.source_fingerprint = "current"
    session.commit()
    _, proposals = build_context(session, recipe)
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
        proposals,
        provider=StubProvider(""),
        model="stub-enrichment",
    )
    session.commit()
    occurrences = session.query(IngredientOccurrence).order_by(IngredientOccurrence.position).all()
    assert len(occurrences) == 2
    assert occurrences[0].ingredient_id == occurrences[1].ingredient_id
