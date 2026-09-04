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
    IngredientLineKind,
    IngredientParseMethod,
    IngredientResolutionMethod,
    RecipeEnrichmentStatus,
    RecipeFacetKind,
    RecipeFactSource,
)
from app.models.ingredient import Ingredient, IngredientAlias, IngredientLine, IngredientOccurrence
from app.models.recipe import Recipe
from app.models.recipe_fact import RecipeCuisine, RecipeFacet, RecipeFacetValue
from app.services.ai import AIProvider, ModelRole, Usage, get_ai_provider
from app.services.embeddings import embed_recipes
from app.services.keywords import get_or_create_keyword
from app.services.recipe_enrichment.parser import DeterministicProposal, parse_line
from app.services.recipe_enrichment.schema import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    TAXONOMY_VERSION,
    EnrichmentResponse,
)
from app.services.recipe_facts import (
    accepted_cuisine_ids,
    add_ingredient_alias,
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
        )
    )
    if recipe is None:
        raise ValueError(f"Recipe {recipe_id} not found")
    return recipe


def _ingredient_vocab(session: Session) -> tuple[dict[str, Ingredient], dict[str, IngredientAlias]]:
    ingredients = {str(item.id): item for item in session.scalars(select(Ingredient))}
    aliases = {str(item.id): item for item in session.scalars(select(IngredientAlias))}
    return ingredients, aliases


def _resolved_proposal(
    proposal: DeterministicProposal,
    canonical: dict[str, Ingredient],
    aliases: dict[str, IngredientAlias],
) -> bool:
    names = {item.name_folded for item in canonical.values()} | {
        item.name_folded for item in aliases.values()
    }
    return all(fold(occurrence.name) in names for occurrence in proposal.occurrences)


def build_context(
    session: Session, recipe: Recipe
) -> tuple[dict, dict[str, DeterministicProposal]]:
    """Build the provider input; stable vocabularies deliberately precede recipe data."""
    upsert_facet_vocabulary(session)
    session.flush()
    canonical, aliases = _ingredient_vocab(session)
    proposals = {
        str(line.id): proposal
        for line in recipe.ingredients_verbatim
        if line.kind is None
        if (proposal := parse_line(str(line.id), line.text)) is not None
        and _resolved_proposal(proposal, canonical, aliases)
    }
    facets = list(session.scalars(select(RecipeFacetValue)))
    state = recipe.enrichment_state
    if state is None:
        raise EnrichmentValidationError("recipe has no enrichment state")
    source = ensure_source_fingerprint(recipe)
    return (
        {
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
                "source_fingerprint": source,
                "name": recipe.name,
                "description": recipe.description,
                "yield": recipe.yields,
                "instructions": recipe.instructions,
                "lines": [
                    {"id": str(line.id), "text": line.text} for line in recipe.ingredients_verbatim
                ],
                "deterministic_proposals": [
                    {
                        "line_id": proposal.line_id,
                        "occurrences": [item.__dict__ for item in proposal.occurrences],
                    }
                    for proposal in proposals.values()
                ],
                "ai_parse_line_ids": [
                    str(line.id)
                    for line in recipe.ingredients_verbatim
                    if str(line.id) not in proposals
                ],
            },
        },
        proposals,
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
    proposals: dict[str, DeterministicProposal],
) -> None:
    state = recipe.enrichment_state
    assert state is not None
    if response.recipe_id != str(recipe.id):
        raise EnrichmentValidationError("response recipe ID does not match")
    if response.source_fingerprint != state.source_fingerprint:
        raise EnrichmentValidationError("response source fingerprint is stale")
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
    ai_line_ids = set(lines) - set(proposals)
    if (set(parsed) | set(non_ingredient)) & ai_line_ids != ai_line_ids:
        raise EnrichmentValidationError("response must decide every AI-parsed line")
    if any(not decision.occurrences for decision in response.parsed_lines):
        raise EnrichmentValidationError("parsed ingredient line has no occurrence")

    canonical, aliases = _ingredient_vocab(session)
    proposed = [occ.canonical_name for line in response.parsed_lines for occ in line.occurrences]
    proposed_folded = [fold(name) for name in proposed]

    cuisine_ids = [fact.value_id for fact in response.cuisines]
    if len(cuisine_ids) != len(set(cuisine_ids)) or not set(cuisine_ids) <= accepted_cuisine_ids():
        raise EnrichmentValidationError("response contains unknown or duplicate cuisine")
    values = {
        (item.kind, item.value_id): item for item in session.scalars(select(RecipeFacetValue))
    }
    for kind, facts in (
        (RecipeFacetKind.METHOD, response.methods),
        (RecipeFacetKind.COURSE, response.courses),
    ):
        ids = [fact.value_id for fact in facts]
        if len(ids) != len(set(ids)) or any((kind, value_id) not in values for value_id in ids):
            raise EnrichmentValidationError(f"response contains unknown or duplicate {kind.value}")
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
        fold(values[(RecipeFacetKind.COURSE, fact.value_id)].name) for fact in response.courses
    }
    forbidden |= {item.name_folded for item in canonical.values()} | {
        item.name_folded for item in aliases.values()
    }
    forbidden |= set(proposed_folded)
    if set(folded_keywords) & forbidden:
        raise EnrichmentValidationError(
            "residual keyword duplicates a structured fact or ingredient"
        )


