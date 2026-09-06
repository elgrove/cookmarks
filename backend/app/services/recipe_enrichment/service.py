"""Validation, transactional application and orchestration for recipe enrichment."""

import json
import logging
import uuid
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import (
    RecipeEnrichmentStatus,
    RecipeFacetKind,
)
from app.models.ingredient import Ingredient, RecipeCanonicalIngredient
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
    normalize_ingredient_name,
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
            selectinload(Recipe.ingredients_verbatim),
            selectinload(Recipe.canonical_ingredients).joinedload(
                RecipeCanonicalIngredient.ingredient
            ),
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


def _ingredient_vocab(session: Session) -> dict[str, Ingredient]:
    return {str(item.id): item for item in session.scalars(select(Ingredient))}


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
    return {
        "recipe": {
            "id": str(recipe.id),
            "name": recipe.name,
            "ingredients": [line.text for line in recipe.ingredients_verbatim],
        }
    }


def deduplicate_ingredient_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for name in names:
        norm = normalize_ingredient_name(name)
        folded = norm.casefold()
        if folded and folded not in seen:
            seen.add(folded)
            unique.append(norm)
    return unique


def build_stage2_context(
    session: Session,
    recipe: Recipe,
    ingredients: list[str],
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
            "ingredients": ingredients,
            "instructions": recipe.instructions,
        },
    }
    if include_description and recipe.description:
        ctx["recipe"]["description"] = recipe.description
    return ctx


def validate_stage1_response(context: dict, response: Stage1Response) -> None:
    """Validate that Stage 1 extracted valid ingredients when ingredients exist."""
    recipe = context["recipe"]
    ingredients = recipe.get("ingredients", [])
    if ingredients and not response.ingredients:
        raise EnrichmentValidationError("Stage 1 extracted no ingredients from recipe")


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
    upsert_facet_vocabulary(session)
    session.flush()
    for item in response.canonical_ingredients:
        if not item.name.strip():
            raise EnrichmentValidationError("canonical ingredient name cannot be empty")
    if sum(item.is_key for item in response.canonical_ingredients) > 3:
        raise EnrichmentValidationError("response must contain at most three key ingredients")
    if response.canonical_ingredients and not any(
        item.is_key for item in response.canonical_ingredients
    ):
        raise EnrichmentValidationError("response must contain at least one key ingredient")

    names = [item.name for item in response.canonical_ingredients]
    folded_names = [fold(name) for name in names]
    if len(folded_names) != len(set(folded_names)):
        raise EnrichmentValidationError("response contains duplicate canonical ingredients")

    canonical = {item.name_folded: item for item in session.scalars(select(Ingredient))}

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
    forbidden |= set(canonical.keys())
    forbidden |= set(folded_names)
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
    existing_ingredients = 0

    session.execute(
        delete(RecipeCanonicalIngredient).where(RecipeCanonicalIngredient.recipe_id == recipe.id)
    )

    for item in response.canonical_ingredients:
        name_folded = fold(item.name)
        ingredient = canonical_by_name.get(name_folded)
        if ingredient is not None:
            existing_ingredients += 1
        else:
            ingredient = created.get(name_folded)
            if ingredient is None:
                ingredient = create_ingredient(session, item.name)
                created[name_folded] = ingredient
                canonical_by_name[name_folded] = ingredient
        session.add(
            RecipeCanonicalIngredient(
                recipe_id=recipe.id,
                ingredient_id=ingredient.id,
                is_key=item.is_key,
            )
        )

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
        "canonical_ingredients": len(response.canonical_ingredients),
        "key_ingredients": sum(item.is_key for item in response.canonical_ingredients),
        "ingredients_created": len(created),
        "existing_ingredients": existing_ingredients,
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
        if not stage1_context["recipe"]["ingredients"]:
            stage1_response = Stage1Response(i=[])
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

        unique_ingredients = deduplicate_ingredient_names(stage1_response.ingredients)
        stage2_context = build_stage2_context(
            session, recipe, unique_ingredients, include_description=include_description
        )
        stage2_response, usage2 = stage2_provider.enrich_recipe_stage2(stage2_context, stage2_model)

        usage = usage1 + usage2
        try:
            response = EnrichmentResponse.from_stages(unique_ingredients, stage2_response)
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
