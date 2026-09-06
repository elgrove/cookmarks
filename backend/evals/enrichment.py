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
import uuid
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
from app.services.recipe_enrichment.parser import DeterministicProposal, parse_line
from app.services.recipe_enrichment.schema import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    EnrichmentResponse,
    LineDecision,
    OccurrenceDecision,
    Stage1Response,
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
    kind: str
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
    cuisines: list[GoldFact] = []
    accepted_cuisines: list[str] = []
    methods: list[GoldFact] = []
    courses: list[GoldFact] = []
    accepted_courses: list[str] = []
    residual_keywords: list[str] = []


class EnrichmentDimensionScores(BaseModel):
    ingredient_identity_precision: float
    ingredient_identity_recall: float
    ingredient_identity_f1: float

    quantity_accuracy: float
    unit_accuracy: float
    preparation_accuracy: float
    optional_accuracy: float
    alternative_group_accuracy: float
    ingredient_details_mean: float

    line_kinds_accuracy: float

    cuisine_score: float
    primary_method_score: float
    methods_jaccard: float
    course_score: float
    facets_mean: float

    keywords_validity: float
    keywords_count: int
    keywords_duplicates: int
    keywords_overlap: int

    composite: float


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


def score_ingredient_identity(
    gold_lines: list[GoldLine], response: EnrichmentResponse
) -> tuple[float, float, float]:
    gold_names = {
        _norm_eval_ingredient(occ.canonical_name)
        for line in gold_lines
        for occ in line.occurrences
        if occ.canonical_name
    }
    pred_names = {
        _norm_eval_ingredient(occ.canonical_name)
        for line in response.parsed_lines
        for occ in line.occurrences
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


def score_ingredient_details(
    gold_lines: list[GoldLine], response: EnrichmentResponse
) -> dict[str, float]:
    parsed_by_line = {line.line_id: line for line in response.parsed_lines}

    qty_matches: list[float] = []
    unit_matches: list[float] = []
    prep_matches: list[float] = []
    opt_matches: list[float] = []
    alt_matches: list[float] = []

    for gold_line in gold_lines:
        line_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{gold_line.position}:{gold_line.text}"))
        pred_line = parsed_by_line.get(line_id)
        if not pred_line or not gold_line.occurrences:
            if not gold_line.occurrences and (not pred_line or not pred_line.occurrences):
                continue
            qty_matches.append(0.0)
            unit_matches.append(0.0)
            prep_matches.append(0.0)
            opt_matches.append(0.0)
            alt_matches.append(0.0)
            continue

        gold_occs = gold_line.occurrences
        pred_occs = pred_line.occurrences

        for i, g_occ in enumerate(gold_occs):
            if i < len(pred_occs):
                p_occ = pred_occs[i]
                g_qty = _norm_str(g_occ.quantity)
                p_qty = _norm_str(p_occ.quantity)
                qty_matches.append(
                    1.0 if g_qty == p_qty or (g_qty in p_qty) or (p_qty in g_qty) else 0.0
                )

                g_u = _norm_unit(g_occ.unit)
                p_u = _norm_unit(p_occ.unit)
                unit_matches.append(1.0 if g_u == p_u else 0.0)

                g_p = _norm_str(g_occ.preparation)
                p_p = _norm_str(p_occ.preparation)
                if not g_p and not p_p:
                    prep_matches.append(1.0)
                elif not g_p or not p_p:
                    prep_matches.append(0.0)
                else:
                    prep_matches.append(1.0 if (g_p in p_p or p_p in g_p) else 0.0)

                opt_matches.append(1.0 if g_occ.optional == p_occ.optional else 0.0)

                g_has_alt = g_occ.alternative_group is not None
                p_has_alt = p_occ.alternative_group is not None
                alt_matches.append(1.0 if g_has_alt == p_has_alt else 0.0)
            else:
                qty_matches.append(0.0)
                unit_matches.append(0.0)
                prep_matches.append(0.0)
                opt_matches.append(0.0)
                alt_matches.append(0.0)

    qty_acc = sum(qty_matches) / len(qty_matches) if qty_matches else 1.0
    unit_acc = sum(unit_matches) / len(unit_matches) if unit_matches else 1.0
    prep_acc = sum(prep_matches) / len(prep_matches) if prep_matches else 1.0
    opt_acc = sum(opt_matches) / len(opt_matches) if opt_matches else 1.0
    alt_acc = sum(alt_matches) / len(alt_matches) if alt_matches else 1.0
    details_mean = (qty_acc + unit_acc + prep_acc + opt_acc + alt_acc) / 5.0

    return {
        "quantity_accuracy": qty_acc,
        "unit_accuracy": unit_acc,
        "preparation_accuracy": prep_acc,
        "optional_accuracy": opt_acc,
        "alternative_group_accuracy": alt_acc,
        "ingredient_details_mean": details_mean,
    }


def score_line_kinds(gold_lines: list[GoldLine], response: EnrichmentResponse) -> float:
    non_ing_lines = {item.line_id: item.kind for item in response.non_ingredient_lines}

    matches = 0
    total = len(gold_lines)

    for gold_line in gold_lines:
        line_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{gold_line.position}:{gold_line.text}"))
        pred_kind = non_ing_lines.get(line_id, "ingredient")
        if pred_kind == gold_line.kind:
            matches += 1

    return matches / total if total else 1.0


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
    forbidden |= {
        fold(occ.canonical_name) for line in response.parsed_lines for occ in line.occurrences
    }

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
        "ingredient_identity": 0.30,
        "ingredient_details": 0.20,
        "line_kinds": 0.15,
        "facets": 0.20,
        "residual_keywords": 0.15,
    }
    composite = (
        weights["ingredient_identity"] * scores["ingredient_identity_f1"]
        + weights["ingredient_details"] * scores["ingredient_details_mean"]
        + weights["line_kinds"] * scores["line_kinds_accuracy"]
        + weights["facets"] * scores["facets_mean"]
        + weights["residual_keywords"] * scores["keywords_validity"]
    )
    return round(composite, 4)


