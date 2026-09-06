"""Durable Gemini Batch recipe-enrichment backfill (MY-175).

Two sequential waves reuse exactly the MY-174 stage prompts, Gemini schemas,
validator and atomic apply service: stage 1 (ingredient structuring) first,
then stage 2 (facet/keyword assignment) whose contexts need stage 1 AI
ingredient names. Each wave chunks recipes at 500 items / 50 MiB of JSONL and
keeps at most four remote jobs active; further chunks wait locally prepared.

Lifecycle on the parent TaskRun:
queued → running (prepare/submit) → waiting (remote jobs) → running
(download/apply) → done | failed. Failed items get one bounded retry; stale
items (source changed mid-flight) wait for a later run. Resume creates a new
parent run selecting only recipes not yet current.
"""

import logging
import uuid
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.db import SessionLocal
from app.models.enums import (
    EnrichmentBatchItemStatus,
    EnrichmentBatchStatus,
    RecipeEnrichmentStatus,
    TaskStatus,
    TaskType,
)
from app.models.ingredient import IngredientLine
from app.models.recipe import Keyword, Recipe
from app.models.recipe_enrichment import RecipeEnrichmentState
from app.models.recipe_enrichment_batch import RecipeEnrichmentBatch, RecipeEnrichmentBatchItem
from app.models.task_run import TaskRun
from app.services.ai import Usage, get_ai_provider, get_config
from app.services.ai.base import ModelRole, _strip_json_fence
from app.services.ai.gemini_batch import ACTIVE_STATES, SUCCEEDED_STATES, GeminiBatchClient
from app.services.embeddings import backfill as backfill_embeddings
from app.services.embeddings import embed_recipes
from app.services.recipe_enrichment.batch import (
    BATCH_CHUNK_MAX_BYTES,
    BATCH_CHUNK_MAX_RECIPES,
    BATCH_DEFAULT_MAX_ACTIVE_JOBS,
    BATCH_MAX_ATTEMPTS,
    BATCH_PRICING_SNAPSHOT_VERSION,
    batch_cost_usd,
    correlate_results,
    display_name,
    job_key,
    plan_chunks,
    poll_countdown,
    request_key,
    stage1_row,
    stage2_row,
)
from app.services.recipe_enrichment.schema import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    TAXONOMY_VERSION,
    EnrichmentResponse,
    Stage1Response,
    Stage2Response,
)
from app.services.recipe_enrichment.service import (
    apply_enrichment,
    build_context,
    build_stage1_context,
    build_stage2_context,
    ensure_source_fingerprint,
    source_fingerprint,
)
from app.tasks.celery_app import celery_app
from app.tasks.runs import complete_run, fail_run, set_running, set_waiting, start_run

logger = logging.getLogger(__name__)

TERMINAL_ITEM_STATES = frozenset(
    {
        EnrichmentBatchItemStatus.APPLIED,
        EnrichmentBatchItemStatus.STALE,
        EnrichmentBatchItemStatus.FAILED,
    }
)


def _versions() -> dict[str, str]:
    return {
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
    }


def _is_current(state: RecipeEnrichmentState | None, recipe: Recipe) -> bool:
    """A recipe is current when COMPLETE for this source and these versions."""
    if state is None or state.status is not RecipeEnrichmentStatus.COMPLETE:
        return False
    return (
        state.source_fingerprint == source_fingerprint(recipe)
        and state.schema_version == SCHEMA_VERSION
        and state.prompt_version == PROMPT_VERSION
        and state.taxonomy_version == TAXONOMY_VERSION
    )


def select_backfill_recipe_ids(session: Session) -> list[uuid.UUID]:
    """Every recipe not yet current for this source fingerprint and versions.

    Resume-safe: re-running selects only what is still outstanding, so invoking
    resume repeatedly never re-enriches current recipes.
    """
    recipes = session.scalars(
        select(Recipe)
        .options(selectinload(Recipe.ingredients_verbatim), selectinload(Recipe.enrichment_state))
        .order_by(Recipe.id)
    ).all()
    return [recipe.id for recipe in recipes if not _is_current(recipe.enrichment_state, recipe)]


def _ensure_state(session: Session, recipe: Recipe) -> RecipeEnrichmentState:
    state = recipe.enrichment_state
    if state is None:
        state = RecipeEnrichmentState(recipe_id=recipe.id)
        session.add(state)
        session.flush()
        recipe.enrichment_state = state
    return state


def _batch_client(session: Session) -> tuple[GeminiBatchClient, str]:
    """Build the Batch client from the configured Gemini API key plus model name."""
    config = get_config(session)
    if config.ai_provider != "GEMINI":
        raise RuntimeError("Recipe-enrichment backfill requires the Gemini provider")
    if not config.api_key:
        raise RuntimeError("Gemini provider is configured without an API key")
    provider = get_ai_provider(session)
    model = (
        provider.model_for(ModelRole.RECIPE_ENRICHMENT)
        if provider is not None
        else "gemini-2.5-flash"
    )
    return GeminiBatchClient(config.api_key), model


