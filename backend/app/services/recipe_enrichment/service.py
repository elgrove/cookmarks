"""Validation, transactional application and orchestration for recipe enrichment."""

import json
import logging
import re
import uuid
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import (
    IngredientLineKind,
    IngredientParseMethod,
    IngredientResolutionMethod,
    RecipeEnrichmentStatus,
    RecipeFacetKind,
)
from app.models.ingredient import Ingredient, IngredientAlias, IngredientLine, IngredientOccurrence
from app.models.recipe import Recipe
from app.models.recipe_fact import RecipeCuisine, RecipeFacet, RecipeFacetValue
from app.services.ai import (
    AIProvider,
    AIResponseError,
    ModelRole,
    Usage,
    get_ai_provider,
    get_recipe_enrichment_providers,
)
from app.services.embeddings import embed_recipes
from app.services.keywords import get_or_create_keyword
from app.services.recipe_enrichment.schema import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    TAXONOMY_VERSION,
    EnrichmentResponse,
    Stage1Response,
)
from app.services.recipe_facts import (
    accepted_cuisine_ids,
    create_ingredient,
    upsert_facet_vocabulary,
)
from app.text import fold

logger = logging.getLogger(__name__)


class EnrichmentValidationError(ValueError):
    """The provider response violates the load-bearing enrichment contract."""