def score_enrichment_response(
    gold: GoldRecipe, response: EnrichmentResponse
) -> EnrichmentDimensionScores:
    p, r, f1 = score_ingredient_identity(gold.lines, response)
    details = score_ingredient_details(gold.lines, response)
    line_kinds_acc = score_line_kinds(gold.lines, response)
    facets = score_facets(gold, response)
    kw = score_residual_keywords(response.keywords, gold, response)

    payload = {
        "ingredient_identity_precision": p,
        "ingredient_identity_recall": r,
        "ingredient_identity_f1": f1,
        "line_kinds_accuracy": line_kinds_acc,
        **details,
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
        for line in r.lines:
            for occ in line.occurrences:
                if occ.canonical_name:
                    vocab[fold(occ.canonical_name)] = occ.canonical_name
    return vocab


def build_gold_proposals(
    gold: GoldRecipe, vocab: dict[str, str]
) -> dict[str, DeterministicProposal]:
    proposals: dict[str, DeterministicProposal] = {}
    for line in gold.lines:
        line_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{line.position}:{line.text}"))
        p = parse_line(line_id, line.text)
        if p and all(fold(occ.name) in vocab for occ in p.occurrences):
            proposals[line_id] = p
    return proposals


def proposals_to_line_decisions(
    proposals: dict[str, DeterministicProposal], vocab: dict[str, str]
) -> list[LineDecision]:
    lines = []
    for line_id, proposal in proposals.items():
        occurrences = [
            OccurrenceDecision(
                n=vocab.get(fold(occ.name), occ.name.title()),
                q=occ.quantity,
                u=occ.unit,
                p=occ.preparation,
                x=False,
                a=None,
                k=False,
            )
            for occ in proposal.occurrences
        ]
        lines.append(LineDecision(l=line_id, o=occurrences))
    return lines


def build_gold_stage1_context(
    gold: GoldRecipe, proposals: dict[str, DeterministicProposal] | None = None
) -> dict:
    props = proposals or {}
    ai_parse_line_ids = [
        str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{line.position}:{line.text}"))
        for line in gold.lines
        if str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{line.position}:{line.text}")) not in props
    ]
    lines_payload = [
        {
            "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{line.position}:{line.text}")),
            "text": line.text,
        }
        for line in gold.lines
        if str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{line.position}:{line.text}")) in ai_parse_line_ids
    ]

    return {
        "recipe": {
            "id": gold.id,
            "name": gold.name,
            "instructions": gold.instructions,
            "lines": lines_payload,
            "ai_parse_line_ids": ai_parse_line_ids,
        }
    }


