"""Batch building blocks for the recipe-enrichment backfill (MY-175, MY-187).

Pure helpers with no I/O: display-name/request-key identity, chunk planning,
request construction using exactly the MY-174 stage prompts and schemas, keyed
result correlation, poll backoff, and the versioned Batch pricing snapshot.
Stage 1 submits through `GeminiBatchClient` in
`app/services/ai/gemini_batch.py`; stage 2 submits through
`AnthropicBatchClient` in `app/services/ai/anthropic_batch.py`;
orchestration lives in `app/tasks/enrichment_backfill.py`.
"""

import json
import logging
from typing import Any

from app.services.recipe_enrichment.prompt import (
    build_stage1_prompt,
    build_stage2_prompt,
    build_stage2_prompts,
)
from app.services.recipe_enrichment.schema import (
    GEMINI_STAGE1_JSON_SCHEMA,
    GEMINI_STAGE2_JSON_SCHEMA,
    STAGE2_JSON_SCHEMA,
)

logger = logging.getLogger(__name__)

# Conservative chunk limits, well below Gemini's 2 GiB file cap: at most 500
# recipes or 50 MiB of encoded JSONL per local chunk, whichever fills first.
BATCH_CHUNK_MAX_RECIPES = 500
BATCH_CHUNK_MAX_BYTES = 50 * 1024 * 1024

# At most four remote jobs active at once; further chunks wait locally prepared.
BATCH_DEFAULT_MAX_ACTIVE_JOBS = 4

# Poll backoff: first re-check after 60 s, growing to a 15-minute ceiling.
BATCH_POLL_MIN_SECONDS = 60
BATCH_POLL_MAX_SECONDS = 900

# Failed items get one bounded automatic retry (two attempts total); afterwards
# the failure is terminal and the parent run finishes failed with successes kept.
BATCH_MAX_ATTEMPTS = 2

# Versioned Batch pricing snapshot (USD per million tokens). Batch bills at half
# the live rate; cost estimates are labelled with this snapshot version and never
# inferred by dividing live pricing at display time.
BATCH_PRICING_SNAPSHOT_VERSION = "2026-09-11"
BATCH_PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.15, 1.25),
    "gemini-2.5-flash-lite": (0.05, 0.20),
    "gemini-2.0-flash-lite": (0.0375, 0.15),
    "claude-haiku-4-5-20251001": (0.50, 2.50),
}