def _resolve_existing(session: Session, name: str) -> tuple[Ingredient, IngredientResolutionMethod]:
    folded = fold(name)
    ingredient = session.scalar(select(Ingredient).where(Ingredient.name_folded == folded))
    if ingredient:
        return ingredient, IngredientResolutionMethod.CANONICAL_NAME
    alias = session.scalar(select(IngredientAlias).where(IngredientAlias.name_folded == folded))
    if alias:
        return alias.ingredient, IngredientResolutionMethod.ALIAS
    raise EnrichmentValidationError(f"deterministic ingredient cannot resolve: {name}")


def _apply_response(
    session: Session,
    recipe: Recipe,
    response: EnrichmentResponse,
    proposals: dict[str, DeterministicProposal],
    *,
    provider: AIProvider,
    model: str,
    task_run_id: uuid.UUID | None,
) -> dict[str, int]:
    _validate_response(session, recipe, response, proposals)
    state = recipe.enrichment_state
    assert state is not None
    created: dict[str, Ingredient] = {}
    canonical_by_name = {item.name_folded: item for item in session.scalars(select(Ingredient))}
    aliases_by_name = {
        item.name_folded: item for item in session.scalars(select(IngredientAlias))
    }
    aliases_created = 0
    existing_ingredients = 0
    occurrences_created = 0
    deterministic_accepted = 0
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
        elif line_id in parsed_lines:
            decision = parsed_lines[line_id]
            line.kind = IngredientLineKind.INGREDIENT
            ai_lines += 1
            parsed = [(item, IngredientParseMethod.AI, item) for item in decision.occurrences]
        else:
            line.kind = IngredientLineKind.INGREDIENT
            assert line_id in proposals
            deterministic_accepted += 1
            parsed = [
                (item, IngredientParseMethod.DETERMINISTIC, None)
                for item in proposals[line_id].occurrences
            ]
        for position, (raw, parse_method, decision_occurrence) in enumerate(parsed):
            if parse_method is IngredientParseMethod.DETERMINISTIC:
                assert isinstance(raw, type(proposals[line_id].occurrences[0]))
                ingredient, resolution = _resolve_existing(session, raw.name)
                existing_ingredients += 1
                quantity, unit, preparation = raw.quantity, raw.unit, raw.preparation
                optional = False
                alternative_group = None
                is_key = False
            else:
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
                source_name = decision_occurrence.source_name
                if source_name and fold(source_name) != ingredient.name_folded:
                    existing_alias = session.scalar(
                        select(IngredientAlias).where(
                            IngredientAlias.name_folded == fold(source_name)
                        )
                    )
                    if existing_alias is None:
                        add_ingredient_alias(session, ingredient, source_name)
                        aliases_created += 1
                    elif existing_alias.ingredient_id != ingredient.id:
                        raise EnrichmentValidationError(
                            "ingredient alias collides with another ingredient"
                        )
                quantity = decision_occurrence.quantity
                unit = decision_occurrence.unit
                preparation = decision_occurrence.preparation
                optional = decision_occurrence.optional
                alternative_group = decision_occurrence.alternative_group
                is_key = decision_occurrence.is_key
            session.add(
                IngredientOccurrence(
                    line_id=line.id,
                    ingredient_id=ingredient.id,
                    position=position,
                    quantity=quantity,
                    unit=unit,
                    preparation=preparation,
                    optional=optional,
                    alternative_group=alternative_group,
                    is_key=is_key,
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
                source=RecipeFactSource(fact.source),
                evidence=fact.evidence,
            )
        )
    for fact in response.courses:
        recipe.facets.append(
            RecipeFacet(
                facet_value_id=facet_values[(RecipeFacetKind.COURSE, fact.value_id)].id,
                is_primary=False,
                source=RecipeFactSource(fact.source),
                evidence=fact.evidence,
            )
        )
    recipe.cuisines = [
        RecipeCuisine(
            cuisine_id=fact.value_id, source=RecipeFactSource(fact.source), evidence=fact.evidence
        )
        for fact in response.cuisines
    ]
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
        "deterministic_accepted": deterministic_accepted,
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
    proposals: dict[str, DeterministicProposal],
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
                proposals,
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


def enrich_recipe(
    session: Session,
    recipe_id: uuid.UUID,
    *,
    provider: AIProvider | None = None,
    task_run_id: uuid.UUID | None = None,
) -> tuple[dict[str, int], Usage]:
    """Call the configured provider once then atomically persist the valid response."""
    recipe = _recipe_with_facts(session, recipe_id)
    state = recipe.enrichment_state
    if state is not None and state.status is RecipeEnrichmentStatus.COMPLETE:
        return {"skipped": 1}, Usage()
    provider = provider or get_ai_provider(session)
    if provider is None:
        raise RuntimeError("No usable AI provider is configured")
    if state is None:
        raise EnrichmentValidationError("recipe has no enrichment state")
    ensure_source_fingerprint(recipe)
    state.status = RecipeEnrichmentStatus.RUNNING
    state.started_at = datetime.now(UTC)
    session.commit()
    context, proposals = build_context(session, _recipe_with_facts(session, recipe_id))
    model = provider.model_for(ModelRole.RECIPE_ENRICHMENT)
    try:
        response, usage = provider.enrich_recipe(context, model)
        result = apply_enrichment(
            session,
            recipe_id,
            response,
            proposals,
            provider=provider,
            model=model,
            task_run_id=task_run_id,
        )
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
        embed_recipes(session, [_recipe_with_facts(session, recipe_id)], provider)
        session.commit()
    except Exception:
        logger.exception("Embedding refresh failed after enrichment for %s", recipe_id)
    return result, usage


def aggregate_metrics(results: list[dict[str, int]]) -> dict[str, int]:
    totals = Counter()
    for result in results:
        totals.update(result)
    return dict(totals)