def _recipe_map(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, Recipe]:
    return {
        recipe.id: recipe
        for recipe in session.scalars(
            select(Recipe)
            .where(Recipe.id.in_(ids))
            .options(
                selectinload(Recipe.ingredients_verbatim),
                selectinload(Recipe.enrichment_state),
                selectinload(Recipe.book),
            )
        )
    }


def prepare_stage_chunks(
    session: Session,
    run: TaskRun,
    recipe_ids: list[uuid.UUID],
    *,
    stage: str,
    attempt: int,
    first_chunk: int,
) -> list[RecipeEnrichmentBatch]:
    """Persist preparing batch rows + items for one wave, returning the chunks.

    Recipes whose lines resolve fully deterministically skip the remote stage 1
    call: their items are marked succeeded locally with the deterministic
    ingredient names captured. Everything else becomes one JSONL row per recipe.
    """
    recipes = _recipe_map(session, recipe_ids)
    rows: list[tuple[uuid.UUID, str]] = []
    deterministic: dict[uuid.UUID, list[str]] = {}
    for recipe_id in recipe_ids:
        recipe = recipes.get(recipe_id)
        if recipe is None:
            continue
        state = _ensure_state(session, recipe)
        ensure_source_fingerprint(recipe)
        key = request_key(str(recipe_id), state.source_fingerprint)
        if stage == "stage1":
            _context, proposals = build_context(session, recipe)
            stage1_context = build_stage1_context(recipe, proposals)
            if not stage1_context["recipe"]["ai_parse_line_ids"]:
                deterministic[recipe_id] = [
                    occ.name for proposal in proposals.values() for occ in proposal.occurrences
                ]
                rows.append((recipe_id, ""))
                continue
            rows.append((recipe_id, stage1_row(key, stage1_context)))
        else:
            rows.append((recipe_id, ""))
    sizes = [len(content.encode()) if content else 1 for _, content in rows]
    groups = plan_chunks(sizes)
    batches: list[RecipeEnrichmentBatch] = []
    for offset, group in enumerate(groups):
        chunk = first_chunk + offset
        batch = RecipeEnrichmentBatch(
            task_run_id=run.id,
            job_key=job_key(str(run.id), chunk, stage, attempt),
            display_name=display_name(str(run.id), chunk, stage, attempt),
            status=EnrichmentBatchStatus.PREPARING,
            stage=stage,
            attempt=attempt,
            **_versions(),
            provider="GEMINI",
        )
        session.add(batch)
        session.flush()
        for index in group:
            recipe_id, _content = rows[index]
            recipe = recipes[recipe_id]
            assert recipe.enrichment_state is not None
            if recipe_id in deterministic:
                item = RecipeEnrichmentBatchItem(
                    batch_id=batch.id,
                    recipe_id=recipe_id,
                    source_fingerprint=recipe.enrichment_state.source_fingerprint,
                    request_key=request_key(
                        str(recipe_id), recipe.enrichment_state.source_fingerprint
                    ),
                    status=EnrichmentBatchItemStatus.SUCCEEDED,
                    attempt=attempt,
                    stage1_ingredients=deterministic[recipe_id],
                )
                session.add(item)
                continue
            session.add(
                RecipeEnrichmentBatchItem(
                    batch_id=batch.id,
                    recipe_id=recipe_id,
                    source_fingerprint=recipe.enrichment_state.source_fingerprint,
                    request_key=request_key(
                        str(recipe_id), recipe.enrichment_state.source_fingerprint
                    ),
                    status=EnrichmentBatchItemStatus.PENDING,
                    attempt=attempt,
                )
            )
        session.flush()
        batches.append(batch)
    session.commit()
    return batches


def build_stage2_payloads(
    session: Session, batch: RecipeEnrichmentBatch
) -> dict[str, str]:
    """Build stage 2 JSONL rows for a batch from ingested stage 1 results.

    Eligible items already hold stage 1 data (freshly promoted or retry items
    with stage1_response kept and stage2 stripped) — or resolved fully
    deterministically with no remote stage 1 call, in which case the stored
    response is empty and facet assignment still runs. Items already APPLIED
    are never rebuilt.
    """
    eligible = [
        item for item in batch.items
        if item.status in (EnrichmentBatchItemStatus.SUCCEEDED, EnrichmentBatchItemStatus.PENDING)
        and "stage2" not in (item.stage1_response or {})
    ]
    recipes = _recipe_map(session, [item.recipe_id for item in eligible])
    payloads: dict[str, str] = {}
    for item in eligible:
        recipe = recipes.get(item.recipe_id)
        if recipe is None:
            continue
        _context, proposals = build_context(session, recipe)
        deterministic_names = [
            occ.name for proposal in proposals.values() for occ in proposal.occurrences
        ]
        stage2_context = build_stage2_context(
            session, recipe, [*deterministic_names, *item.stage1_ingredients]
        )
        payloads[item.request_key] = stage2_row(item.request_key, stage2_context)
    return payloads


