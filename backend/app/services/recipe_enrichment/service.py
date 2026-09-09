"""Validation, transactional application and orchestration for recipe enrichment."""

import json
import logging
import re
import threading
import uuid
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import (
    RecipeEnrichmentStatus,
    RecipeFacetKind,
)
from app.models.ingredient import CanonicalIngredient, RecipeIngredient
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
from app.services.keywords import get_or_create_keyword
from app.services.recipe_enrichment.schema import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    TAXONOMY_VERSION,
    EnrichmentResponse,
    MethodDecision,
    Stage1Response,
    normalize_ingredient_name,
)
from app.services.recipe_facts import (
    accepted_cuisine_ids,
    get_or_create_canonical_ingredient,
    upsert_facet_vocabulary,
)
from app.text import fold

logger = logging.getLogger(__name__)

_enrichment_write_lock = threading.RLock()
_KEYWORD_WORD = re.compile(r"[^\W\d_]+(?:['\u2019][^\W\d_]+)?", re.UNICODE)
_KEYWORD_INVALID_CHARACTERS = re.compile(r"[^\w\s'\u2019\-]", re.UNICODE)
_KEYWORD_FORMAT = re.compile(
    r"[^\W\d_]+(?:[ '\-][^\W\d_]+(?:['\u2019][^\W\d_]+)?)*", re.UNICODE
)


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
            selectinload(Recipe.ingredients).joinedload(
                RecipeIngredient.canonical_ingredient
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


def _ingredient_vocab(session: Session) -> dict[str, CanonicalIngredient]:
    return {str(item.id): item for item in session.scalars(select(CanonicalIngredient))}


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
            "lines": [
                {"id": f"{i:02d}", "text": line.text}
                for i, line in enumerate(recipe.ingredients, start=1)
            ],
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
    """Validate that Stage 1 extracted valid decisions when lines exist."""
    recipe = context["recipe"]
    lines = recipe.get("lines", [])
    if lines and not response.ingredients:
        raise EnrichmentValidationError("Stage 1 extracted no ingredient decisions from recipe")


def _validate_keyword(value: str) -> str | None:
    """Return a display-safe residual keyword, or discard provider noise."""
    name = _KEYWORD_INVALID_CHARACTERS.sub("", value.strip())
    name = " ".join(name.split())
    if not name or not _KEYWORD_FORMAT.fullmatch(name):
        return None
    return _KEYWORD_WORD.sub(lambda match: match.group(0).capitalize(), name)


def _keyword_fold(value: str) -> str:
    """Fold residual keyword text and make word separators equivalent."""
    return " ".join(fold(value).replace("-", " ").split())


def sanitize_enrichment_response(
    session: Session, response: EnrichmentResponse
) -> None:
    """Filter unrecognised identifiers and deduplicate cuisines, methods, and courses."""
    accepted_cuisines = accepted_cuisine_ids()
    response.cuisines = list(
        dict.fromkeys(c for c in response.cuisines if c in accepted_cuisines)
    )

    values = {
        (item.kind, item.value_id): item for item in session.scalars(select(RecipeFacetValue))
    }
    seen_methods: set[str] = set()
    clean_methods: list[MethodDecision] = []
    has_primary = False
    for fact in response.methods:
        if (
            (RecipeFacetKind.METHOD, fact.value_id) in values
            and fact.value_id not in seen_methods
        ):
            seen_methods.add(fact.value_id)
            is_primary = fact.is_primary and not has_primary
            if is_primary:
                has_primary = True
            clean_methods.append(MethodDecision(v=fact.value_id, p=is_primary))
    response.methods = clean_methods

    response.courses = list(
        dict.fromkeys(
            c for c in response.courses if (RecipeFacetKind.COURSE, c) in values
        )
    )


def _validate_response(
    session: Session,
    recipe: Recipe,
    response: EnrichmentResponse,
) -> None:
    upsert_facet_vocabulary(session)
    session.flush()
    canonical_items = [item for item in response.ingredients if item.name]
    distinct_keys = {
        item.name.casefold()
        for item in canonical_items
        if item.name and item.is_key
    }
    if len(distinct_keys) > 3:
        raise EnrichmentValidationError("response must contain at most three key ingredients")
    if canonical_items and not distinct_keys:
        raise EnrichmentValidationError("response must contain at least one key ingredient")

    names = [item.name for item in canonical_items if item.name]
    folded_names = [_keyword_fold(name) for name in names]

    canonical = {
        _keyword_fold(item.name): item for item in session.scalars(select(CanonicalIngredient))
    }

    sanitize_enrichment_response(session, response)
    cuisine_ids = response.cuisines
    values = {
        (item.kind, item.value_id): item for item in session.scalars(select(RecipeFacetValue))
    }
    forbidden = {_keyword_fold(cuisine_id) for cuisine_id in cuisine_ids}
    forbidden |= {
        _keyword_fold(values[(RecipeFacetKind.METHOD, fact.value_id)].name)
        for fact in response.methods
    }
    forbidden |= {
        _keyword_fold(values[(RecipeFacetKind.COURSE, value_id)].name)
        for value_id in response.courses
    }
    forbidden |= set(canonical.keys())
    forbidden |= set(folded_names)
    keywords: list[str] = []
    seen_keywords: set[str] = set()
    for value in response.keywords:
        keyword = _validate_keyword(value)
        if keyword is None:
            continue
        folded_keyword = _keyword_fold(keyword)
        if folded_keyword in seen_keywords or folded_keyword in forbidden:
            continue
        seen_keywords.add(folded_keyword)
        keywords.append(keyword)
    response.keywords = keywords[:5]


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
    created: dict[str, CanonicalIngredient] = {}
    canonical_by_name = {
        item.name_folded: item for item in session.scalars(select(CanonicalIngredient))
    }
    existing_ingredients = 0

    decisions_by_id = {item.line_id: item for item in response.ingredients}

    for i, line in enumerate(recipe.ingredients, start=1):
        line_id = f"{i:02d}"
        decision = decisions_by_id.get(line_id)
        if decision is None or not decision.name:
            line.canonical_ingredient_id = None
            line.is_key = False
            continue

        canonical_name = decision.name
        name_folded = fold(canonical_name)
        canonical = canonical_by_name.get(name_folded)
        if canonical is not None:
            existing_ingredients += 1
        else:
            canonical = created.get(name_folded)
            if canonical is None:
                canonical = get_or_create_canonical_ingredient(session, canonical_name)
                created[name_folded] = canonical
                canonical_by_name[name_folded] = canonical

        line.canonical_ingredient_id = canonical.id
        line.is_key = decision.is_key

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
        "canonical_ingredients": sum(
            line.canonical_ingredient_id is not None for line in recipe.ingredients
        ),
        "key_ingredients": sum(line.is_key for line in recipe.ingredients),
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
    with _enrichment_write_lock:
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
    temp: float = 0,
) -> tuple[Stage1Response, Usage]:
    try:
        response, usage = provider.enrich_recipe_stage1(context, model, temp=temp)
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
    with _enrichment_write_lock:
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
        session.rollback()
        if not stage1_context["recipe"]["lines"]:
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
                        temp=0.2,
                    )
                except AIResponseError as fallback_exc:
                    raise AIResponseError(
                        str(fallback_exc), primary_exc.usage + fallback_exc.usage
                    ) from fallback_exc
                usage1 = primary_exc.usage + fallback_usage

        usage = usage1
        stage2_retried = False
        while True:
            stage1_names = [item.name for item in stage1_response.ingredients if item.name]
            unique_ingredients = deduplicate_ingredient_names(stage1_names)
            recipe = _recipe_with_facts(session, recipe_id)
            stage2_context = build_stage2_context(
                session, recipe, unique_ingredients, include_description=include_description
            )
            session.rollback()
            try:
                stage2_response, usage2 = stage2_provider.enrich_recipe_stage2(
                    stage2_context,
                    stage2_model,
                    allow_truncate_keys=stage2_retried,
                    temp=0.2 if stage2_retried else 0.0,
                )
            except AIResponseError as stage2_exc:
                if not stage2_retried:
                    stage2_retried = True
                    usage += stage2_exc.usage
                    logger.info(
                        "Stage 2 failed validation for recipe %s (%s); retrying Stage 2 with %s",
                        recipe_id,
                        stage2_exc,
                        stage2_model,
                    )
                    continue
                raise
            usage += usage2
            if unique_ingredients and not stage2_response.key_ingredients:
                if not stage2_retried:
                    stage2_retried = True
                    logger.info(
                        "Stage 2 selected 0 key ingredients for recipe %s; retrying Stage 2 with %s",
                        recipe_id,
                        stage2_model,
                    )
                    continue
                stage2_response.key_ingredients = [unique_ingredients[0]]
                logger.info(
                    "Stage 2 selected 0 key ingredients on retry for recipe %s; falling back to %s",
                    recipe_id,
                    unique_ingredients[0],
                )
            try:
                response = EnrichmentResponse.from_stages(stage1_response, stage2_response)
            except ValueError as exc:
                if str(exc) == "Stage 2 refers to an unknown Stage 1 ingredient":
                    if not stage1_fallback_used:
                        stage1_fallback_used = True
                        logger.info(
                            "Stage 2 selected an unknown Stage 1 ingredient for recipe %s; "
                            "retrying Stage 1 with %s",
                            recipe_id,
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
                                str(fallback_exc), usage + fallback_exc.usage
                            ) from fallback_exc
                        usage += fallback_usage
                        continue
                    elif not stage2_retried:
                        stage2_retried = True
                        logger.info(
                            "Stage 2 selected an unknown Stage 1 ingredient for recipe %s after Stage 1 fallback; "
                            "retrying Stage 2 with %s",
                            recipe_id,
                            stage2_model,
                        )
                        continue
                    if unique_ingredients:
                        ings_folded = {u.casefold(): u for u in unique_ingredients}
                        valid_keys: list[str] = []
                        for k in stage2_response.key_ingredients:
                            k_str = str(k).strip()
                            if k_str.casefold() in ings_folded:
                                valid_keys.append(ings_folded[k_str.casefold()])
                            else:
                                for u in unique_ingredients:
                                    if (
                                        k_str.casefold() in u.casefold()
                                        or u.casefold() in k_str.casefold()
                                    ):
                                        if u not in valid_keys:
                                            valid_keys.append(u)
                                        break
                        stage2_response.key_ingredients = (
                            valid_keys or [unique_ingredients[0]]
                        )[:3]
                        response = EnrichmentResponse.from_stages(
                            stage1_response, stage2_response
                        )
                        break
                elif str(exc) == "Stage 2 must select at least one key ingredient":
                    if not stage2_retried:
                        stage2_retried = True
                        logger.info(
                            "Stage 2 selected 0 key ingredients for recipe %s; retrying Stage 2 with %s",
                            recipe_id,
                            stage2_model,
                        )
                        continue
                    if unique_ingredients:
                        stage2_response.key_ingredients = [unique_ingredients[0]]
                        response = EnrichmentResponse.from_stages(stage1_response, stage2_response)
                        break
                raise AIResponseError(f"Invalid Stage 2 response: {exc}", usage) from exc
            break

        applied_stage1_model = (
            f"{stage1_model} (fallback {stage1_fallback_model})"
            if stage1_fallback_used
            else stage1_model
        )
        with _enrichment_write_lock:
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
        with _enrichment_write_lock:
            session.rollback()
            failed_recipe = _recipe_with_facts(session, recipe_id)
            failed_state = failed_recipe.enrichment_state
            if failed_state is not None and failed_state.status is RecipeEnrichmentStatus.RUNNING:
                failed_state.status = RecipeEnrichmentStatus.FAILED
                failed_state.last_error = str(exc)[:1000]
                failed_state.completed_at = datetime.now(UTC)
            session.commit()
        raise
    return result, usage


def aggregate_metrics(results: list[dict[str, int]]) -> dict[str, int]:
    totals = Counter()
    for result in results:
        totals.update(result)
    return dict(totals)
