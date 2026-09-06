"""Recipe enrichment eval: score candidate models against human gold annotations.

Scores candidate models across five separate dimensions:
1. Ingredient Identity: canonical ingredient resolution precision, recall, and F1.
2. Ingredient Details: accuracy of quantities, units, preparation, optionality, and alternatives.
3. Line Kinds: classification accuracy across ingredient vs heading vs note lines.
4. Controlled Facets: accuracy on cuisines, primary/secondary cooking methods, and courses.
5. Residual Keywords: zero to five Title Case UK-English keywords without forbidden overlap.

Evaluation runs against the curated gold set in ``evals/gold/enrichment/recipes.json``.
"""

import json
import logging
import time
import tomllib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.services.ai import AIProvider, AIResponseError, Usage
from app.services.ai.anthropic import AnthropicProvider
from app.services.ai.gemini import GeminiProvider
from app.services.ai.openrouter import OpenRouterProvider
from app.services.ai.stub import StubProvider
from app.services.recipe_enrichment.schema import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    EnrichmentResponse,
    Stage1Response,
)
from app.services.recipe_enrichment.service import (
    deduplicate_ingredient_names,
    validate_stage1_response,
)
from app.services.recipe_facts import accepted_cuisine_ids, facet_vocabulary
from app.text import fold
from evals.config import DEFAULT_CONFIG_PATH, EVALS_DIR, RUNS_DIR, git_sha
from evals.environment import resolve_api_key
from evals.models import CandidateModel
from evals.report import _table

logger = logging.getLogger(__name__)

ENRICHMENT_GOLD_PATH = EVALS_DIR / "gold" / "enrichment" / "recipes.json"
ENRICHMENT_LEDGER_PATH = EVALS_DIR / "enrichment.jsonl"
MAX_CONCURRENT_ENRICHMENT_REQUESTS = 6

_FRACTION_MAP = {
    "½": "0.5",
    "1/2": "0.5",
    "⅓": "0.33",
    "1/3": "0.33",
    "⅔": "0.67",
    "2/3": "0.67",
    "¼": "0.25",
    "1/4": "0.25",
    "¾": "0.75",
    "3/4": "0.75",
}

_UNIT_ALIASES = {
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tb": "tbsp",
    "tbs": "tbsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "cups": "cup",
    "gram": "g",
    "grams": "g",
    "kilogram": "kg",
    "kilograms": "kg",
    "millilitre": "ml",
    "millilitres": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "liters": "litre",
    "ounces": "oz",
    "ounce": "oz",
    "pounds": "lb",
    "pound": "lb",
    "cloves": "clove",
}


def _norm_str(val: str | None) -> str:
    if not val:
        return ""
    text = fold(val).strip()
    for frac, dec in _FRACTION_MAP.items():
        text = text.replace(frac, dec)
    return text


def _norm_unit(val: str | None) -> str:
    unit = _norm_str(val)
    return _UNIT_ALIASES.get(unit, unit)


class GoldOccurrence(BaseModel):
    canonical_name: str
    quantity: str | None = None
    unit: str | None = None
    preparation: str | None = None
    optional: bool = False
    alternative_group: int | None = None
    is_key: bool = False


class GoldLine(BaseModel):
    position: int
    text: str
    kind: str | None = None
    occurrences: list[GoldOccurrence] = []


class GoldFact(BaseModel):
    value_id: str
    is_primary: bool = False


class GoldRecipe(BaseModel):
    id: str
    slug: str
    name: str
    archetype: str
    yields: str | None = None
    description: str | None = None
    book_title: str | None = None
    book_author: str | None = None
    instructions: list[str]
    lines: list[GoldLine]
    canonical_ingredients: list[str] = []
    key_ingredients: list[str] = []
    cuisines: list[GoldFact] = []
    accepted_cuisines: list[str] = []
    methods: list[GoldFact] = []
    courses: list[GoldFact] = []
    accepted_courses: list[str] = []
    residual_keywords: list[str] = []