def submit_prepared(
    session: Session,
    run: TaskRun,
    client: GeminiBatchClient,
    model: str,
    *,
    max_active: int = BATCH_DEFAULT_MAX_ACTIVE_JOBS,
) -> int:
    """Upload + create remote jobs for preparing batches while a slot is free.

    Stage 1 rows rebuild deterministically from the recipes; stage 2 rows build
    from ingested stage 1 data at submit time. Submitted keys persist on the
    batch so ingest correlates exactly what was sent. Returns submitted count.
    """
    active = session.scalar(
        select(func.count())
        .select_from(RecipeEnrichmentBatch)
        .where(
            RecipeEnrichmentBatch.task_run_id == run.id,
            RecipeEnrichmentBatch.status == EnrichmentBatchStatus.SUBMITTED,
        )
    ) or 0
    submitted = 0
    preparing = session.scalars(
        select(RecipeEnrichmentBatch)
        .where(
            RecipeEnrichmentBatch.task_run_id == run.id,
            RecipeEnrichmentBatch.status == EnrichmentBatchStatus.PREPARING,
        )
        .order_by(RecipeEnrichmentBatch.created_at)
    ).all()
    for batch in preparing:
        if active >= max_active:
            break
        if batch.stage == "stage2":
            rows = build_stage2_payloads(session, batch)
        else:
            rows = _rebuild_stage1_payloads(session, batch)
        if not rows:
            batch.status = EnrichmentBatchStatus.SUCCEEDED
            batch.completed_at = datetime.now(UTC)
            session.commit()
            continue
        content = "".join(f"{rows[key]}\n" for key in sorted(rows))
        if len(content.encode()) > BATCH_CHUNK_MAX_BYTES or len(rows) > BATCH_CHUNK_MAX_RECIPES:
            _split_oversized(session, batch, rows)
            continue
        # Non-idempotent create: reconcile by display name before creating.
        existing = client.find_by_display_name(batch.display_name)
        if existing:
            adopted = sorted(existing, key=lambda job: job.name)[0]
            batch.provider_batch_id = adopted.name
            batch.duplicate_ids = sorted(
                {job.name for job in existing if job.name != adopted.name}
            )
            for extra in batch.duplicate_ids:
                client.cancel_job(extra)
        else:
            input_file_id = client.upload_jsonl(content, display_name=batch.display_name)
            batch.input_file_id = input_file_id
            session.commit()
            # Crash window: remote job may exist while the local ID is not yet
            # saved — the next poll reconciles by display name, adopting it.
            created = client.create_job(
                model=model, input_file_id=input_file_id, display_name=batch.display_name
            )
            batch.provider_batch_id = created.name
        batch.status = EnrichmentBatchStatus.SUBMITTED
        batch.request_count = len(rows)
        batch.submitted_keys = sorted(rows)
        batch.model = model
        batch.submitted_at = datetime.now(UTC)
        session.commit()
        active += 1
        submitted += 1
    return submitted


def _rebuild_stage1_payloads(session: Session, batch: RecipeEnrichmentBatch) -> dict[str, str]:
    """Rebuild stage 1 JSONL rows deterministically from the recipes."""
    recipes = _recipe_map(session, [item.recipe_id for item in batch.items])
    payloads: dict[str, str] = {}
    for item in batch.items:
        if item.status is not EnrichmentBatchItemStatus.PENDING:
            continue
        recipe = recipes.get(item.recipe_id)
        if recipe is None:
            item.status = EnrichmentBatchItemStatus.FAILED
            item.provider_error = "recipe missing at submit"
            continue
        _context, proposals = build_context(session, recipe)
        stage1_context = build_stage1_context(recipe, proposals)
        if not stage1_context["recipe"]["ai_parse_line_ids"]:
            item.status = EnrichmentBatchItemStatus.SUCCEEDED
            item.stage1_ingredients = [
                occ.name for proposal in proposals.values() for occ in proposal.occurrences
            ]
            continue
        payloads[item.request_key] = stage1_row(item.request_key, stage1_context)
    session.commit()
    return payloads


def _split_oversized(
    session: Session, batch: RecipeEnrichmentBatch, rows: dict[str, str]
) -> None:
    """Split an oversized preparing batch into smaller preparing batches."""
    keys = sorted(rows)
    sizes = [len(rows[key].encode()) + 1 for key in keys]
    groups = plan_chunks(sizes)
    items = {item.request_key: item for item in batch.items}
    run_id = batch.task_run_id
    base_chunk = len(
        session.scalars(
            select(RecipeEnrichmentBatch).where(
                RecipeEnrichmentBatch.task_run_id == run_id
            )
        ).all()
    )
    for offset, group in enumerate(groups):
        sibling = RecipeEnrichmentBatch(
            task_run_id=run_id,
            job_key=job_key(str(run_id), base_chunk + offset, batch.stage, batch.attempt),
            display_name=display_name(
                str(run_id), base_chunk + offset, batch.stage, batch.attempt
            ),
            status=EnrichmentBatchStatus.PREPARING,
            stage=batch.stage,
            attempt=batch.attempt,
            **_versions(),
            provider="GEMINI",
        )
        session.add(sibling)
        session.flush()
        for index in group:
            item = items[keys[index]]
            item.batch_id = sibling.id
    session.delete(batch)
    session.commit()


def _extract_text(response: dict) -> str | None:
    try:
        candidates = response.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(part.get("text", "") or "" for part in parts)
    except (IndexError, AttributeError):
        return None


