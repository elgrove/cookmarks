"""The deliberately bounded, normal-API recipe enrichment pilot."""

import random
import re
import uuid
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models.recipe import Recipe
from app.models.task_run import TaskRun
from app.services.ai import AIResponseError, Usage
from app.services.recipe_enrichment.service import enrich_recipe
from app.tasks.celery_app import celery_app
from app.tasks.runs import complete_run, fail_run, start_run

PILOT_SAMPLE_SIZE = 100
PILOT_STRATUM_SIZE = 25
PILOT_SEED = 172
_COMPLEX_LINE = re.compile(r"(:$|\bor\b|/|\+|,)", re.IGNORECASE)
_COMMON_FACT = re.compile(
    r"\b(bake|boil|braise|fry|grill|roast|simmer|steam|italian|indian|japanese|mexican)\b",
    re.IGNORECASE,
)


def _recipe_rows(session) -> list[Recipe]:
    return list(
        session.scalars(
            select(Recipe).options(selectinload(Recipe.ingredients_verbatim)).order_by(Recipe.id)
        )
    )


def _take(candidates: list[Recipe], chosen: list[Recipe], count: int) -> list[Recipe]:
    used = {recipe.id for recipe in chosen}
    picked = [recipe for recipe in candidates if recipe.id not in used][:count]
    chosen.extend(picked)
    return picked


def choose_pilot_sample(session, seed: int = PILOT_SEED, size: int = PILOT_SAMPLE_SIZE) -> dict:
    """A recorded, deterministic stratified sample. Small libraries simply use all rows."""
    recipes = _recipe_rows(session)
    chosen: list[Recipe] = []
    complex_recipes = [
        recipe
        for recipe in recipes
        if any(_COMPLEX_LINE.search(line.text) for line in recipe.ingredients_verbatim)
    ]
    common_fact_recipes = [
        recipe
        for recipe in recipes
        if _COMMON_FACT.search(
            " ".join([recipe.name, recipe.description or "", *recipe.instructions])
        )
    ]
    sparse_recipes = [
        recipe
        for recipe in recipes
        if len(recipe.ingredients_verbatim) <= 1
        or not recipe.description
        or len(recipe.instructions) <= 1
    ]
    strata = {
        "complex": _take(complex_recipes, chosen, PILOT_STRATUM_SIZE),
        "common_facts": _take(common_fact_recipes, chosen, PILOT_STRATUM_SIZE),
        "sparse": _take(sparse_recipes, chosen, PILOT_STRATUM_SIZE),
    }
    # Overlapping strata are deduplicated above; each is then topped up from the
    # reproducibly ordered library, retaining a 25-item review cohort where possible.
    for items in strata.values():
        items.extend(_take(recipes, chosen, PILOT_STRATUM_SIZE - len(items)))
    remaining = [recipe for recipe in recipes if recipe.id not in {item.id for item in chosen}]
    random.Random(seed).shuffle(remaining)
    strata["random"] = _take(remaining, chosen, PILOT_STRATUM_SIZE)
    strata["random"].extend(_take(recipes, chosen, PILOT_STRATUM_SIZE - len(strata["random"])))
    # Fill every stratum's shortfall deterministically without duplicates, then cap.
    _take(
        [recipe for recipe in recipes if recipe.id not in {item.id for item in chosen}],
        chosen,
        size - len(chosen),
    )
    return {
        "seed": seed,
        "recipe_ids": [str(recipe.id) for recipe in chosen[:size]],
        "strata": {name: [str(recipe.id) for recipe in items] for name, items in strata.items()},
    }


def enqueue_recipe_enrichment_pilot(run_id: str) -> None:
    recipe_enrichment_pilot_task.delay(run_id)