class EnrichmentDimensionScores(BaseModel):
    canonical_ingredients_precision: float = 0.0
    canonical_ingredients_recall: float = 0.0
    canonical_ingredients_f1: float = 0.0
    key_ingredients_precision: float = 0.0
    key_ingredients_recall: float = 0.0
    key_ingredients_f1: float = 0.0

    # Historical fields preserved for past JSONL evaluation records
    ingredient_identity_precision: float | None = None
    ingredient_identity_recall: float | None = None
    ingredient_identity_f1: float | None = None
    quantity_accuracy: float | None = None
    unit_accuracy: float | None = None
    preparation_accuracy: float | None = None
    optional_accuracy: float | None = None
    alternative_group_accuracy: float | None = None
    ingredient_details_mean: float | None = None
    line_kinds_accuracy: float | None = None

    cuisine_score: float = 0.0
    primary_method_score: float = 0.0
    methods_jaccard: float = 0.0
    course_score: float = 0.0
    facets_mean: float = 0.0

    keywords_validity: float = 0.0
    keywords_count: int = 0
    keywords_duplicates: int = 0
    keywords_overlap: int = 0

    composite: float = 0.0


class EnrichmentRecipeRecord(BaseModel):
    run_id: str
    timestamp: str
    git_sha: str | None
    recipe_id: str
    recipe_slug: str
    recipe_name: str
    archetype: str
    model_id: str
    provider: str
    model: str
    stage1_model_id: str | None = None
    stage2_model_id: str | None = None
    deterministic_enabled: bool | None = None
    prompt_version: str | None = None
    schema_version: str | None = None
    scores: EnrichmentDimensionScores
    input_tokens: int | None
    output_tokens: int | None
    candidate_tokens: int | None
    thinking_tokens: int | None
    cost_usd: float | None
    stage1_input_tokens: int | None = None
    stage1_output_tokens: int | None = None
    stage1_cost_usd: float | None = None
    stage2_input_tokens: int | None = None
    stage2_output_tokens: int | None = None
    stage2_cost_usd: float | None = None
    duration_s: float
    finish_reason: str | None = None
    error: str | None = None


def load_gold_recipes(path: Path = ENRICHMENT_GOLD_PATH) -> list[GoldRecipe]:
    data = json.loads(path.read_text())
    return [GoldRecipe.model_validate(item) for item in data]


_EVAL_PLURAL_MAP = {
    "noodles": "noodle",
    "sprouts": "sprout",
    "seeds": "seed",
    "flakes": "flake",
    "leaves": "leaf",
    "chives": "chive",
}

_EVAL_EN_GB_MAP = {
    "chile": "chilli",
    "chili": "chilli",
    "chiles": "chilli",
    "chilis": "chilli",
    "chillies": "chilli",
    "cilantro": "coriander",
    "eggplant": "aubergine",
    "eggplants": "aubergine",
    "zucchini": "courgette",
    "zucchinis": "courgette",
    "scallion": "spring onion",
    "scallions": "spring onion",
    "green onion": "spring onion",
    "green onions": "spring onion",
}


def _norm_eval_ingredient(name: str) -> str:
    folded = fold(name)
    tokens = folded.split()
    norm_tokens: list[str] = []
    for t in tokens:
        if t in _EVAL_EN_GB_MAP:
            t = _EVAL_EN_GB_MAP[t]
        if t in _EVAL_PLURAL_MAP:
            t = _EVAL_PLURAL_MAP[t]
        norm_tokens.append(t)
    return " ".join(norm_tokens)


def score_canonical_ingredients(
    gold_ingredients: list[str], response: EnrichmentResponse
) -> tuple[float, float, float]:
    gold_names = {_norm_eval_ingredient(name) for name in gold_ingredients if name}
    pred_names = {
        _norm_eval_ingredient(item.name)
        for item in response.canonical_ingredients
        if item.name
    }

    if not gold_names and not pred_names:
        return 1.0, 1.0, 1.0
    if not gold_names or not pred_names:
        return 0.0, 0.0, 0.0

    tp = len(gold_names & pred_names)
    precision = tp / len(pred_names) if pred_names else 0.0
    recall = tp / len(gold_names) if gold_names else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def score_ingredient_identity(
    gold_ingredients: list[str], response: EnrichmentResponse
) -> tuple[float, float, float]:
    return score_canonical_ingredients(gold_ingredients, response)