def _response_usage(response: dict) -> dict:
    meta = response.get("usageMetadata") or {}
    return {
        "input_tokens": int(meta.get("promptTokenCount") or 0),
        "output_tokens": int(
            (meta.get("candidatesTokenCount") or 0) + (meta.get("thoughtsTokenCount") or 0)
        ),
        "cached_tokens": int(meta.get("cachedContentTokenCount") or 0),
    }


def ingest_succeeded_batch(
    session: Session, batch: RecipeEnrichmentBatch, lines: list[str]
) -> None:
    """Correlate one completed job's output rows by key and record per-item results."""
    expected = set(batch.submitted_keys or [])
    if not expected:
        expected = {item.request_key for item in batch.items if item.status is
                    EnrichmentBatchItemStatus.PENDING}
    by_key, problems = correlate_results(lines, expected)
    items = {item.request_key: item for item in batch.items}
    for problem in problems:
        logger.warning("Batch %s result problem: %s", batch.job_key, problem)
    for key in sorted(expected):
        item = items[key]
        row = by_key.get(key)
        if row is None:
            item.status = EnrichmentBatchItemStatus.FAILED
            item.provider_error = "missing from provider output"
            continue
        if isinstance(row.get("error"), dict):
            err = row["error"]
            item.status = EnrichmentBatchItemStatus.FAILED
            item.provider_error = str(err.get("message", err))[:1000]
            item.provider_code = str(err.get("code", ""))[:100]
            continue
        response = row.get("response")
        if not isinstance(response, dict):
            item.status = EnrichmentBatchItemStatus.FAILED
            item.provider_error = "provider row has no response"
            continue
        item.usage = _response_usage(response)
        text = _extract_text(response)
        if not text:
            item.status = EnrichmentBatchItemStatus.FAILED
            item.provider_error = "empty provider response"
            continue
        try:
            if batch.stage == "stage1":
                parsed = Stage1Response.model_validate_json(_strip_json_fence(text))
                item.stage1_response = parsed.model_dump(mode="json", by_alias=True)
                item.stage1_ingredients = [
                    occ.canonical_name
                    for line in parsed.parsed_lines
                    for occ in line.occurrences
                ]
            else:
                parsed = Stage2Response.model_validate_json(_strip_json_fence(text))
                item.stage1_response = {
                    **(item.stage1_response or {}),
                    "stage2": parsed.model_dump(mode="json", by_alias=True),
                }
        except ValidationError as exc:
            item.status = EnrichmentBatchItemStatus.FAILED
            item.provider_error = f"invalid structured response: {exc}"[:1000]
            continue
        item.status = EnrichmentBatchItemStatus.SUCCEEDED
    batch.status = EnrichmentBatchStatus.SUCCEEDED
    batch.completed_at = datetime.now(UTC)
    session.commit()


def apply_ready_stage2(
    session: Session, run: TaskRun, provider_model: str
) -> dict[str, int]:
    """Apply every succeeded stage 2 item through the MY-174 atomic service.

    Each recipe commits independently: one bad response never rolls back good
    recipes. A source change since capture marks the item stale for a later run.
    """
    provider = get_ai_provider(session)
    if provider is None:
        raise RuntimeError("No usable AI provider is configured")
    counts = Counter(applied=0, stale=0, failed=0)
    items = session.scalars(
        select(RecipeEnrichmentBatchItem)
        .join(RecipeEnrichmentBatch, RecipeEnrichmentBatchItem.batch_id == RecipeEnrichmentBatch.id)
        .where(
            RecipeEnrichmentBatch.task_run_id == run.id,
            RecipeEnrichmentBatch.stage == "stage2",
            RecipeEnrichmentBatchItem.status == EnrichmentBatchItemStatus.SUCCEEDED,
        )
    ).all()
    # Only items whose stage 2 response actually arrived (ingest stored it under
    # "stage2") — freshly promoted items wait for their remote wave.
    items = [item for item in items if (item.stage1_response or {}).get("stage2")]
    for item in items:
        recipe = session.get(Recipe, item.recipe_id)
        if recipe is None:
            item.status = EnrichmentBatchItemStatus.FAILED
            item.provider_error = "recipe missing at apply"
            session.commit()
            counts["failed"] += 1
            continue
        if source_fingerprint(recipe) != item.source_fingerprint:
            item.status = EnrichmentBatchItemStatus.STALE
            session.commit()
            counts["stale"] += 1
            continue
        try:
            stored = item.stage1_response or {}
            stage2_payload = stored.get("stage2")
            if stage2_payload is None:
                raise ValueError("stage 2 response missing")
            stage1 = Stage1Response.model_validate(
                {k: v for k, v in stored.items() if k != "stage2"})
            stage2 = Stage2Response.model_validate(stage2_payload)
            response = EnrichmentResponse.from_stages(stage1, stage2)
            _context, proposals = build_context(session, recipe)
            metrics = apply_enrichment(
                session,
                recipe.id,
                response,
                proposals,
                provider=provider,
                model=provider_model,
                task_run_id=run.id,
            )
            session.commit()
            try:
                embed_recipes(session, [recipe], provider)
                session.commit()
            except Exception:
                logger.warning("Post-apply embedding failed for %s", recipe.id)
                session.rollback()
            item.status = EnrichmentBatchItemStatus.APPLIED
            item.applied_at = datetime.now(UTC)
            item.usage = {**item.usage, **{k: metrics.get(k, 0) for k in (
                "deterministic_accepted", "ai_parsed_lines", "headings",
                "ingredients_created", "existing_ingredients", "aliases_created")}}
            session.commit()
            counts["applied"] += 1
        except Exception as exc:
            session.rollback()
            item.status = EnrichmentBatchItemStatus.FAILED
            item.provider_error = str(exc)[:1000]
            session.commit()
            counts["failed"] += 1
    return dict(counts)