def run_recipe_enrichment_pilot(run_id: str) -> dict:
    start_run(run_id)
    outcomes: list[dict] = []
    usage = Usage()
    try:
        with SessionLocal() as session:
            run = session.get(TaskRun, uuid.UUID(run_id))
            if run is None:
                raise ValueError("recipe enrichment pilot run not found")
            ids = [uuid.UUID(value) for value in run.detail["recipe_ids"]]
            recipes = {
                recipe.id: recipe
                for recipe in session.scalars(select(Recipe).where(Recipe.id.in_(ids)))
            }
            for recipe_id in ids:
                recipe = recipes.get(recipe_id)
                if recipe is None:
                    outcomes.append(
                        {"recipe_id": str(recipe_id), "status": "failed", "error": "missing"}
                    )
                    continue
                started = datetime.now(UTC)
                try:
                    metrics, call_usage = enrich_recipe(session, recipe_id, task_run_id=run.id)
                    usage += call_usage
                    session.refresh(recipe)
                    status = "skipped" if metrics.get("skipped") else "complete"
                    outcomes.append(
                        {
                            "recipe_id": str(recipe_id),
                            "status": status,
                            "elapsed_seconds": round(
                                (datetime.now(UTC) - started).total_seconds(), 3
                            ),
                            "keywords": [keyword.name for keyword in recipe.keywords],
                            "line_kinds": [
                                line.kind.value if line.kind else None
                                for line in recipe.ingredients_verbatim
                            ],
                            "cuisines": [fact.cuisine_id for fact in recipe.cuisines],
                            "methods": [
                                fact.facet_value.value_id
                                for fact in recipe.facets
                                if fact.facet_value.kind.value == "method"
                            ],
                            "courses": [
                                fact.facet_value.value_id
                                for fact in recipe.facets
                                if fact.facet_value.kind.value == "course"
                            ],
                            **metrics,
                        }
                    )
                except Exception as exc:
                    if isinstance(exc, AIResponseError):
                        usage += exc.usage
                    outcomes.append(
                        {
                            "recipe_id": str(recipe_id),
                            "status": "stale" if "stale" in str(exc).lower() else "failed",
                            "error": str(exc)[:500],
                        }
                    )
        statuses = Counter(item["status"] for item in outcomes)
        line_counts = Counter()
        fact_counts = {"cuisines": Counter(), "methods": Counter(), "courses": Counter()}
        recipes_with_headings = 0
        keyword_validation_failures = 0
        for item in outcomes:
            for key in (
                "ai_parsed_lines",
                "stage1_fallback_used",
                "headings",
                "ingredients_created",
                "existing_ingredients",
                "aliases_created",
            ):
                line_counts[key] += int(item.get(key, 0))
            recipes_with_headings += int(bool(item.get("headings")))
            for key, values in fact_counts.items():
                values.update(item.get(key, []))
            keyword_validation_failures += int("keyword" in item.get("error", "").lower())
        detail = {
            "attempted": len(outcomes),
            "complete": statuses["complete"],
            "skipped": statuses["skipped"],
            "failed": statuses["failed"],
            "stale_response": statuses["stale"],
            "outcomes": outcomes,
            "recipes_with_headings": recipes_with_headings,
            "recipes_with_headings_percent": round(recipes_with_headings / len(outcomes) * 100, 1)
            if outcomes
            else 0,
            "keyword_validation_failures": keyword_validation_failures,
            "cuisine_frequency": dict(fact_counts["cuisines"]),
            "method_frequency": dict(fact_counts["methods"]),
            "course_frequency": dict(fact_counts["courses"]),
            "primary_method_coverage": sum(
                bool(item.get("methods")) for item in outcomes if item["status"] == "complete"
            ),
            "candidate_tokens": usage.candidate_tokens,
            "thinking_tokens": usage.thinking_tokens,
            **dict(line_counts),
        }
        complete_run(run_id, detail, usage)
        return detail
    except Exception as exc:
        fail_run(run_id, exc)
        raise


@celery_app.task(name="recipe_enrichment_pilot")
def recipe_enrichment_pilot_task(run_id: str) -> dict:
    return run_recipe_enrichment_pilot(run_id)