def score_key_ingredients(
    gold_key_ingredients: list[str], response: EnrichmentResponse
) -> tuple[float, float, float]:
    gold_names = {_norm_eval_ingredient(name) for name in gold_key_ingredients if name}
    pred_names = {
        _norm_eval_ingredient(item.name)
        for item in response.canonical_ingredients
        if item.is_key and item.name
    }

    if not gold_names and not pred_names:
        return 1.0, 1.0, 1.0
    if not gold_names or not pred_names:
        return 0.0, 0.0, 0.0

    tp = len(gold_names & pred_names)
    precision = tp / len(pred_names) if pred_names else 0.0
    recall = tp / len(gold_names) if gold_names else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def score_facets(gold: GoldRecipe, response: EnrichmentResponse) -> dict[str, float]:
    pred_cuisines = set(response.cuisines)
    accepted_cuisines = set(gold.accepted_cuisines or [item.value_id for item in gold.cuisines])
    if not accepted_cuisines and not pred_cuisines:
        cuisine_score = 1.0
    elif not pred_cuisines:
        cuisine_score = 0.0
    elif accepted_cuisines & pred_cuisines:
        cuisine_score = 1.0
    else:
        cuisine_score = 0.0

    gold_primary = next((item.value_id for item in gold.methods if item.is_primary), None)
    pred_primary = next((item.value_id for item in response.methods if item.is_primary), None)
    primary_method_score = 1.0 if gold_primary == pred_primary else 0.0

    gold_methods = {item.value_id for item in gold.methods}
    pred_methods = {item.value_id for item in response.methods}
    if not gold_methods and not pred_methods:
        methods_jaccard = 1.0
    elif not gold_methods or not pred_methods:
        methods_jaccard = 0.0
    else:
        methods_jaccard = len(gold_methods & pred_methods) / len(gold_methods | pred_methods)

    pred_courses = set(response.courses)
    accepted_courses = set(gold.accepted_courses or [item.value_id for item in gold.courses])
    if not accepted_courses and not pred_courses:
        course_score = 1.0
    elif not pred_courses:
        course_score = 0.0
    else:
        course_score = 1.0 if (pred_courses & accepted_courses) else 0.0

    facets_mean = (cuisine_score + primary_method_score + methods_jaccard + course_score) / 4.0

    return {
        "cuisine_score": cuisine_score,
        "primary_method_score": primary_method_score,
        "methods_jaccard": methods_jaccard,
        "course_score": course_score,
        "facets_mean": facets_mean,
    }


def score_residual_keywords(
    keywords: list[str], gold: GoldRecipe, response: EnrichmentResponse
) -> dict[str, Any]:
    count = len(keywords)
    count_score = 1.0 if count <= 5 else 0.0

    seen = set()
    duplicates = 0
    title_case_count = 0
    for kw in keywords:
        k_fold = fold(kw)
        if k_fold in seen:
            duplicates += 1
        seen.add(k_fold)
        if kw.istitle() or (kw and kw[0].isupper()):
            title_case_count += 1

    title_score = title_case_count / count if count else 1.0

    forbidden = {fold(c) for c in response.cuisines}
    forbidden |= {fold(m.value_id) for m in response.methods}
    forbidden |= {fold(o) for o in response.courses}
    forbidden |= {fold(item.name) for item in response.canonical_ingredients}

    overlap = sum(1 for kw in keywords if fold(kw) in forbidden)
    overlap_score = max(0.0, 1.0 - overlap * 0.2)

    validity = (count_score + title_score + (1.0 if duplicates == 0 else 0.0) + overlap_score) / 4.0

    return {
        "keywords_validity": validity,
        "keywords_count": count,
        "keywords_duplicates": duplicates,
        "keywords_overlap": overlap,
    }


def calculate_composite_score(scores: dict[str, Any]) -> float:
    weights = {
        "canonical_ingredients": 0.35,
        "key_ingredients": 0.15,
        "facets": 0.30,
        "residual_keywords": 0.20,
    }
    composite = (
        weights["canonical_ingredients"] * scores["canonical_ingredients_f1"]
        + weights["key_ingredients"] * scores["key_ingredients_f1"]
        + weights["facets"] * scores["facets_mean"]
        + weights["residual_keywords"] * scores["keywords_validity"]
    )
    return round(composite, 4)