def build_retry_chunks(session: Session, run: TaskRun) -> int:
    """Re-queue failed (never stale) items into new preparing chunks, once."""
    retryable = session.scalars(
        select(RecipeEnrichmentBatchItem)
        .join(RecipeEnrichmentBatch, RecipeEnrichmentBatchItem.batch_id == RecipeEnrichmentBatch.id)
        .where(
            RecipeEnrichmentBatch.task_run_id == run.id,
            RecipeEnrichmentBatchItem.status == EnrichmentBatchItemStatus.FAILED,
            RecipeEnrichmentBatchItem.attempt < BATCH_MAX_ATTEMPTS,
        )
    ).all()
    if not retryable:
        return 0
    by_stage: dict[str, list[RecipeEnrichmentBatchItem]] = {}
    for item in retryable:
        batch = session.get(RecipeEnrichmentBatch, item.batch_id)
        assert batch is not None
        by_stage.setdefault(batch.stage, []).append(item)
    created = 0
    existing_chunks = session.scalar(
        select(func.count())
        .select_from(RecipeEnrichmentBatch)
        .where(RecipeEnrichmentBatch.task_run_id == run.id)
    ) or 0
    for stage, items in by_stage.items():
        attempt = max(item.attempt for item in items) + 1
        batch = RecipeEnrichmentBatch(
            task_run_id=run.id,
            job_key=job_key(str(run.id), existing_chunks + created, stage, attempt),
            display_name=display_name(str(run.id), existing_chunks + created, stage, attempt),
            status=EnrichmentBatchStatus.PREPARING,
            stage=stage,
            attempt=attempt,
            **_versions(),
            provider="GEMINI",
        )
        session.add(batch)
        session.flush()
        for item in items:
            # A re-queued stage 2 item must go remote again: drop its previous
            # stage 2 payload so only a fresh response can apply.
            stored = dict(item.stage1_response or {})
            stored.pop("stage2", None)
            item.stage1_response = stored
            item.batch_id = batch.id
            item.attempt = attempt
            item.status = EnrichmentBatchItemStatus.PENDING
            item.provider_error = None
            item.provider_code = None
        created += 1
    session.commit()
    return created


def build_progress_detail(session: Session, run: TaskRun) -> dict:
    """Aggregate Task Runs progress: counts, chunks, metrics, usage, cost, poll."""
    batches = session.scalars(
        select(RecipeEnrichmentBatch).where(RecipeEnrichmentBatch.task_run_id == run.id)
    ).all()
    items = session.scalars(
        select(RecipeEnrichmentBatchItem)
        .join(RecipeEnrichmentBatch, RecipeEnrichmentBatchItem.batch_id == RecipeEnrichmentBatch.id)
        .where(RecipeEnrichmentBatch.task_run_id == run.id)
    ).all()
    item_states = Counter(item.status.value for item in items)
    chunks_by_state = Counter(batch.status.value for batch in batches)
    attempts = Counter(f"attempt_{batch.attempt}" for batch in batches)
    submitted_batch_ids = {
        batch.id for batch in batches
        if batch.status
        in (EnrichmentBatchStatus.SUBMITTED, EnrichmentBatchStatus.SUCCEEDED,
            EnrichmentBatchStatus.APPLIED)
    }
    submitted_items = sum(1 for item in items if item.batch_id in submitted_batch_ids)
    input_tokens = sum((item.usage or {}).get("input_tokens", 0) for item in items)
    output_tokens = sum((item.usage or {}).get("output_tokens", 0) for item in items)
    cached_tokens = sum((item.usage or {}).get("cached_tokens", 0) for item in items)
    model = next((b.model for b in batches if b.model), None)
    line_counts = Counter()
    cuisines: Counter[str] = Counter()
    methods: Counter[str] = Counter()
    courses: Counter[str] = Counter()
    keyword_failures = 0
    for item in items:
        usage = item.usage or {}
        for key in (
            "deterministic_accepted", "ai_parsed_lines", "headings",
            "ingredients_created", "existing_ingredients", "aliases_created",
        ):
            line_counts[key] += int(usage.get(key, 0) or 0)
        if item.provider_error and "keyword" in item.provider_error.lower():
            keyword_failures += 1
    started = run.started_at
    elapsed = (datetime.now(UTC) - started.replace(tzinfo=UTC)).total_seconds() if started else 0
    last_error = next(
        (b.last_error for b in sorted(batches, key=lambda b: b.created_at, reverse=True)
         if b.last_error),
        next((i.provider_error for i in items if i.provider_error), None),
    )
    return {
        "selected": run.detail.get("selected", 0),
        "prepared": len(items),
        "submitted": submitted_items,
        "succeeded": item_states.get("succeeded", 0),
        "applied": item_states.get("applied", 0),
        "stale": item_states.get("stale", 0),
        "terminal_failed": item_states.get("failed", 0),
        "chunks_by_state": dict(chunks_by_state),
        "attempts": dict(attempts),
        "polls_done": run.detail.get("polls_done", 0),
        "next_poll_in_seconds": run.detail.get("next_poll_in_seconds"),
        "last_provider_error": last_error,
        **{f"lines_{k}": v for k, v in line_counts.items()},
        "cuisine_frequency": dict(cuisines),
        "method_frequency": dict(methods),
        "course_frequency": dict(courses),
        "keyword_validation_failures": keyword_failures,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "cost_estimate_usd": round(batch_cost_usd(model or "", input_tokens, output_tokens), 4),
        "pricing_snapshot_version": BATCH_PRICING_SNAPSHOT_VERSION,
        "elapsed_seconds": round(elapsed, 1),
        **_versions(),
    }


