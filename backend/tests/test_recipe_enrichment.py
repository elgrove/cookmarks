import uuid

import pytest
from pydantic import ValidationError

from app.models.enums import RecipeEnrichmentStatus
from app.models.ingredient import IngredientLine, IngredientOccurrence
from app.models.recipe import Keyword, Recipe
from app.models.recipe_enrichment import RecipeEnrichmentState
from app.services.ai.stub import StubProvider
from app.services.recipe_enrichment.prompt import build_prompt
from app.services.recipe_enrichment.schema import (
    ENRICHMENT_JSON_SCHEMA,
    SCHEMA_VERSION,
    EnrichmentResponse,
)
from app.services.recipe_enrichment.service import (
    EnrichmentValidationError,
    apply_enrichment,
    build_context,
    enrich_recipe,
)
from app.services.recipe_facts import create_ingredient


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


def _response(recipe: Recipe, ingredient_id: uuid.UUID, **overrides) -> EnrichmentResponse:
    data = {
        "recipe_id": str(recipe.id),
        "source_fingerprint": "current",
        "parsed_lines": [
            {
                "line_id": str(recipe.ingredients_verbatim[0].id),
                "occurrences": [{"ingredient_id": str(ingredient_id), "is_key": True}],
            }
        ],
        "cuisines": [],
        "methods": [
            {"value_id": "bake", "source": "explicit", "evidence": "Bake it.", "is_primary": True}
        ],
        "courses": [],
        "keywords": ["Cosy", "Fresh", "Outdoor", "Party", "Summer"],
    }
    data.update(overrides)
    return EnrichmentResponse.model_validate(data)


def test_apply_enrichment_replaces_all_derived_facts_atomically(session) -> None:
    recipe = _recipe(session)
    ingredient = create_ingredient(session, "Sea Salt")
    context, proposals = build_context(session, recipe)
    assert context["recipe"]["ai_parse_line_ids"] == [str(recipe.ingredients_verbatim[0].id)]
    result = apply_enrichment(
        session,
        recipe.id,
        _response(recipe, ingredient.id),
        proposals,
        provider=StubProvider(""),
        model="stub-enrichment",
    )
    session.commit()
    session.refresh(recipe)
    assert result["occurrences"] == 1
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


def test_invalid_response_rolls_back_and_keeps_previous_keywords(session) -> None:
    recipe = _recipe(session)
    recipe.keywords = [Keyword(name="Existing")]
    ingredient = create_ingredient(session, "Sea Salt")
    session.commit()
    _, proposals = build_context(session, recipe)
    bad = _response(recipe, ingredient.id, keywords=["Only", "Four", "Keywords", "Here"])
    with pytest.raises(EnrichmentValidationError, match="exactly five"):
        apply_enrichment(
            session,
            recipe.id,
            bad,
            proposals,
            provider=StubProvider(""),
            model="stub-enrichment",
        )
    session.commit()
    session.refresh(recipe)
    assert recipe.enrichment_state is not None
    assert recipe.enrichment_state.status is RecipeEnrichmentStatus.FAILED
    assert [keyword.name for keyword in recipe.keywords] == ["Existing"]
    assert recipe.ingredients_verbatim[0].kind is None
    assert session.query(IngredientOccurrence).count() == 0


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
    ingredient = create_ingredient(session, "Sea Salt")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _response(
            recipe,
            ingredient.id,
            courses=[{"value_id": "main", "source": "inferred", "is_primary": True}],
        )
    definitions = ENRICHMENT_JSON_SCHEMA["$defs"]
    assert "p" not in definitions["FactDecision"]["properties"]
    assert "p" in definitions["MethodDecision"]["properties"]


def test_response_rejects_ambiguous_occurrence_resolution(session) -> None:
    recipe = _recipe(session)
    ingredient = create_ingredient(session, "Sea Salt")
    with pytest.raises(ValidationError, match="exactly one"):
        _response(
            recipe,
            ingredient.id,
            parsed_lines=[
                {
                    "line_id": str(recipe.ingredients_verbatim[0].id),
                    "occurrences": [
                        {
                            "ingredient_id": str(ingredient.id),
                            "canonical_name": "Sea Salt",
                        }
                    ],
                }
            ],
        )


def test_response_rejects_missing_ai_line_decision(session) -> None:
    recipe = _recipe(session)
    ingredient = create_ingredient(session, "Sea Salt")
    _, proposals = build_context(session, recipe)
    assert not proposals
    response = _response(
        recipe,
        ingredient.id,
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


def test_schema_version_tracks_the_constrained_output_change() -> None:
    assert SCHEMA_VERSION == "v3"


def test_prompt_distinguishes_deterministic_and_ai_line_decisions(session) -> None:
    recipe = _recipe(session)
    context, _ = build_context(session, recipe)
    prompt = build_prompt(context)
    assert "Omit accepted deterministic proposals entirely" in prompt
    assert "never\nboth" in prompt


def test_repeated_new_canonical_ingredient_resolves_to_one_identity(session) -> None:
    recipe = _recipe(session)
    recipe.ingredients_verbatim.append(IngredientLine(position=1, text="more seaweed"))
    assert recipe.enrichment_state is not None
    recipe.enrichment_state.source_fingerprint = "current"
    session.commit()
    _, proposals = build_context(session, recipe)
    response = EnrichmentResponse.model_validate(
        {
            "recipe_id": str(recipe.id),
            "source_fingerprint": "current",
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