def source_fingerprint(recipe: Recipe) -> str:
    """The persisted equivalent of extraction's source fingerprint.

    MY-173 deliberately left migrated rows without a fingerprint. Computing it from
    the same source-only fields lets their first enrichment safely establish the
    idempotency boundary without re-extracting the book.
    """
    source = {
        "name": recipe.name,
        "description": recipe.description,
        "instructions": recipe.instructions,
        "ingredients": [line.text for line in recipe.ingredients_verbatim],
    }
    return sha256(
        json.dumps(source, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def ensure_source_fingerprint(recipe: Recipe) -> str:
    state = recipe.enrichment_state
    if state is None:
        raise EnrichmentValidationError("recipe has no enrichment state")
    if state.source_fingerprint is None:
        state.source_fingerprint = source_fingerprint(recipe)
    assert state.source_fingerprint is not None
    return state.source_fingerprint


def _recipe_with_facts(session: Session, recipe_id: uuid.UUID) -> Recipe:
    recipe = session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(
            selectinload(Recipe.ingredients_verbatim).selectinload(IngredientLine.occurrences),
            selectinload(Recipe.ingredients_verbatim),
            selectinload(Recipe.enrichment_state),
            selectinload(Recipe.keywords),
            selectinload(Recipe.facets).selectinload(RecipeFacet.facet_value),
            selectinload(Recipe.cuisines),
            selectinload(Recipe.book),
        )
    )
    if recipe is None:
        raise ValueError(f"Recipe {recipe_id} not found")
    return recipe


def _ingredient_vocab(session: Session) -> tuple[dict[str, Ingredient], dict[str, IngredientAlias]]:
    ingredients = {str(item.id): item for item in session.scalars(select(Ingredient))}
    aliases = {str(item.id): item for item in session.scalars(select(IngredientAlias))}
    return ingredients, aliases


def build_context(session: Session, recipe: Recipe) -> dict:
    """Build the provider input; stable vocabularies deliberately precede recipe data."""
    upsert_facet_vocabulary(session)
    session.flush()
    facets = list(session.scalars(select(RecipeFacetValue)))
    state = recipe.enrichment_state
    if state is None:
        raise EnrichmentValidationError("recipe has no enrichment state")
    ensure_source_fingerprint(recipe)
    return {
        "vocabulary": {
            "cuisines": sorted(accepted_cuisine_ids()),
            "methods": [
                {"id": item.value_id, "name": item.name}
                for item in facets
                if item.kind is RecipeFacetKind.METHOD
            ],
            "courses": [
                {"id": item.value_id, "name": item.name}
                for item in facets
                if item.kind is RecipeFacetKind.COURSE
            ],
        },
        "recipe": {
            **{
                "id": str(recipe.id),
                "name": recipe.name,
                "instructions": recipe.instructions,
                "lines": [
                    {"id": str(line.id), "text": line.text} for line in recipe.ingredients_verbatim
                ],
                "ai_parse_line_ids": [str(line.id) for line in recipe.ingredients_verbatim],
            },
            **({"description": recipe.description} if recipe.description else {}),
            **({"yield": recipe.yields} if recipe.yields else {}),
        },
    }


def build_stage1_context(
    recipe: Recipe,
) -> dict:
    ai_line_ids = [str(line.id) for line in recipe.ingredients_verbatim]
    return {
        "recipe": {
            "id": str(recipe.id),
            "instructions": recipe.instructions,
            "lines": [
                {"id": str(line.id), "text": line.text} for line in recipe.ingredients_verbatim
            ],
            "ai_parse_line_ids": ai_line_ids,
        }
    }


def build_stage2_context(
    session: Session,
    recipe: Recipe,
    stage1: Stage1Response,
    *,
    include_description: bool = True,
) -> dict:
    upsert_facet_vocabulary(session)
    session.flush()
    facets = list(session.scalars(select(RecipeFacetValue)))
    ctx = {
        "vocabulary": {
            "cuisines": sorted(accepted_cuisine_ids()),
            "methods": [
                {"id": item.value_id, "name": item.name}
                for item in facets
                if item.kind is RecipeFacetKind.METHOD
            ],
            "courses": [
                {"id": item.value_id, "name": item.name}
                for item in facets
                if item.kind is RecipeFacetKind.COURSE
            ],
        },
        "recipe": {
            "id": str(recipe.id),
            "name": recipe.name,
            "book_title": recipe.book.title if recipe.book else None,
            "book_author": recipe.book.author if recipe.book else None,
            "ingredient_lines": [
                {
                    "line_id": line.line_id,
                    "source": next(
                        source.text
                        for source in recipe.ingredients_verbatim
                        if str(source.id) == line.line_id
                    ),
                    "occurrences": [
                        occurrence.model_dump(by_alias=False) for occurrence in line.occurrences
                    ],
                }
                for line in stage1.parsed_lines
            ],
            "instructions": recipe.instructions,
        },
    }
    if include_description and recipe.description:
        ctx["recipe"]["description"] = recipe.description
    return ctx


_FRACTION_TRANSLATION = str.maketrans(
    {"½": " 1/2", "¼": " 1/4", "¾": " 3/4", "⅓": " 1/3", "⅔": " 2/3", "⅛": " 1/8"}
)
_UNIT_SOURCE_FORMS: dict[str, set[str]] = {
    "tsp": {"tsp", "teaspoon", "teaspoons"},
    "tbsp": {"tbsp", "tablespoon", "tablespoons"},
    "cup": {"cup", "cups"},
    "g": {"g", "gram", "grams"},
    "kg": {"kg", "kilogram", "kilograms"},
    "ml": {"ml", "millilitre", "millilitres", "milliliter", "milliliters"},
    "litre": {"l", "litre", "litres", "liter", "liters"},
    "oz": {"oz", "ounce", "ounces"},
    "lb": {"lb", "lbs", "pound", "pounds"},
    "clove": {"clove", "cloves"},
    "pinch": {"pinch", "pinches"},
}


def _grounding_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.translate(_FRACTION_TRANSLATION).casefold()).strip()


def _source_has_unit(source: str, unit: str) -> bool:
    normalised_source = _grounding_text(source)
    normalised_unit = _grounding_text(unit)
    forms = _UNIT_SOURCE_FORMS.get(normalised_unit)
    if forms is None:
        forms = next(
            (
                known_forms
                for known_forms in _UNIT_SOURCE_FORMS.values()
                if normalised_unit in known_forms
            ),
            {normalised_unit},
        )
    return any(re.search(rf"(?<!\w){re.escape(form)}(?!\w)", normalised_source) for form in forms)