def _refresh_submitted(
    session: Session, run: TaskRun, client: GeminiBatchClient
) -> tuple[int, str | None]:
    """Poll every submitted batch; ingest completions. Returns (active, error)."""
    submitted = session.scalars(
        select(RecipeEnrichmentBatch)
        .where(
            RecipeEnrichmentBatch.task_run_id == run.id,
            RecipeEnrichmentBatch.status == EnrichmentBatchStatus.SUBMITTED,
        )
    ).all()
    active = 0
    last_error: str | None = None
    for batch in submitted:
        assert batch.provider_batch_id is not None
        try:
            remote = client.get_job(batch.provider_batch_id)
        except Exception as exc:
            last_error = str(exc)[:500]
            active += 1
            continue
        if remote.state in ACTIVE_STATES:
            active += 1
        elif remote.state in SUCCEEDED_STATES:
            if not remote.output_file_id:
                batch.status = EnrichmentBatchStatus.FAILED
                batch.last_error = "remote job succeeded without an output file"
                last_error = batch.last_error
                session.commit()
                continue
            try:
                batch.result_file_id = remote.output_file_id
                lines = client.download_lines(remote.output_file_id)
            except Exception as exc:
                # Transient download: stay submitted and retry next poll.
                last_error = str(exc)[:500]
                active += 1
                continue
            ingest_succeeded_batch(session, batch, lines)
        else:
            error_text = remote.error or f"remote job state {remote.state}"
            batch.status = EnrichmentBatchStatus.FAILED
            batch.last_error = error_text
            last_error = error_text
            for item in batch.items:
                if item.status is EnrichmentBatchItemStatus.PENDING:
                    item.status = EnrichmentBatchItemStatus.FAILED
                    item.provider_error = error_text[:1000]
            session.commit()
    return active, last_error


def _promote_stage2(session: Session, run: TaskRun) -> None:
    """Create stage 2 preparing chunks for stage 1 batches that just succeeded.

    A promoted stage 1 batch moves to APPLIED (consumed into the stage 2 wave)
    so each source batch promotes exactly once, however often polls run.
    """
    stage1_done = session.scalars(
        select(RecipeEnrichmentBatch).where(
            RecipeEnrichmentBatch.task_run_id == run.id,
            RecipeEnrichmentBatch.stage == "stage1",
            RecipeEnrichmentBatch.status == EnrichmentBatchStatus.SUCCEEDED,
        )
    ).all()
    if not stage1_done:
        return
    chunk_no = session.scalar(
        select(func.count())
        .select_from(RecipeEnrichmentBatch)
        .where(RecipeEnrichmentBatch.task_run_id == run.id)
    ) or 0
    for batch in stage1_done:
        succeeded_items = [
            item for item in batch.items
            if item.status is EnrichmentBatchItemStatus.SUCCEEDED
        ]
        if succeeded_items:
            sibling = RecipeEnrichmentBatch(
                task_run_id=run.id,
                job_key=job_key(str(run.id), chunk_no, "stage2", batch.attempt),
                display_name=display_name(str(run.id), chunk_no, "stage2", batch.attempt),
                status=EnrichmentBatchStatus.PREPARING,
                stage="stage2",
                attempt=batch.attempt,
                **_versions(),
                provider="GEMINI",
            )
            session.add(sibling)
            session.flush()
            for item in succeeded_items:
                session.add(
                    RecipeEnrichmentBatchItem(
                        batch_id=sibling.id,
                        recipe_id=item.recipe_id,
                        source_fingerprint=item.source_fingerprint,
                        request_key=item.request_key,
                        status=EnrichmentBatchItemStatus.SUCCEEDED,
                        attempt=item.attempt,
                        usage=dict(item.usage or {}),
                        stage1_ingredients=list(item.stage1_ingredients or []),
                        stage1_response=dict(item.stage1_response or {}),
                    )
                )
            chunk_no += 1
        batch.status = EnrichmentBatchStatus.APPLIED
        batch.applied_at = datetime.now(UTC)
    session.commit()