def batch_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate Batch cost from provider-reported tokens and the snapshot above."""
    input_rate, output_rate = BATCH_PRICING.get(model, (0.0, 0.0))
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


def job_key(run_id: str, chunk: int, stage: str, attempt: int) -> str:
    """Local intent key: unique per run, chunk, stage wave and attempt."""
    return f"{run_id}:c{chunk:03d}:{stage}:a{attempt}"


def display_name(run_id: str, chunk: int, stage: str, attempt: int) -> str:
    """Deterministic remote display name carrying run UUID, chunk and attempt.

    Creation is non-idempotent, so this name is persisted *before* submission
    and remote batches are queried for it first: an ambiguous failure adopts
    the existing job instead of creating a duplicate.
    """
    short = run_id.replace("-", "")[:12]
    return f"cookmarks-enrich-{short}-c{chunk:03d}-{stage}-a{attempt}"


def request_key(recipe_id: str, fingerprint: str | None) -> str:
    """JSONL correlation key: recipe UUID plus source fingerprint prefix."""
    short = (fingerprint or "nofp")[:12]
    return f"{recipe_id}:{short}"


def plan_chunks(sizes: list[int]) -> list[list[int]]:
    """Split recipe indexes into chunks capped by count and encoded bytes.

    `sizes` is the encoded JSONL byte length per recipe, in order. Returns the
    index groups; each group holds at most BATCH_CHUNK_MAX_RECIPES entries and
    at most BATCH_CHUNK_MAX_BYTES total bytes.
    """
    chunks: list[list[int]] = []
    current: list[int] = []
    current_bytes = 0
    for index, size in enumerate(sizes):
        if current and (
            len(current) >= BATCH_CHUNK_MAX_RECIPES or current_bytes + size > BATCH_CHUNK_MAX_BYTES
        ):
            chunks.append(current)
            current = []
            current_bytes = 0
        current.append(index)
        current_bytes += size
    if current:
        chunks.append(current)
    return chunks


def jsonl_size(rows: dict[str, str]) -> int:
    """Encoded byte size of a chunk payload as uploaded (one row per line)."""
    return sum(len(row.encode()) + 1 for row in rows.values())


def stage1_row(key: str, context: dict) -> str:
    """One JSONL line for a stage 1 (ingredient structuring) Batch request."""
    return json.dumps(
        {
            "key": key,
            "request": {
                "contents": [{"parts": [{"text": build_stage1_prompt(context)}]}],
                "generation_config": {
                    "temperature": 0,
                    "response_mime_type": "application/json",
                    "response_json_schema": GEMINI_STAGE1_JSON_SCHEMA,
                    "max_output_tokens": 4096,
                },
            },
        },
        ensure_ascii=False,
    )


def stage2_row(key: str, context: dict) -> str:
    """One JSONL line for a stage 2 (facet/keyword) Batch request."""
    return json.dumps(
        {
            "key": key,
            "request": {
                "contents": [{"parts": [{"text": build_stage2_prompt(context)}]}],
                "generation_config": {
                    "temperature": 0,
                    "response_mime_type": "application/json",
                    "response_json_schema": GEMINI_STAGE2_JSON_SCHEMA,
                    "max_output_tokens": 2048,
                },
            },
        },
        ensure_ascii=False,
    )


def anthropic_custom_id(key: str) -> str:
    """Sanitise a request key into a valid Anthropic `custom_id`.

    Anthropic requires `^[a-zA-Z0-9_-]{1,64}$`, but request keys join the
    recipe UUID and fingerprint with a colon. Neither UUIDs nor hex
    fingerprints ever contain an underscore, so the single `_` separator is
    unambiguous and `anthropic_request_key` reverses it exactly.
    """
    return key.replace(":", "_")


def anthropic_request_key(custom_id: str) -> str:
    """Reverse `anthropic_custom_id` back to the request key."""
    return custom_id.replace("_", ":", 1)


def anthropic_stage2_request(key: str, context: dict, model: str) -> dict[str, Any]:
    """One Anthropic Message Batch request for stage 2 (facet/keyword).

    Uses exactly the MY-174 stage 2 prompts with the full (un-stripped)
    `STAGE2_JSON_SCHEMA` as the structured-output tool schema.
    """
    system_prompt, user_prompt = build_stage2_prompts(context)
    return {
        "custom_id": anthropic_custom_id(key),
        "params": {
            "model": model,
            "max_tokens": 2048,
            "temperature": 0,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "tools": [
                {
                    "name": "structured_output",
                    "description": "Output structured data matching the schema",
                    "input_schema": STAGE2_JSON_SCHEMA,
                }
            ],
            "tool_choice": {"type": "tool", "name": "structured_output"},
        },
    }


def parse_anthropic_batch_item(
    item_result: dict,
) -> tuple[dict[str, Any] | None, dict[str, Any], str | None]:
    """Split one Anthropic batch result into (parsed, usage, error).

    `item_result` is one decoded `MessageBatchIndividualResponse` dict with
    `custom_id` and `result`. On success returns the structured tool-use input
    dict, the token usage, and None. On `errored`/`canceled`/`expired` (or a
    response with no structured tool use) returns (None, usage, error text).
    """
    result = item_result.get("result") if isinstance(item_result, dict) else None
    if not isinstance(result, dict):
        return None, {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}, (
            "batch item has no result"
        )
    result_type = result.get("type")
    if result_type != "succeeded":
        error = result.get("error")
        message: str | None = None
        if isinstance(error, dict):
            inner = error.get("error")
            if isinstance(inner, dict):
                message = inner.get("message") or error.get("message")
            else:
                message = error.get("message")
            if message is None:
                message = str(error)
        elif error is not None:
            message = str(error)
        if not message:
            message = f"batch item {result_type or 'failed'}"
        return (
            None,
            {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0},
            str(message)[:1000],
        )
    message_obj = result.get("message")
    if not isinstance(message_obj, dict):
        return (
            None,
            {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0},
            "batch item message missing",
        )
    usage = message_obj.get("usage") if isinstance(message_obj.get("usage"), dict) else {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    cached_tokens = int(usage.get("cache_read_input_tokens") or 0) + int(
        usage.get("cache_creation_input_tokens") or 0
    )
    usage_dict: dict[str, Any] = {
        "model": message_obj.get("model"),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
    }
    content = message_obj.get("content") or []
    if isinstance(content, list):
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "structured_output"
                and isinstance(block.get("input"), dict)
            ):
                return block["input"], usage_dict, None
    return None, usage_dict, "no structured tool use in response"


def poll_countdown(polls_done: int) -> int:
    """Increasing re-poll delay: 60 s doubling to the 15-minute ceiling."""
    delay = BATCH_POLL_MIN_SECONDS * (2**polls_done)
    return min(delay, BATCH_POLL_MAX_SECONDS)


def correlate_results(lines: list[str], expected_keys: set[str]) -> tuple[dict[str, dict], list[str]]:
    """Correlate output JSONL rows by request key, never by output order.

    Returns (by_key, problems): the first row per known key, plus a problem
    list covering unknown keys, duplicate keys and missing keys. Callers treat
    any problem as a per-item failure, never a silent skip.
    """
    by_key: dict[str, dict] = {}
    problems: list[str] = []
    seen: set[str] = set()
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"line {lineno}: unparseable JSON")
            continue
        key = row.get("key")
        if not isinstance(key, str) or not key:
            problems.append(f"line {lineno}: missing key")
            continue
        if key not in expected_keys:
            problems.append(f"line {lineno}: unknown key {key}")
            continue
        if key in seen:
            problems.append(f"line {lineno}: duplicate key {key}")
            continue
        seen.add(key)
        by_key[key] = row
    for key in sorted(expected_keys - seen):
        problems.append(f"missing key {key}")
    return by_key, problems