def validate_stage1_response(context: dict, response: Stage1Response) -> None:
    """Validate complete line ownership and source-grounded numeric fields."""
    recipe = context["recipe"]
    lines = {str(line["id"]): str(line["text"]) for line in recipe["lines"]}
    expected = {str(line_id) for line_id in recipe["ai_parse_line_ids"]}
    parsed_ids = [decision.line_id for decision in response.parsed_lines]
    non_ingredient_ids = [decision.line_id for decision in response.non_ingredient_lines]
    decided = parsed_ids + non_ingredient_ids
    if len(decided) != len(set(decided)):
        raise EnrichmentValidationError("Stage 1 contains duplicate line decisions")
    if set(decided) != expected or not expected <= set(lines):
        raise EnrichmentValidationError("Stage 1 must decide every supplied line exactly once")
    for decision in response.parsed_lines:
        source = lines[decision.line_id]
        for occurrence in decision.occurrences:
            if occurrence.quantity and _grounding_text(occurrence.quantity) not in _grounding_text(
                source
            ):
                raise EnrichmentValidationError(
                    f"Stage 1 quantity is not grounded in line {decision.line_id}"
                )
            if occurrence.unit and not _source_has_unit(source, occurrence.unit):
                raise EnrichmentValidationError(
                    f"Stage 1 unit is not grounded in line {decision.line_id}"
                )


def _validate_keyword(value: str) -> str:
    name = value.strip()
    if not name or name != name.title():
        raise EnrichmentValidationError(f"keyword is not Title Case: {value!r}")
    return name


def _validate_response(
    session: Session,
    recipe: Recipe,
    response: EnrichmentResponse,
) -> None:
    lines = {str(line.id): line for line in recipe.ingredients_verbatim}
    parsed = {decision.line_id: decision for decision in response.parsed_lines}
    non_ingredient = {decision.line_id: decision for decision in response.non_ingredient_lines}
    if len(parsed) != len(response.parsed_lines) or len(non_ingredient) != len(
        response.non_ingredient_lines
    ):
        raise EnrichmentValidationError("response contains duplicate line decisions")
    if not (set(parsed) | set(non_ingredient)) <= set(lines):
        raise EnrichmentValidationError("response includes an unknown ingredient line")
    if set(parsed) & set(non_ingredient):
        raise EnrichmentValidationError("line cannot be both parsed and non-ingredient")
    if set(parsed) | set(non_ingredient) != set(lines):
        raise EnrichmentValidationError("response must decide every ingredient line")
    if any(not decision.occurrences for decision in response.parsed_lines):
        raise EnrichmentValidationError("parsed ingredient line has no occurrence")

    canonical, aliases = _ingredient_vocab(session)
    proposed = [occ.canonical_name for line in response.parsed_lines for occ in line.occurrences]
    proposed_folded = [fold(name) for name in proposed]

    cuisine_ids = response.cuisines
    if len(cuisine_ids) != len(set(cuisine_ids)) or not set(cuisine_ids) <= accepted_cuisine_ids():
        raise EnrichmentValidationError("response contains unknown or duplicate cuisine")
    values = {
        (item.kind, item.value_id): item for item in session.scalars(select(RecipeFacetValue))
    }
    method_ids = [fact.value_id for fact in response.methods]
    if len(method_ids) != len(set(method_ids)) or any(
        (RecipeFacetKind.METHOD, value_id) not in values for value_id in method_ids
    ):
        raise EnrichmentValidationError("response contains unknown or duplicate method")
    course_ids = response.courses
    if len(course_ids) != len(set(course_ids)) or any(
        (RecipeFacetKind.COURSE, value_id) not in values for value_id in course_ids
    ):
        raise EnrichmentValidationError("response contains unknown or duplicate course")
    if sum(fact.is_primary for fact in response.methods) > 1:
        raise EnrichmentValidationError("response has multiple primary methods")
    if len(response.keywords) > 5:
        raise EnrichmentValidationError("response must contain at most five residual keywords")
    keywords = [_validate_keyword(value) for value in response.keywords]
    folded_keywords = [fold(value) for value in keywords]
    if len(folded_keywords) != len(set(folded_keywords)):
        raise EnrichmentValidationError("response contains duplicate residual keywords")
    forbidden = set(cuisine_ids)
    forbidden |= {
        fold(values[(RecipeFacetKind.METHOD, fact.value_id)].name) for fact in response.methods
    }
    forbidden |= {
        fold(values[(RecipeFacetKind.COURSE, value_id)].name) for value_id in response.courses
    }
    forbidden |= {item.name_folded for item in canonical.values()} | {
        item.name_folded for item in aliases.values()
    }
    forbidden |= set(proposed_folded)
    if set(folded_keywords) & forbidden:
        raise EnrichmentValidationError(
            "residual keyword duplicates a structured fact or ingredient"
        )