def score_enrichment_response(
    gold: GoldRecipe, response: EnrichmentResponse
) -> EnrichmentDimensionScores:
    p_ing, r_ing, f1_ing = score_canonical_ingredients(gold.canonical_ingredients, response)
    p_key, r_key, f1_key = score_key_ingredients(gold.key_ingredients, response)
    facets = score_facets(gold, response)
    kw = score_residual_keywords(response.keywords, gold, response)

    payload = {
        "canonical_ingredients_precision": p_ing,
        "canonical_ingredients_recall": r_ing,
        "canonical_ingredients_f1": f1_ing,
        "key_ingredients_precision": p_key,
        "key_ingredients_recall": r_key,
        "key_ingredients_f1": f1_key,
        **facets,
        **kw,
    }
    composite = calculate_composite_score(payload)
    return EnrichmentDimensionScores.model_validate({"composite": composite, **payload})


def source_fingerprint_dict(source: dict) -> str:
    return sha256(
        json.dumps(source, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def gold_ingredient_vocab(recipes: list[GoldRecipe]) -> dict[str, str]:
    vocab: dict[str, str] = {}
    for r in recipes:
        for name in r.canonical_ingredients:
            if name:
                vocab[fold(name)] = name
    return vocab


def build_gold_stage1_context(gold: GoldRecipe) -> dict:
    return {
        "recipe": {
            "id": gold.id,
            "name": gold.name,
            "ingredients": [line.text for line in gold.lines],
        }
    }


def build_gold_stage2_context(
    gold: GoldRecipe, ingredients: list[str], *, include_description: bool = True
) -> dict:
    _, entries = facet_vocabulary()
    methods = [
        {"id": entry["id"], "name": entry["name"]} for entry in entries if entry["kind"] == "method"
    ]
    courses = [
        {"id": entry["id"], "name": entry["name"]} for entry in entries if entry["kind"] == "course"
    ]

    recipe_payload: dict[str, Any] = {
        "id": gold.id,
        "name": gold.name,
        "ingredients": ingredients,
        "instructions": gold.instructions,
    }
    if gold.book_title:
        recipe_payload["book_title"] = gold.book_title
    if gold.book_author:
        recipe_payload["book_author"] = gold.book_author
    if include_description and gold.description:
        recipe_payload["description"] = gold.description
    if gold.yields:
        recipe_payload["yield"] = gold.yields

    return {
        "vocabulary": {
            "cuisines": sorted(accepted_cuisine_ids()),
            "methods": methods,
            "courses": courses,
        },
        "recipe": recipe_payload,
    }


def build_gold_context(gold: GoldRecipe) -> dict:
    _, entries = facet_vocabulary()
    methods = [
        {"id": entry["id"], "name": entry["name"]} for entry in entries if entry["kind"] == "method"
    ]
    courses = [
        {"id": entry["id"], "name": entry["name"]} for entry in entries if entry["kind"] == "course"
    ]

    recipe_payload: dict[str, Any] = {
        "id": gold.id,
        "name": gold.name,
        "ingredients": [line.text for line in gold.lines],
        "instructions": gold.instructions,
    }
    if gold.book_title:
        recipe_payload["book_title"] = gold.book_title
    if gold.book_author:
        recipe_payload["book_author"] = gold.book_author
    if gold.description:
        recipe_payload["description"] = gold.description
    if gold.yields:
        recipe_payload["yield"] = gold.yields

    return {
        "vocabulary": {
            "cuisines": sorted(accepted_cuisine_ids()),
            "methods": methods,
            "courses": courses,
        },
        "recipe": recipe_payload,
    }


def validate_enrichment_response(context: dict, response: EnrichmentResponse) -> None:
    """Reject structured responses that the production application would not accept."""
    for item in response.canonical_ingredients:
        if not item.name.strip():
            raise ValueError("canonical ingredient name cannot be empty")
    if sum(item.is_key for item in response.canonical_ingredients) > 3:
        raise ValueError("response must contain at most three key ingredients")
    if response.canonical_ingredients and not any(
        item.is_key for item in response.canonical_ingredients
    ):
        raise ValueError("response must contain at least one key ingredient")

    names = [item.name for item in response.canonical_ingredients]
    folded_names = [fold(name) for name in names]
    if len(folded_names) != len(set(folded_names)):
        raise ValueError("response contains duplicate canonical ingredients")

    vocabulary = context["vocabulary"]
    allowed = {
        "cuisine": set(vocabulary["cuisines"]),
        "method": {item["id"] for item in vocabulary["methods"]},
        "course": {item["id"] for item in vocabulary["courses"]},
    }
    if (
        len(response.cuisines) != len(set(response.cuisines))
        or not set(response.cuisines) <= allowed["cuisine"]
    ):
        raise ValueError("response contains an unknown or duplicate cuisine")
    method_ids = [fact.value_id for fact in response.methods]
    if len(method_ids) != len(set(method_ids)) or not set(method_ids) <= allowed["method"]:
        raise ValueError("response contains an unknown or duplicate method")
    if (
        len(response.courses) != len(set(response.courses))
        or not set(response.courses) <= allowed["course"]
    ):
        raise ValueError("response contains an unknown or duplicate course")
    if sum(fact.is_primary for fact in response.methods) > 1:
        raise ValueError("response has multiple primary methods")
    if len(response.keywords) > 5:
        raise ValueError("response must contain at most five residual keywords")
    seen_kw = set()
    for kw in response.keywords:
        name = kw.strip()
        if not name or not (name.istitle() or (name and name[0].isupper())):
            raise ValueError(f"keyword is not Title Case: {kw!r}")
        folded_kw = fold(name)
        if folded_kw in seen_kw:
            raise ValueError("response contains duplicate residual keywords")
        seen_kw.add(folded_kw)


def instantiate_provider(candidate: CandidateModel, api_key: str) -> AIProvider:
    overrides = {"recipe_enrichment": candidate.model}
    if candidate.provider == "GEMINI":
        return GeminiProvider(api_key=api_key, model_overrides=overrides)
    if candidate.provider == "ANTHROPIC":
        return AnthropicProvider(api_key=api_key, model_overrides=overrides)
    if candidate.provider == "OPENROUTER":
        return OpenRouterProvider(api_key=api_key, model_overrides=overrides)
    if candidate.provider == "STUB":
        return StubProvider(api_key=api_key, model_overrides=overrides)
    raise ValueError(f"Unknown provider: {candidate.provider}")


def load_enrichment_config(path: Path = DEFAULT_CONFIG_PATH) -> tuple[list[CandidateModel], Path]:
    if not path.exists():
        return [], ENRICHMENT_GOLD_PATH
    data = tomllib.loads(path.read_text()).get("enrichment", {})
    models = [CandidateModel.parse(m) for m in data.get("models", [])]
    gold_rel = data.get("gold")
    gold_path = path.parent / gold_rel if gold_rel else ENRICHMENT_GOLD_PATH
    return models, gold_path


def leaderboard(records: list[EnrichmentRecipeRecord]) -> str:
    if not records:
        return "No enrichment records to report."

    by_model = defaultdict(list)

    for r in records:
        by_model[r.model_id].append(r)

    rows = []
    for model_id, items in by_model.items():
        valid_items = [item for item in items if item.error is None]
        if not valid_items:
            rows.append(
                [
                    model_id,
                    "0.000",
                    "0.0%",
                    "0.0%",
                    "0.0%",
                    "0.0%",
                    "—",
                    "—",
                    f"{len(items)} errors",
                ]
            )
            continue

        comp_mean = sum(item.scores.composite for item in valid_items) / len(valid_items)
        ing_f1 = sum(
            item.scores.canonical_ingredients_f1
            if item.scores.canonical_ingredients_f1 is not None
            else (item.scores.ingredient_identity_f1 or 0.0)
            for item in valid_items
        ) / len(valid_items)
        key_f1 = sum(
            item.scores.key_ingredients_f1
            if item.scores.key_ingredients_f1 is not None
            else 0.0
            for item in valid_items
        ) / len(valid_items)
        facets_mean = sum(item.scores.facets_mean for item in valid_items) / len(valid_items)
        kw_mean = sum(item.scores.keywords_validity for item in valid_items) / len(valid_items)

        total_cost = sum(item.cost_usd or 0.0 for item in items)
        total_dur = sum(item.duration_s for item in items)

        rows.append(
            [
                model_id,
                f"{comp_mean:.3f}",
                f"{ing_f1 * 100:.1f}%",
                f"{key_f1 * 100:.1f}%",
                f"{facets_mean * 100:.1f}%",
                f"{kw_mean * 100:.1f}%",
                f"${total_cost:.4f}",
                f"{total_dur:.1f}s",
                f"{len(valid_items)}/{len(items)}",
            ]
        )

    rows.sort(key=lambda r: float(r[1]), reverse=True)
    headers = [
        "Model",
        "Composite",
        "Ing F1",
        "Key F1",
        "Facets",
        "Keywords",
        "Cost",
        "Duration",
        "Passed",
    ]
    return "Enrichment Leaderboard\n\n" + _table(headers, rows)


def _zero_enrichment_scores() -> EnrichmentDimensionScores:
    return EnrichmentDimensionScores(
        canonical_ingredients_precision=0.0,
        canonical_ingredients_recall=0.0,
        canonical_ingredients_f1=0.0,
        key_ingredients_precision=0.0,
        key_ingredients_recall=0.0,
        key_ingredients_f1=0.0,
        cuisine_score=0.0,
        primary_method_score=0.0,
        methods_jaccard=0.0,
        course_score=0.0,
        facets_mean=0.0,
        keywords_validity=0.0,
        keywords_count=0,
        keywords_duplicates=0,
        keywords_overlap=0,
        composite=0.0,
    )


def evaluate_enrichment_recipe(
    candidate: CandidateModel,
    provider: AIProvider,
    gold: GoldRecipe,
    *,
    run_id: str,
    timestamp: str,
    sha: str | None,
    run_dir: Path,
    vocab: dict[str, str] | None = None,
    include_description: bool = True,
    stage2_candidate: CandidateModel | None = None,
    stage2_provider: AIProvider | None = None,
) -> EnrichmentRecipeRecord:
    """Evaluate one independent model and recipe pair using two-stage enrichment."""
    started = time.monotonic()
    stage2_candidate = stage2_candidate or candidate
    stage2_provider = stage2_provider or provider
    mixed_models = stage2_candidate.id != candidate.id
    model_id = f"{candidate.id} -> {stage2_candidate.id}" if mixed_models else candidate.id
    provider_id = (
        f"{candidate.provider}->{stage2_candidate.provider}" if mixed_models else candidate.provider
    )
    model_name = f"{candidate.model}->{stage2_candidate.model}" if mixed_models else candidate.model
    artefact_model = model_id.replace("/", "_").replace(":", "_").replace(" -> ", "__to__")
    usage1 = Usage()
    usage2 = Usage()

    try:
        stage1_context = build_gold_stage1_context(gold)

        if not stage1_context["recipe"]["ingredients"]:
            stage1_response = Stage1Response(i=[])
            usage1 = Usage()
        else:
            try:
                stage1_response, usage1 = provider.enrich_recipe_stage1(
                    stage1_context, candidate.model
                )
            except AIResponseError as exc:
                usage1 = exc.usage
                raise

        try:
            validate_stage1_response(stage1_context, stage1_response)
        except ValueError as exc:
            raise AIResponseError(f"Invalid Stage 1 response: {exc}", usage1) from exc

        deduped_ingredients = deduplicate_ingredient_names(stage1_response.ingredients)

        stage2_context = build_gold_stage2_context(
            gold, deduped_ingredients, include_description=include_description
        )
        try:
            stage2_response, usage2 = stage2_provider.enrich_recipe_stage2(
                stage2_context, stage2_candidate.model
            )
        except AIResponseError as exc:
            usage2 = exc.usage
            raise AIResponseError(str(exc), usage1 + usage2) from exc

        usage = usage1 + usage2
        try:
            response = EnrichmentResponse.from_stages(deduped_ingredients, stage2_response)
        except ValueError as exc:
            raise AIResponseError(f"Invalid Stage 2 response: {exc}", usage) from exc

        full_context = build_gold_context(gold)
        try:
            validate_enrichment_response(full_context, response)
        except ValueError as exc:
            artefact_path = run_dir / f"{gold.slug}_{artefact_model}.invalid.json"
            artefact_path.write_text(
                json.dumps(
                    {
                        "response": response.model_dump(),
                        "stage1": stage1_response.model_dump(),
                        "stage2": stage2_response.model_dump(),
                        "gold": gold.model_dump(),
                    },
                    indent=2,
                )
            )
            raise AIResponseError(f"Invalid recipe enrichment response: {exc}", usage) from exc
        duration = time.monotonic() - started
        scores = score_enrichment_response(gold, response)
        record = EnrichmentRecipeRecord(
            run_id=run_id,
            timestamp=timestamp,
            git_sha=sha,
            recipe_id=gold.id,
            recipe_slug=gold.slug,
            recipe_name=gold.name,
            archetype=gold.archetype,
            model_id=model_id,
            provider=provider_id,
            model=model_name,
            stage1_model_id=candidate.id,
            stage2_model_id=stage2_candidate.id,
            deterministic_enabled=False,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            scores=scores,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            candidate_tokens=usage.candidate_tokens,
            thinking_tokens=usage.thinking_tokens,
            cost_usd=float(usage.cost_usd) if usage.cost_usd is not None else None,
            stage1_input_tokens=usage1.input_tokens,
            stage1_output_tokens=usage1.output_tokens,
            stage1_cost_usd=(float(usage1.cost_usd) if usage1.cost_usd is not None else None),
            stage2_input_tokens=usage2.input_tokens,
            stage2_output_tokens=usage2.output_tokens,
            stage2_cost_usd=(float(usage2.cost_usd) if usage2.cost_usd is not None else None),
            duration_s=round(duration, 3),
            finish_reason=usage.finish_reason,
        )

        artefact_path = run_dir / f"{gold.slug}_{artefact_model}.json"
        artefact_data = {
            "record": record.model_dump(),
            "response": response.model_dump(),
            "stage1": stage1_response.model_dump(),
            "stage2": stage2_response.model_dump(),
            "gold": gold.model_dump(),
            "include_description": include_description,
            "deterministic_enabled": False,
        }
        artefact_path.write_text(json.dumps(artefact_data, indent=2))
        return record

    except AIResponseError as exc:
        duration = time.monotonic() - started
        logger.error(f"{gold.slug} / {model_id} failed: {exc}")
        usage = usage1 + usage2
        return EnrichmentRecipeRecord(
            run_id=run_id,
            timestamp=timestamp,
            git_sha=sha,
            recipe_id=gold.id,
            recipe_slug=gold.slug,
            recipe_name=gold.name,
            archetype=gold.archetype,
            model_id=model_id,
            provider=provider_id,
            model=model_name,
            stage1_model_id=candidate.id,
            stage2_model_id=stage2_candidate.id,
            deterministic_enabled=False,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            scores=_zero_enrichment_scores(),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            candidate_tokens=usage.candidate_tokens,
            thinking_tokens=usage.thinking_tokens,
            cost_usd=float(usage.cost_usd) if usage.cost_usd is not None else None,
            stage1_input_tokens=usage1.input_tokens,
            stage1_output_tokens=usage1.output_tokens,
            stage1_cost_usd=(float(usage1.cost_usd) if usage1.cost_usd is not None else None),
            stage2_input_tokens=usage2.input_tokens,
            stage2_output_tokens=usage2.output_tokens,
            stage2_cost_usd=(float(usage2.cost_usd) if usage2.cost_usd is not None else None),
            duration_s=round(duration, 3),
            finish_reason=usage.finish_reason,
            error=str(exc)[:500],
        )

    except Exception as exc:
        duration = time.monotonic() - started
        logger.error(f"{gold.slug} / {model_id} failed: {exc}")
        return EnrichmentRecipeRecord(
            run_id=run_id,
            timestamp=timestamp,
            git_sha=sha,
            recipe_id=gold.id,
            recipe_slug=gold.slug,
            recipe_name=gold.name,
            archetype=gold.archetype,
            model_id=model_id,
            provider=provider_id,
            model=model_name,
            stage1_model_id=candidate.id,
            stage2_model_id=stage2_candidate.id,
            deterministic_enabled=False,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            scores=_zero_enrichment_scores(),
            input_tokens=None,
            output_tokens=None,
            candidate_tokens=None,
            thinking_tokens=None,
            cost_usd=None,
            duration_s=round(duration, 3),
            error=str(exc)[:500],
        )


def run_enrichment_eval(
    config_path: Path = DEFAULT_CONFIG_PATH,
    model_ids: list[str] | None = None,
    recipe_slugs: list[str] | None = None,
    include_description: bool = True,
    stage1_model_id: str | None = None,
    stage2_model_id: str | None = None,
) -> list[EnrichmentRecipeRecord]:
    if bool(stage1_model_id) != bool(stage2_model_id):
        raise ValueError("stage-1-model and stage-2-model must be supplied together")
    if model_ids and stage1_model_id:
        raise ValueError("model cannot be combined with stage-1-model and stage-2-model")
    cfg_models, gold_path = load_enrichment_config(config_path)
    models = cfg_models
    if model_ids:
        models = [
            CandidateModel.parse(m) if ":" in m else next(c for c in cfg_models if c.id == m)
            for m in model_ids
        ]
    if not models:
        models = [
            CandidateModel.parse("GEMINI:gemini-2.5-flash"),
            CandidateModel.parse("GEMINI:gemini-2.5-flash-lite"),
        ]

    gold_recipes = load_gold_recipes(gold_path)
    if recipe_slugs:
        gold_recipes = [r for r in gold_recipes if r.slug in recipe_slugs or r.id in recipe_slugs]

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    timestamp = datetime.now(UTC).isoformat()
    sha = git_sha()
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    providers: list[tuple[CandidateModel, AIProvider, CandidateModel, AIProvider]] = []

    if stage1_model_id and stage2_model_id:
        stage1_candidate = CandidateModel.parse(stage1_model_id)
        stage2_candidate = CandidateModel.parse(stage2_model_id)
        stage1_provider = instantiate_provider(
            stage1_candidate, resolve_api_key(stage1_candidate.provider)
        )
        stage2_provider = instantiate_provider(
            stage2_candidate, resolve_api_key(stage2_candidate.provider)
        )
        providers.append((stage1_candidate, stage1_provider, stage2_candidate, stage2_provider))

    for candidate in models if not stage1_model_id else []:
        try:
            key = resolve_api_key(candidate.provider)
        except RuntimeError as exc:
            logger.warning(f"Skipping {candidate.id}: {exc}")
            continue

        provider = instantiate_provider(candidate, key)
        providers.append((candidate, provider, candidate, provider))

    vocab = gold_ingredient_vocab(gold_recipes)

    evaluations = [
        (stage1_candidate, stage1_provider, stage2_candidate, stage2_provider, gold)
        for gold in gold_recipes
        for stage1_candidate, stage1_provider, stage2_candidate, stage2_provider in providers
    ]

    records: list[EnrichmentRecipeRecord] = []
    if not evaluations:
        logger.warning("No enrichment evaluations to run.")
        return records

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_ENRICHMENT_REQUESTS) as executor:
        futures = {
            executor.submit(
                evaluate_enrichment_recipe,
                candidate,
                provider,
                gold,
                run_id=run_id,
                timestamp=timestamp,
                sha=sha,
                run_dir=run_dir,
                vocab=vocab,
                include_description=include_description,
                stage2_candidate=stage2_candidate,
                stage2_provider=stage2_provider,
            ): (f"{candidate.id} -> {stage2_candidate.id}", gold.slug)
            for candidate, provider, stage2_candidate, stage2_provider, gold in evaluations
        }
        for future in as_completed(futures):
            record = future.result()
            records.append(record)
            status_str = (
                f"score={record.scores.composite:.3f}"
                if record.error is None
                else f"ERROR: {record.error[:40]}"
            )
            print(
                f"  {record.recipe_slug:35s} {record.model_id:30s} {status_str} ({record.duration_s:.1f}s)"
            )

    # Append to ledger
    with open(ENRICHMENT_LEDGER_PATH, "a") as f:
        for r in records:
            f.write(r.model_dump_json() + "\n")

    return records
