"""Gemini Batch building blocks for the recipe-enrichment backfill (MY-175).

Pure helpers with no I/O: display-name/request-key identity, chunk planning,
JSONL row construction using exactly the MY-174 stage prompts and
Gemini-compilable schemas, keyed result correlation, poll backoff, and the
versioned Batch pricing snapshot. The provider I/O lives behind
`GeminiBatchClient` in `app/services/ai/gemini_batch.py`; orchestration lives
in `app/tasks/enrichment_backfill.py`.
"""

import json
import logging

from app.services.recipe_enrichment.prompt import build_stage1_prompt, build_stage2_prompt
from app.services.recipe_enrichment.schema import (
    GEMINI_STAGE1_JSON_SCHEMA,
    GEMINI_STAGE2_JSON_SCHEMA,
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
BATCH_PRICING_SNAPSHOT_VERSION = "2026-08-31"
BATCH_PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.15, 1.25),
    "gemini-2.5-flash-lite": (0.05, 0.20),
    "gemini-2.0-flash-lite": (0.0375, 0.15),
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
                },
            },
        },
        ensure_ascii=False,
    )


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