def _apply_response(
    session: Session,
    recipe: Recipe,
    response: EnrichmentResponse,
    *,
    provider: AIProvider,
    model: str,
    task_run_id: uuid.UUID | None,
) -> dict[str, int]:
    _validate_response(session, recipe, response)
    state = recipe.enrichment_state
    assert state is not None
    created: dict[str, Ingredient] = {}
    canonical_by_name = {item.name_folded: item for item in session.scalars(select(Ingredient))}
    aliases_by_name = {item.name_folded: item for item in session.scalars(select(IngredientAlias))}
    aliases_created = 0
    existing_ingredients = 0
    occurrences_created = 0
    ai_lines = 0
    parsed_lines = {decision.line_id: decision for decision in response.parsed_lines}
    non_ingredient_lines = {
        decision.line_id: decision for decision in response.non_ingredient_lines
    }
    for line in recipe.ingredients_verbatim:
        line_id = str(line.id)
        session.execute(delete(IngredientOccurrence).where(IngredientOccurrence.line_id == line.id))
        parsed = []
        if line_id in non_ingredient_lines:
            line.kind = IngredientLineKind(non_ingredient_lines[line_id].kind)
        else:
            decision = parsed_lines[line_id]
            line.kind = IngredientLineKind.INGREDIENT
            ai_lines += 1
            parsed = [(item, IngredientParseMethod.AI, item) for item in decision.occurrences]
        for position, (_raw, parse_method, decision_occurrence) in enumerate(parsed):
            assert decision_occurrence is not None
            canonical_name = decision_occurrence.canonical_name
            name_folded = fold(canonical_name)
            ingredient = canonical_by_name.get(name_folded)
            if ingredient is None:
                alias = aliases_by_name.get(name_folded)
                ingredient = alias.ingredient if alias is not None else None
            if ingredient is not None:
                resolution = IngredientResolutionMethod.AI_EXISTING
                existing_ingredients += 1
            else:
                ingredient = created.get(name_folded)
                if ingredient is None:
                    ingredient = create_ingredient(session, canonical_name)
                    created[name_folded] = ingredient
                resolution = IngredientResolutionMethod.AI_CREATED
            session.add(
                IngredientOccurrence(
                    line_id=line.id,
                    ingredient_id=ingredient.id,
                    position=position,
                    quantity=decision_occurrence.quantity,
                    unit=decision_occurrence.unit,
                    preparation=decision_occurrence.preparation,
                    optional=decision_occurrence.optional,
                    alternative_group=decision_occurrence.alternative_group,
                    is_key=decision_occurrence.is_key,
                    parse_method=parse_method,
                    resolution_method=resolution,
                )
            )
            occurrences_created += 1

    recipe.facets.clear()
    recipe.cuisines.clear()
    session.flush()
    facet_values = {
        (item.kind, item.value_id): item for item in session.scalars(select(RecipeFacetValue))
    }
    for fact in response.methods:
        recipe.facets.append(
            RecipeFacet(
                facet_value_id=facet_values[(RecipeFacetKind.METHOD, fact.value_id)].id,
                is_primary=fact.is_primary,
            )
        )
    for course_id in response.courses:
        recipe.facets.append(
            RecipeFacet(
                facet_value_id=facet_values[(RecipeFacetKind.COURSE, course_id)].id,
                is_primary=False,
            )
        )
    recipe.cuisines = [RecipeCuisine(cuisine_id=cuisine_id) for cuisine_id in response.cuisines]
    recipe.keywords = [get_or_create_keyword(session, value.strip()) for value in response.keywords]
    state.status = RecipeEnrichmentStatus.COMPLETE
    state.schema_version = SCHEMA_VERSION
    state.prompt_version = PROMPT_VERSION
    state.taxonomy_version = TAXONOMY_VERSION
    state.provider = provider.name
    state.model = model
    state.task_run_id = task_run_id
    state.last_error = None
    state.started_at = state.started_at or datetime.now(UTC)
    state.completed_at = datetime.now(UTC)
    return {
        "occurrences": occurrences_created,
        "ai_parsed_lines": ai_lines,
        "ingredients_created": len(created),
        "existing_ingredients": existing_ingredients,
        "aliases_created": aliases_created,
        "headings": sum(
            line.kind is IngredientLineKind.HEADING for line in recipe.ingredients_verbatim
        ),
    }