def _is_terminal(session: Session, run: TaskRun) -> bool:
    open_batches = session.scalar(
        select(func.count())
        .select_from(RecipeEnrichmentBatch)
        .where(
            RecipeEnrichmentBatch.task_run_id == run.id,
            RecipeEnrichmentBatch.status.in_(
                [EnrichmentBatchStatus.PREPARING, EnrichmentBatchStatus.SUBMITTED]
            ),
        )
    ) or 0
    if open_batches:
        return False
    retryable = session.scalar(
        select(func.count())
        .select_from(RecipeEnrichmentBatchItem)
        .join(RecipeEnrichmentBatch, RecipeEnrichmentBatchItem.batch_id == RecipeEnrichmentBatch.id)
        .where(
            RecipeEnrichmentBatch.task_run_id == run.id,
            RecipeEnrichmentBatchItem.status == EnrichmentBatchItemStatus.FAILED,
            RecipeEnrichmentBatchItem.attempt < BATCH_MAX_ATTEMPTS,
        )
    ) or 0
    return not retryable


def _finalise(session: Session, run: TaskRun, usage: Usage) -> dict:
    applied = session.scalar(
        select(func.count())
        .select_from(RecipeEnrichmentBatchItem)
        .join(RecipeEnrichmentBatch, RecipeEnrichmentBatchItem.batch_id == RecipeEnrichmentBatch.id)
        .where(
            RecipeEnrichmentBatch.task_run_id == run.id,
            RecipeEnrichmentBatchItem.status == EnrichmentBatchItemStatus.APPLIED,
        )
    ) or 0
    failed = session.scalar(
        select(func.count())
        .select_from(RecipeEnrichmentBatchItem)
        .join(RecipeEnrichmentBatch, RecipeEnrichmentBatchItem.batch_id == RecipeEnrichmentBatch.id)
        .where(
            RecipeEnrichmentBatch.task_run_id == run.id,
            RecipeEnrichmentBatchItem.status == EnrichmentBatchItemStatus.FAILED,
        )
    ) or 0
    stale = session.scalar(
        select(func.count())
        .select_from(RecipeEnrichmentBatchItem)
        .join(RecipeEnrichmentBatch, RecipeEnrichmentBatchItem.batch_id == RecipeEnrichmentBatch.id)
        .where(
            RecipeEnrichmentBatch.task_run_id == run.id,
            RecipeEnrichmentBatchItem.status == EnrichmentBatchItemStatus.STALE,
        )
    ) or 0
    failures = [
        {"recipe_id": str(item.recipe_id), "error": (item.provider_error or "")[:300]}
        for item in session.scalars(
            select(RecipeEnrichmentBatchItem)
            .join(RecipeEnrichmentBatch,
                  RecipeEnrichmentBatchItem.batch_id == RecipeEnrichmentBatch.id)
            .where(
                RecipeEnrichmentBatch.task_run_id == run.id,
                RecipeEnrichmentBatchItem.status == EnrichmentBatchItemStatus.FAILED,
            )
        ).all()
    ]
    progress = build_progress_detail(session, run)
    if failed or stale:
        detail = {**progress, "applied": applied, "failures": failures}
        complete_run(str(run.id), detail, usage)
        session.refresh(run)
        run.status = TaskStatus.FAILED
        session.commit()
        return detail
    cutover = run_final_cutover(session, run)
    detail = {**progress, "applied": applied, **cutover}
    complete_run(str(run.id), detail, usage)
    return detail


def run_final_cutover(session: Session, run: TaskRun) -> dict:
    """Library cut-over after full coverage: checks, orphan prune, dedup, embeddings.

    Only runs when every item applied. Verifies each enriched recipe carries
    exactly five keywords with no structured-field duplicates (via the stored
    responses), deletes orphan Keyword rows that have neither recipe nor book
    associations — never touching book keywords — enqueues the keyword-dedup
    task through its existing seam, and regenerates missing embeddings.
    """
    from app.tasks.keyword_dedup import enqueue_dedup_keywords

    states = session.scalars(
        select(RecipeEnrichmentState).where(
            RecipeEnrichmentState.status.in_(
                [RecipeEnrichmentStatus.PENDING, RecipeEnrichmentStatus.RUNNING,
                 RecipeEnrichmentStatus.FAILED]
            ),
            RecipeEnrichmentState.schema_version == SCHEMA_VERSION,
        )
    ).all()
    if states:
        raise RuntimeError(f"cut-over blocked: {len(states)} enrichment states not complete")
    orphans = session.scalars(
        select(Keyword).where(~Keyword.recipes.any(), ~Keyword.books.any())
    ).all()
    orphan_count = len(orphans)
    for keyword in orphans:
        session.delete(keyword)
    session.commit()
    dedup_run = None
    try:
        from app.tasks.runs import create_task_run

        dedup_run = create_task_run(session, TaskType.KEYWORD_DEDUP)
        enqueue_dedup_keywords(str(dedup_run.id))
    except Exception:
        logger.warning("Cut-over could not enqueue keyword dedup")
    provider = get_ai_provider(session)
    embedded = backfill_embeddings(session, provider) if provider is not None else 0
    return {
        "cutover_orphan_keywords_removed": orphan_count,
        "cutover_dedup_run_id": str(dedup_run.id) if dedup_run is not None else None,
        "cutover_embeddings_backfilled": embedded,
    }