def build_gold_stage2_context(
    gold: GoldRecipe, ingredient_names: list[str], *, include_description: bool = True
) -> dict:
    _, entries = facet_vocabulary()
    methods = [
        {"id": entry["id"], "name": entry["name"]} for entry in entries if entry["kind"] == "method"
    ]
    courses = [
        {"id": entry["id"], "name": entry["name"]} for entry in entries if entry["kind"] == "course"
    ]

    recipe_payload = {
        "id": gold.id,
        "name": gold.name,
        "instructions": gold.instructions,
        "ingredients": ingredient_names,
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

    lines_payload = []
    ai_parse_line_ids = []
    for line in gold.lines:
        line_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{line.position}:{line.text}"))
        lines_payload.append({"id": line_id, "text": line.text})
        ai_parse_line_ids.append(line_id)

    recipe_payload = {
        "id": gold.id,
        "name": gold.name,
        "instructions": gold.instructions,
        "lines": lines_payload,
        "ai_parse_line_ids": ai_parse_line_ids,
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
    recipe = context["recipe"]
    expected_line_ids = set(recipe["ai_parse_line_ids"])
    parsed_ids = [line.line_id for line in response.parsed_lines]
    non_ingredient_ids = [line.line_id for line in response.non_ingredient_lines]
    decision_ids = set(parsed_ids) | set(non_ingredient_ids)
    if len(parsed_ids) != len(set(parsed_ids)) or len(non_ingredient_ids) != len(
        set(non_ingredient_ids)
    ):
        raise ValueError("response contains duplicate line decisions")
    if set(parsed_ids) & set(non_ingredient_ids) or decision_ids != expected_line_ids:
        raise ValueError("response must make one decision for every requested line")
    if any(not line.occurrences for line in response.parsed_lines):
        raise ValueError("response has an ingredient line without occurrences")

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
                    "0.0%",
                    "—",
                    "—",
                    f"{len(items)} errors",
                ]
            )
            continue

        comp_mean = sum(item.scores.composite for item in valid_items) / len(valid_items)
        f1_mean = sum(item.scores.ingredient_identity_f1 for item in valid_items) / len(valid_items)
        details_mean = sum(item.scores.ingredient_details_mean for item in valid_items) / len(
            valid_items
        )
        kinds_mean = sum(item.scores.line_kinds_accuracy for item in valid_items) / len(valid_items)
        facets_mean = sum(item.scores.facets_mean for item in valid_items) / len(valid_items)
        kw_mean = sum(item.scores.keywords_validity for item in valid_items) / len(valid_items)

        total_cost = sum(item.cost_usd or 0.0 for item in items)
        total_dur = sum(item.duration_s for item in items)

        rows.append(
            [
                model_id,
                f"{comp_mean:.3f}",
                f"{f1_mean * 100:.1f}%",
                f"{details_mean * 100:.1f}%",
                f"{kinds_mean * 100:.1f}%",
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
        "Details",
        "Kinds",
        "Facets",
        "Keywords",
        "Cost",
        "Duration",
        "Passed",
    ]
    return "Enrichment Leaderboard\n\n" + _table(headers, rows)


def _zero_enrichment_scores() -> EnrichmentDimensionScores:
    return EnrichmentDimensionScores(
        ingredient_identity_precision=0.0,
        ingredient_identity_recall=0.0,
        ingredient_identity_f1=0.0,
        quantity_accuracy=0.0,
        unit_accuracy=0.0,
        preparation_accuracy=0.0,
        optional_accuracy=0.0,
        alternative_group_accuracy=0.0,
        ingredient_details_mean=0.0,
        line_kinds_accuracy=0.0,
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
        f"{candidate.provider}->{stage2_candidate.provider}"
        if mixed_models
        else candidate.provider
    )
    model_name = (
        f"{candidate.model}->{stage2_candidate.model}" if mixed_models else candidate.model
    )
    artefact_model = model_id.replace("/", "_").replace(":", "_").replace(" -> ", "__to__")
    usage1 = Usage()
    usage2 = Usage()

    try:
        active_vocab = vocab or {}
        proposals = build_gold_proposals(gold, active_vocab)
        stage1_context = build_gold_stage1_context(gold, proposals)

        if not stage1_context["recipe"]["ai_parse_line_ids"]:
            stage1_response = Stage1Response(p=[], n=[])
            usage1 = Usage()
        else:
            stage1_response, usage1 = provider.enrich_recipe_stage1(stage1_context, candidate.model)

        deterministic_lines = proposals_to_line_decisions(proposals, active_vocab)
        deterministic_names = [
            occ.canonical_name for line in deterministic_lines for occ in line.occurrences
        ]
        ai_names = [
            occ.canonical_name for line in stage1_response.parsed_lines for occ in line.occurrences
        ]
        ingredient_names = deterministic_names + ai_names

        stage2_context = build_gold_stage2_context(
            gold, ingredient_names, include_description=include_description
        )
        stage2_response, usage2 = stage2_provider.enrich_recipe_stage2(
            stage2_context, stage2_candidate.model
        )

        all_parsed_lines = deterministic_lines + stage1_response.parsed_lines
        combined_stage1 = Stage1Response(
            p=all_parsed_lines,
            n=stage1_response.non_ingredient_lines,
        )
        response = EnrichmentResponse.from_stages(combined_stage1, stage2_response)
        usage = usage1 + usage2

        full_context = build_gold_context(gold)
        try:
            validate_enrichment_response(full_context, response)
        except ValueError as exc:
            artefact_path = (
                run_dir
                / f"{gold.slug}_{artefact_model}.invalid.json"
            )
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

        artefact_path = (
            run_dir / f"{gold.slug}_{artefact_model}.json"
        )
        artefact_data = {
            "record": record.model_dump(),
            "response": response.model_dump(),
            "stage1": stage1_response.model_dump(),
            "stage2": stage2_response.model_dump(),
            "gold": gold.model_dump(),
            "include_description": include_description,
        }
        artefact_path.write_text(json.dumps(artefact_data, indent=2))
        return record

    except AIResponseError as exc:
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
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            scores=_zero_enrichment_scores(),
            input_tokens=exc.usage.input_tokens,
            output_tokens=exc.usage.output_tokens,
            candidate_tokens=exc.usage.candidate_tokens,
            thinking_tokens=exc.usage.thinking_tokens,
            cost_usd=float(exc.usage.cost_usd) if exc.usage.cost_usd is not None else None,
            duration_s=round(duration, 3),
            finish_reason=exc.usage.finish_reason,
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