def apply_enrichment(
    session: Session,
    recipe_id: uuid.UUID,
    response: EnrichmentResponse,
    *,
    provider: AIProvider,
    model: str,
    task_run_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Validate before mutation; a bad completion leaves old facts and keywords intact."""
    recipe = _recipe_with_facts(session, recipe_id)
    try:
        with session.begin_nested():
            result = _apply_response(
                session,
                recipe,
                response,
                provider=provider,
                model=model,
                task_run_id=task_run_id,
            )
            session.flush()
        return result
    except Exception as exc:
        logger.info("Recipe enrichment rejected for %s: %s", recipe_id, exc)
        state = _recipe_with_facts(session, recipe_id).enrichment_state
        assert state is not None
        state.status = RecipeEnrichmentStatus.FAILED
        state.last_error = str(exc)[:1000]
        state.completed_at = datetime.now(UTC)
        session.flush()
        raise


def _run_stage1(
    context: dict,
    provider: AIProvider,
    model: str,
) -> tuple[Stage1Response, Usage]:
    try:
        response, usage = provider.enrich_recipe_stage1(context, model)
        validate_stage1_response(context, response)
        return response, usage
    except AIResponseError:
        raise
    except EnrichmentValidationError as exc:
        raise AIResponseError(str(exc), usage) from exc


def enrich_recipe(
    session: Session,
    recipe_id: uuid.UUID,
    *,
    provider: AIProvider | None = None,
    stage1_provider: AIProvider | None = None,
    stage1_fallback_provider: AIProvider | None = None,
    stage2_provider: AIProvider | None = None,
    stage1_model: str | None = None,
    stage1_fallback_model: str | None = None,
    stage2_model: str | None = None,
    task_run_id: uuid.UUID | None = None,
    include_description: bool = True,
) -> tuple[dict[str, int], Usage]:
    """Execute two-stage enrichment and atomically persist the valid response."""
    recipe = _recipe_with_facts(session, recipe_id)
    state = recipe.enrichment_state
    if state is not None and state.status is RecipeEnrichmentStatus.COMPLETE:
        return {"skipped": 1}, Usage()
    configured_stage1 = None
    configured_stage2 = None
    if stage1_provider is None or stage1_fallback_provider is None or stage2_provider is None:
        configured_stage1, configured_stage2 = get_recipe_enrichment_providers(session)
    base_provider = provider or stage1_provider or configured_stage1 or get_ai_provider(session)
    if base_provider is None:
        raise RuntimeError("No usable AI provider is configured")
    stage1_provider = stage1_provider or configured_stage1 or base_provider
    stage2_provider = stage2_provider or configured_stage2 or base_provider
    stage1_fallback_provider = stage1_fallback_provider or configured_stage2 or base_provider
    if state is None:
        raise EnrichmentValidationError("recipe has no enrichment state")
    ensure_source_fingerprint(recipe)
    state.status = RecipeEnrichmentStatus.RUNNING
    state.started_at = datetime.now(UTC)
    session.commit()
    recipe = _recipe_with_facts(session, recipe_id)
    build_context(session, recipe)
    stage1_model = stage1_model or stage1_provider.model_for(ModelRole.RECIPE_INGREDIENTS)
    stage1_fallback_model = stage1_fallback_model or stage1_fallback_provider.model_for(
        ModelRole.RECIPE_INGREDIENTS_FALLBACK
    )
    stage2_model = stage2_model or stage2_provider.model_for(ModelRole.RECIPE_SEMANTICS)
    stage1_fallback_used = False
    try:
        stage1_context = build_stage1_context(recipe)
        if not stage1_context["recipe"]["ai_parse_line_ids"]:
            stage1_response = Stage1Response(p=[], n=[])
            usage1 = Usage()
        else:
            try:
                stage1_response, usage1 = _run_stage1(stage1_context, stage1_provider, stage1_model)
            except AIResponseError as primary_exc:
                stage1_fallback_used = True
                logger.info(
                    "Stage 1 failed validation for recipe %s with %s; retrying the complete recipe with %s",
                    recipe_id,
                    stage1_model,
                    stage1_fallback_model,
                )
                try:
                    stage1_response, fallback_usage = _run_stage1(
                        stage1_context,
                        stage1_fallback_provider,
                        stage1_fallback_model,
                    )
                except AIResponseError as fallback_exc:
                    raise AIResponseError(
                        str(fallback_exc), primary_exc.usage + fallback_exc.usage
                    ) from fallback_exc
                usage1 = primary_exc.usage + fallback_usage

        stage2_context = build_stage2_context(
            session, recipe, stage1_response, include_description=include_description
        )
        stage2_response, usage2 = stage2_provider.enrich_recipe_stage2(stage2_context, stage2_model)

        usage = usage1 + usage2
        try:
            response = EnrichmentResponse.from_stages(stage1_response, stage2_response)
        except ValueError as exc:
            raise AIResponseError(f"Invalid Stage 2 response: {exc}", usage) from exc

        applied_stage1_model = (
            f"{stage1_model} (fallback {stage1_fallback_model})"
            if stage1_fallback_used
            else stage1_model
        )
        result = apply_enrichment(
            session,
            recipe_id,
            response,
            provider=stage2_provider,
            model=f"{applied_stage1_model} -> {stage2_model}",
            task_run_id=task_run_id,
        )
        result["stage1_fallback_used"] = int(stage1_fallback_used)
        completed_state = _recipe_with_facts(session, recipe_id).enrichment_state
        assert completed_state is not None
        completed_state.provider = f"{stage1_provider.name}->{stage2_provider.name}"
        session.commit()
    except Exception as exc:
        failed_recipe = _recipe_with_facts(session, recipe_id)
        failed_state = failed_recipe.enrichment_state
        if failed_state is not None and failed_state.status is RecipeEnrichmentStatus.RUNNING:
            failed_state.status = RecipeEnrichmentStatus.FAILED
            failed_state.last_error = str(exc)[:1000]
            failed_state.completed_at = datetime.now(UTC)
        session.commit()
        raise
    # Embedding intentionally follows the fact transaction: a failed embedding never
    # turns an otherwise valid enrichment into a failed one.
    try:
        embed_recipes(session, [_recipe_with_facts(session, recipe_id)], base_provider)
        session.commit()
    except Exception:
        logger.exception("Embedding refresh failed after enrichment for %s", recipe_id)
    return result, usage


def aggregate_metrics(results: list[dict[str, int]]) -> dict[str, int]:
    totals = Counter()
    for result in results:
        totals.update(result)
    return dict(totals)