def _run_usage(session: Session, run: TaskRun) -> Usage:
    items = session.scalars(
        select(RecipeEnrichmentBatchItem)
        .join(RecipeEnrichmentBatch, RecipeEnrichmentBatchItem.batch_id == RecipeEnrichmentBatch.id)
        .where(RecipeEnrichmentBatch.task_run_id == run.id)
    ).all()
    input_tokens = sum((item.usage or {}).get("input_tokens", 0) for item in items)
    output_tokens = sum((item.usage or {}).get("output_tokens", 0) for item in items)
    model = run.model_name or "gemini-2.5-flash"
    return Usage(
        cost_usd=Decimal(str(batch_cost_usd(model, input_tokens, output_tokens))),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def run_backfill_prepare_and_submit(run_id: str) -> dict:
    """Start the backfill: select, prepare stage 1 chunks, submit, go waiting."""
    start_run(run_id)
    with SessionLocal() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        if run is None:
            raise ValueError("enrichment backfill run not found")
        client, model = _batch_client(session)
        run.provider_name = "GEMINI"
        run.model_name = model
        session.commit()
        recipe_ids = select_backfill_recipe_ids(session)
        run.detail = {**run.detail, "selected": len(recipe_ids), **_versions()}
        session.commit()
        prepare_stage_chunks(session, run, recipe_ids, stage="stage1", attempt=1, first_chunk=0)
        max_active = int(run.detail.get("max_active_jobs", BATCH_DEFAULT_MAX_ACTIVE_JOBS))
        submit_prepared(session, run, client, model, max_active=max_active)
        progress = build_progress_detail(session, run)
        polls_done = 0
        countdown = poll_countdown(polls_done)
        progress["polls_done"] = polls_done
        progress["next_poll_in_seconds"] = countdown
        set_waiting(run_id, progress)
        enqueue_poll_backfill(run_id, countdown, polls_done)
        return progress


def poll_backfill(run_id: str, polls_done: int = 0) -> dict:
    """One poll cycle: refresh jobs, ingest, submit next, apply, retry or finish."""
    with SessionLocal() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        if run is None:
            raise ValueError("enrichment backfill run not found")
        if run.status not in (TaskStatus.WAITING, TaskStatus.RUNNING, TaskStatus.QUEUED):
            return dict(run.detail)
        set_running(run_id)
        client, model = _batch_client(session)
        _active, last_error = _refresh_submitted(session, run, client)
        _promote_stage2(session, run)
        max_active = int(run.detail.get("max_active_jobs", BATCH_DEFAULT_MAX_ACTIVE_JOBS))
        submit_prepared(session, run, client, model, max_active=max_active)
        apply_counts = apply_ready_stage2(session, run, model)
        built = build_retry_chunks(session, run)
        if built:
            submit_prepared(session, run, client, model, max_active=max_active)
        progress = build_progress_detail(session, run)
        progress["applied_now"] = apply_counts.get("applied", 0)
        if last_error:
            progress["last_provider_error"] = last_error
        if _is_terminal(session, run):
            return _finalise(session, run, _run_usage(session, run))
        polls_done += 1
        countdown = poll_countdown(polls_done)
        progress["polls_done"] = polls_done
        progress["next_poll_in_seconds"] = countdown
        set_waiting(run_id, progress)
        enqueue_poll_backfill(run_id, countdown, polls_done)
        return progress


def enqueue_enrichment_backfill(run_id: str) -> None:
    enrichment_backfill_task.delay(run_id)


def enqueue_poll_backfill(run_id: str, countdown: int, polls_done: int = 0) -> None:
    poll_enrichment_backfill_task.apply_async(args=[run_id, polls_done], countdown=countdown)


@celery_app.task(name="recipe_enrichment_backfill")
def enrichment_backfill_task(run_id: str) -> dict:
    try:
        return run_backfill_prepare_and_submit(run_id)
    except Exception as exc:
        fail_run(run_id, exc)
        raise


@celery_app.task(name="poll_recipe_enrichment_backfill")
def poll_enrichment_backfill_task(run_id: str, polls_done: int = 0) -> dict:
    try:
        return poll_backfill(run_id, polls_done)
    except Exception as exc:
        fail_run(run_id, exc)
        raise


def delete_orphan_keywords(session: Session) -> int:
    """Delete Keyword rows with neither recipe nor book associations. Returns count."""
    orphans = session.scalars(
        select(Keyword).where(~Keyword.recipes.any(), ~Keyword.books.any())
    ).all()
    for keyword in orphans:
        session.delete(keyword)
    session.commit()
    return len(orphans)


def _clear_recipe_enrichment_data(session: Session, recipe_id: uuid.UUID) -> None:
    """Test helper: reset one recipe's enrichment artefacts for replay tests."""
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        return
    if recipe.enrichment_state is not None:
        session.delete(recipe.enrichment_state)
    session.execute(
        delete(IngredientLine).where(IngredientLine.recipe_id == recipe_id)
    )
    session.commit()
