"""Durable Gemini Batch recipe-enrichment backfill (MY-175).

Two sequential waves reuse exactly the MY-174 stage prompts, Gemini schemas,
validator and atomic apply service: stage 1 (ingredient structuring) first,
then stage 2 (facet/keyword assignment) whose contexts are built from the
stored stage 1 responses. Each wave chunks recipes at 500 items / 50 MiB of
JSONL and keeps at most four remote jobs active; further chunks wait locally
prepared.

Lifecycle on the parent TaskRun:
queued → running (prepare/submit) → waiting (remote jobs) → running
(download/apply) → done | failed. Failed items get one bounded retry shared
across both waves (a recipe retried at stage 1 spends its retry there);
stale items (source changed mid-flight) wait for a later run. Resume creates
a new parent run selecting only recipes not yet current.
"""

import logging
import uuid
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import SessionLocal
from app.models.base import as_utc
from app.models.enums import (
    EnrichmentBatchItemStatus,
    EnrichmentBatchStatus,
    RecipeEnrichmentStatus,
    TaskStatus,
    TaskType,
)
from app.models.recipe import Keyword, Recipe
from app.models.recipe_enrichment import RecipeEnrichmentState
from app.models.recipe_enrichment_batch import RecipeEnrichmentBatch, RecipeEnrichmentBatchItem
from app.models.task_run import TaskRun
from app.services.ai import (
    AIProvider,
    Usage,
    get_ai_provider,
    get_config,
    get_recipe_enrichment_providers,
)
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
    jsonl_size,
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
    build_stage1_context,
    build_stage2_context,
    deduplicate_ingredient_names,
    ensure_source_fingerprint,
    source_fingerprint,
)
from app.tasks.celery_app import celery_app
from app.tasks.keyword_dedup import enqueue_dedup_keywords
from app.tasks.runs import (
    complete_run,
    create_task_run,
    fail_run,
    fail_with_detail,
    set_running,
    set_waiting,
    start_run,
)

logger = logging.getLogger(__name__)

# Consecutive poll errors on one batch before it fails outright: transient
# download/lookup failures stay on the 15-minute ceiling, a deterministically
# broken payload stops parking the run in WAITING.
MAX_CONSECUTIVE_POLL_ERRORS = 10

# SQLite caps a statement at 999 bind parameters — page large selections.
ID_PAGE_SIZE = 500


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
        .options(selectinload(Recipe.ingredients), selectinload(Recipe.enrichment_state))
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


def _stage_providers(session: Session) -> tuple[AIProvider, AIProvider]:
    """Effective ingredient + semantic providers: explicit per-stage config first,
    falling back to the default provider for stages left unconfigured."""
    default = get_ai_provider(session)
    stage1, stage2 = get_recipe_enrichment_providers(session)
    stage1 = stage1 or default
    stage2 = stage2 or default
    if stage1 is None or stage2 is None:
        raise RuntimeError("No usable AI provider is configured")
    return stage1, stage2


def _batch_client(
    session: Session,
) -> tuple[GeminiBatchClient, AIProvider, AIProvider, str, str]:
    """Build the Batch client plus the stage providers and their model names.

    The Gemini-only gate lives at the API entry points (trigger/resume return
    422 otherwise); the worker trusts the run row it was launched from.
    """
    stage1, stage2 = _stage_providers(session)
    config = get_config(session)
    api_key = config.enrichment_stage1_api_key or config.api_key
    if not api_key:
        raise RuntimeError("Gemini provider is configured without an API key")
    return (
        GeminiBatchClient(api_key),
        stage1,
        stage2,
        stage1.model_for(ModelRole.RECIPE_INGREDIENTS),
        stage2.model_for(ModelRole.RECIPE_SEMANTICS),
    )


def _recipe_map(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, Recipe]:
    found: dict[uuid.UUID, Recipe] = {}
    for offset in range(0, len(ids), ID_PAGE_SIZE):
        page = ids[offset : offset + ID_PAGE_SIZE]
        found.update(
            {
                recipe.id: recipe
                for recipe in session.scalars(
                    select(Recipe)
                    .where(Recipe.id.in_(page))
                    .options(
                        selectinload(Recipe.ingredients),
                        selectinload(Recipe.enrichment_state),
                        selectinload(Recipe.book),
                    )
                )
            }
        )
    return found


def prepare_stage_chunks(
    session: Session,
    run: TaskRun,
    recipe_ids: list[uuid.UUID],
    *,
    stage: str,
    attempt: int,
    first_chunk: int,
) -> list[RecipeEnrichmentBatch]:
    """Persist preparing batch rows + items for the stage 1 wave.

    Only the stage 1 wave is ever prepared here: one PENDING item and one
    JSONL row per recipe, using exactly the MY-174 stage 1 prompt and schema.
    Stage 2 waves are born in `_promote_stage2` from ingested stage 1 results,
    which is what guarantees their contexts carry real AI ingredient data.
    """
    assert stage == "stage1"
    recipes = _recipe_map(session, recipe_ids)
    rows: list[tuple[uuid.UUID, str]] = []
    for recipe_id in recipe_ids:
        recipe = recipes.get(recipe_id)
        if recipe is None:
            continue
        state = _ensure_state(session, recipe)
        ensure_source_fingerprint(recipe)
        key = request_key(str(recipe_id), state.source_fingerprint)
        rows.append((recipe_id, stage1_row(key, build_stage1_context(recipe))))
    sizes = [len(content.encode()) for _, content in rows]
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

    Eligible items hold an ingested stage 1 response (freshly promoted, or
    retry items with stage1_response kept and stage2 stripped). The stored
    names feed the stage 2 context exactly as the live path builds it. Items
    already APPLIED are never rebuilt.
    """
    eligible = [
        item for item in batch.items
        if item.status in (EnrichmentBatchItemStatus.SUCCEEDED, EnrichmentBatchItemStatus.PENDING)
        and "stage2" not in (item.stage1_response or {})
        and (item.stage1_response or {}).get("i") is not None
    ]
    recipes = _recipe_map(session, [item.recipe_id for item in eligible])
    payloads: dict[str, str] = {}
    for item in eligible:
        recipe = recipes.get(item.recipe_id)
        if recipe is None:
            continue
        stored = {key: value for key, value in (item.stage1_response or {}).items()
                  if key != "stage2"}
        names = deduplicate_ingredient_names([
            str(entry.get("n", "")) for entry in stored.get("i", [])
            if isinstance(entry, dict) and entry.get("n")
        ])
        stage2_context = build_stage2_context(session, recipe, names)
        payloads[item.request_key] = stage2_row(item.request_key, stage2_context)
    return payloads


def submit_prepared(
    session: Session,
    run: TaskRun,
    client: GeminiBatchClient,
    stage1_model: str,
    stage2_model: str,
    *,
    max_active: int = BATCH_DEFAULT_MAX_ACTIVE_JOBS,
) -> int:
    """Upload + create remote jobs for preparing batches while a slot is free.

    Each wave submits under its own stage model. Stage 1 rows rebuild
    deterministically from the recipes; stage 2 rows build from ingested stage
    1 data at submit time. Submitted keys persist on the batch so ingest
    correlates exactly what was sent. Returns submitted count.
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
        if jsonl_size(rows) > BATCH_CHUNK_MAX_BYTES or len(rows) > BATCH_CHUNK_MAX_RECIPES:
            _split_oversized(session, batch, rows)
            continue
        # Non-idempotent create: reconcile by display name before creating.
        existing = client.find_by_display_name(batch.display_name)
        wave_model = stage2_model if batch.stage == "stage2" else stage1_model
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
                model=wave_model, input_file_id=input_file_id, display_name=batch.display_name
            )
            batch.provider_batch_id = created.name
        batch.status = EnrichmentBatchStatus.SUBMITTED
        batch.request_count = len(rows)
        batch.submitted_keys = sorted(rows)
        batch.model = wave_model
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
        payloads[item.request_key] = stage1_row(item.request_key, build_stage1_context(recipe))
    session.commit()
    return payloads


def _split_oversized(
    session: Session, batch: RecipeEnrichmentBatch, rows: dict[str, str]
) -> None:
    """Split an oversized preparing batch into smaller preparing batches.

    Every item moves — including ones with no row in this payload (already
    resolved or failed) — so deleting the old batch orphans nothing.
    """
    keys = sorted(rows)
    sizes = [len(rows[key].encode()) + 1 for key in keys]
    groups = plan_chunks(sizes)
    items = {item.request_key: item for item in batch.items}
    leftovers = [item for key, item in items.items() if key not in rows]
    run_id = batch.task_run_id
    base_chunk = len(
        session.scalars(
            select(RecipeEnrichmentBatch).where(
                RecipeEnrichmentBatch.task_run_id == run_id
            )
        ).all()
    )
    siblings = []
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
        siblings.append(sibling)
        for index in group:
            sibling.items.append(items[keys[index]])
    for item in leftovers:
        siblings[0].items.append(item)
    session.delete(batch)
    session.commit()


def _extract_text(response: dict) -> str | None:
    try:
        candidates = response.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(part.get("text", "") or "" for part in parts)
    except (IndexError, AttributeError):
        return None


def _response_usage(response: dict, model: str | None) -> dict:
    meta = response.get("usageMetadata") or {}
    return {
        "model": model,
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
        item = items.get(key)
        if item is None:
            # The recipe was deleted mid-flight and its item row cascaded away:
            # one lost row, not a lost poll cycle.
            logger.warning("Batch %s result for deleted recipe: %s", batch.job_key, key)
            continue
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
        item.usage = _response_usage(response, batch.model)
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
                    line.name for line in parsed.ingredients if line.name
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
    session: Session,
    run: TaskRun,
    stage1_provider: AIProvider,
    stage2_provider: AIProvider,
    stage1_model: str,
    stage2_model: str,
) -> dict[str, int]:
    """Apply every succeeded stage 2 item through the MY-174 atomic service.

    Each recipe commits independently: one bad response never rolls back good
    recipes. A source change since capture marks the item stale for a later run.
    Mirrors the live path's stamping (stage 2 provider, combined model label).
    """
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
            metrics = apply_enrichment(
                session,
                recipe.id,
                response,
                provider=stage2_provider,
                model=f"{stage1_model} -> {stage2_model}",
                task_run_id=run.id,
            )
            session.commit()
            try:
                embed_recipes(session, [recipe], stage2_provider)
                session.commit()
            except Exception:
                logger.warning("Post-apply embedding failed for %s", recipe.id)
                session.rollback()
            item.status = EnrichmentBatchItemStatus.APPLIED
            item.applied_at = datetime.now(UTC)
            item.usage = {**item.usage, **{k: metrics.get(k, 0) for k in (
                "occurrences", "ai_parsed_lines", "headings",
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
            # stage 2 payload so only a fresh response can apply. Appends move
            # the row between the batches' collections, never raw FK writes.
            stored = dict(item.stage1_response or {})
            stored.pop("stage2", None)
            item.stage1_response = stored
            batch.items.append(item)
            item.attempt = attempt
            item.status = EnrichmentBatchItemStatus.PENDING
            item.provider_error = None
            item.provider_code = None
        created += 1
    session.commit()
    return created


def build_progress_detail(session: Session, run: TaskRun) -> dict:
    """Aggregate Task Runs progress: counts, chunks, metrics, usage, cost, poll.

    Counts are per recipe, not per item row: stage 1 items are copied into
    stage 2 sibling batches on promotion, so raw row counts would double-count.
    Each recipe reports its furthest state with APPLIED > FAILED > STALE >
    SUCCEEDED > PENDING precedence; `submitted` counts recipes with a key in
    any submitted payload.
    """
    batches = session.scalars(
        select(RecipeEnrichmentBatch).where(RecipeEnrichmentBatch.task_run_id == run.id)
    ).all()
    items = session.scalars(
        select(RecipeEnrichmentBatchItem)
        .join(RecipeEnrichmentBatch, RecipeEnrichmentBatchItem.batch_id == RecipeEnrichmentBatch.id)
        .where(RecipeEnrichmentBatch.task_run_id == run.id)
    ).all()
    precedence = {
        EnrichmentBatchItemStatus.APPLIED: 4,
        EnrichmentBatchItemStatus.FAILED: 3,
        EnrichmentBatchItemStatus.STALE: 2,
        EnrichmentBatchItemStatus.SUCCEEDED: 1,
        EnrichmentBatchItemStatus.PENDING: 0,
    }
    recipe_state: dict[uuid.UUID, EnrichmentBatchItemStatus] = {}
    for item in items:
        current = recipe_state.get(item.recipe_id)
        if current is None or precedence[item.status] > precedence[current]:
            recipe_state[item.recipe_id] = item.status
    recipe_states = Counter(state.value for state in recipe_state.values())
    key_to_recipe = {item.request_key: item.recipe_id for item in items}
    submitted_recipes = {
        key_to_recipe[key]
        for batch in batches
        for key in (batch.submitted_keys or [])
        if key in key_to_recipe
    }
    chunks_by_state = Counter(batch.status.value for batch in batches)
    attempts = Counter(f"attempt_{batch.attempt}" for batch in batches)
    tokens_by_model: dict[str, Counter[str]] = {}
    line_counts = Counter()
    cuisines: Counter[str] = Counter()
    methods: Counter[str] = Counter()
    courses: Counter[str] = Counter()
    keyword_failures = 0
    for item in items:
        usage = item.usage or {}
        model_usage = tokens_by_model.setdefault(str(usage.get("model") or "unknown"), Counter())
        for key in ("input_tokens", "output_tokens", "cached_tokens"):
            model_usage[key] += int(usage.get(key, 0) or 0)
        for key in (
            "occurrences", "ai_parsed_lines", "headings",
            "ingredients_created", "existing_ingredients", "aliases_created",
        ):
            line_counts[key] += int(usage.get(key, 0) or 0)
        stage2 = (item.stage1_response or {}).get("stage2")
        if isinstance(stage2, dict):
            cuisines.update(str(cuisine) for cuisine in stage2.get("c", []))
            methods.update(
                str(method.get("v", method)) if isinstance(method, dict) else str(method)
                for method in stage2.get("m", [])
            )
            courses.update(str(course) for course in stage2.get("o", []))
        if item.provider_error and "keyword" in item.provider_error.lower():
            keyword_failures += 1
    input_tokens = sum(counter["input_tokens"] for counter in tokens_by_model.values())
    output_tokens = sum(counter["output_tokens"] for counter in tokens_by_model.values())
    cached_tokens = sum(counter["cached_tokens"] for counter in tokens_by_model.values())
    cost = sum(
        batch_cost_usd(model, counter["input_tokens"], counter["output_tokens"])
        for model, counter in tokens_by_model.items()
    )
    started = run.started_at
    elapsed = (datetime.now(UTC) - started.replace(tzinfo=UTC)).total_seconds() if started else 0
    last_error = next(
        (b.last_error for b in sorted(batches, key=lambda b: as_utc(b.created_at), reverse=True)
         if b.last_error),
        next((i.provider_error for i in items if i.provider_error), None),
    )
    return {
        "selected": run.detail.get("selected", 0),
        "prepared": len(recipe_state),
        "submitted": len(submitted_recipes),
        "succeeded": recipe_states.get("succeeded", 0),
        "applied": recipe_states.get("applied", 0),
        "stale": recipe_states.get("stale", 0),
        "terminal_failed": recipe_states.get("failed", 0),
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
        "cost_estimate_usd": round(cost, 4),
        "pricing_snapshot_version": BATCH_PRICING_SNAPSHOT_VERSION,
        "elapsed_seconds": round(elapsed, 1),
        **_versions(),
    }


def _refresh_submitted(
    session: Session, run: TaskRun, client: GeminiBatchClient
) -> tuple[int, str | None]:
    """Poll every submitted batch; ingest completions. Returns (active, error).

    Lookup/download failures are transient up to MAX_CONSECUTIVE_POLL_ERRORS per
    batch (tracked on the run detail); beyond that the batch fails outright so
    a deterministically broken payload cannot park the run in WAITING forever.
    """
    submitted = session.scalars(
        select(RecipeEnrichmentBatch)
        .where(
            RecipeEnrichmentBatch.task_run_id == run.id,
            RecipeEnrichmentBatch.status == EnrichmentBatchStatus.SUBMITTED,
        )
    ).all()
    error_budget: dict[str, int] = dict(run.detail.get("consecutive_poll_errors") or {})
    active = 0
    last_error: str | None = None
    for batch in submitted:
        assert batch.provider_batch_id is not None
        try:
            remote = client.get_job(batch.provider_batch_id)
        except Exception as exc:
            last_error = _note_poll_error(session, run, batch, error_budget, str(exc)[:500])
            if batch.status is EnrichmentBatchStatus.SUBMITTED:
                active += 1
            continue
        if remote.state in ACTIVE_STATES:
            error_budget.pop(batch.job_key, None)
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
                last_error = _note_poll_error(session, run, batch, error_budget, str(exc)[:500])
                if batch.status is EnrichmentBatchStatus.SUBMITTED:
                    active += 1
                continue
            error_budget.pop(batch.job_key, None)
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
    run.detail = {**run.detail, "consecutive_poll_errors": error_budget}
    session.commit()
    return active, last_error


def _note_poll_error(
    session: Session,
    run: TaskRun,
    batch: RecipeEnrichmentBatch,
    error_budget: dict[str, int],
    message: str,
) -> str:
    """Record one transient poll error; fail the batch once the budget is spent."""
    strikes = error_budget.get(batch.job_key, 0) + 1
    if strikes >= MAX_CONSECUTIVE_POLL_ERRORS:
        error_budget.pop(batch.job_key, None)
        error_text = f"poll failed {strikes} times in a row: {message}"
        batch.status = EnrichmentBatchStatus.FAILED
        batch.last_error = error_text
        for item in batch.items:
            if item.status is EnrichmentBatchItemStatus.PENDING:
                item.status = EnrichmentBatchItemStatus.FAILED
                item.provider_error = error_text[:1000]
        session.commit()
        return error_text
    error_budget[batch.job_key] = strikes
    return message


def _promote_stage2(session: Session, run: TaskRun) -> None:
    """Create stage 2 preparing chunks for stage 1 batches that just succeeded.

    A promoted stage 1 batch moves to APPLIED (consumed into the stage 2 wave)
    so each source batch promotes exactly once, however often polls run. The
    sibling inherits the source attempt: the single retry is a budget shared
    across both waves, so a recipe retried at stage 1 has none left at stage 2.
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
    progress = build_progress_detail(session, run)
    applied = progress["applied"]
    failed = progress["terminal_failed"]
    stale = progress["stale"]
    if failed or stale:
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
        detail = {**progress, "failures": failures}
        fail_with_detail(str(run.id), detail, RuntimeError(
            f"backfill finished with {failed} terminal failures and {stale} stale recipes; "
            f"{applied} applied and kept"
        ))
        return detail
    cutover = run_final_cutover(session, run)
    detail = {**progress, **cutover}
    complete_run(str(run.id), detail, usage)
    return detail


def _delete_orphan_keywords(session: Session) -> int:
    """Delete Keyword rows with neither recipe nor book associations.

    Book keyword links are never touched: only rows with no associations at
    all are removed. Returns how many were deleted.
    """
    orphans = session.scalars(
        select(Keyword).where(~Keyword.recipes.any(), ~Keyword.books.any())
    ).all()
    for keyword in orphans:
        session.delete(keyword)
    session.commit()
    return len(orphans)


def run_final_cutover(session: Session, run: TaskRun) -> dict:
    """Library cut-over after full coverage: checks, orphan prune, dedup, embeddings.

    Only runs when every recipe is current for this source fingerprint and
    these versions. Deletes genuinely orphan Keyword rows — never touching
    book keyword associations — enqueues the keyword-dedup task through its
    existing seam, and regenerates missing embeddings.
    """
    recipes = session.scalars(
        select(Recipe).options(
            selectinload(Recipe.ingredients),
            selectinload(Recipe.enrichment_state),
        )
    ).all()
    not_current = [
        recipe.id for recipe in recipes
        if not _is_current(recipe.enrichment_state, recipe)
    ]
    if not_current:
        raise RuntimeError(
            f"cut-over blocked: {len(not_current)} recipes not current for these versions"
        )
    orphan_count = _delete_orphan_keywords(session)
    dedup_run = create_task_run(session, TaskType.KEYWORD_DEDUP)
    try:
        enqueue_dedup_keywords(str(dedup_run.id))
    except Exception:
        # Never leave a QUEUED run no worker will pick up: drop the row and
        # report the dedup as not queued instead.
        logger.warning("Cut-over could not enqueue keyword dedup; dropping its run")
        session.delete(dedup_run)
        session.commit()
        dedup_run = None
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
    tokens: dict[str, Counter[str]] = {}
    for item in items:
        usage = item.usage or {}
        counter = tokens.setdefault(str(usage.get("model") or "unknown"), Counter())
        counter["input_tokens"] += int(usage.get("input_tokens", 0) or 0)
        counter["output_tokens"] += int(usage.get("output_tokens", 0) or 0)
    input_tokens = sum(counter["input_tokens"] for counter in tokens.values())
    output_tokens = sum(counter["output_tokens"] for counter in tokens.values())
    cost = sum(
        batch_cost_usd(model, counter["input_tokens"], counter["output_tokens"])
        for model, counter in tokens.items()
    )
    return Usage(
        cost_usd=Decimal(str(cost)),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def run_backfill_prepare_and_submit(run_id: str) -> dict:
    """Start the backfill: select, prepare stage 1 chunks, submit, go waiting.

    An empty selection finishes DONE immediately: there is nothing to enrich,
    and the cut-over side effects (orphan prune, dedup, embeddings) stay
    reserved for runs that actually applied work.
    """
    start_run(run_id)
    with SessionLocal() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        if run is None:
            raise ValueError("enrichment backfill run not found")
        client, _stage1, _stage2, stage1_model, stage2_model = _batch_client(session)
        run.provider_name = "GEMINI"
        run.model_name = f"{stage1_model} -> {stage2_model}"
        session.commit()
        recipe_ids = select_backfill_recipe_ids(session)
        run.detail = {**run.detail, "selected": len(recipe_ids), **_versions()}
        session.commit()
        if not recipe_ids:
            detail = build_progress_detail(session, run)
            complete_run(str(run.id), {**detail, "note": "nothing outstanding"}, Usage())
            return detail
        prepare_stage_chunks(session, run, recipe_ids, stage="stage1", attempt=1, first_chunk=0)
        max_active = int(run.detail.get("max_active_jobs", BATCH_DEFAULT_MAX_ACTIVE_JOBS))
        submit_prepared(session, run, client, stage1_model, stage2_model, max_active=max_active)
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
        client, stage1_provider, stage2_provider, stage1_model, stage2_model = _batch_client(
            session
        )
        _active, last_error = _refresh_submitted(session, run, client)
        _promote_stage2(session, run)
        max_active = int(run.detail.get("max_active_jobs", BATCH_DEFAULT_MAX_ACTIVE_JOBS))
        submit_prepared(session, run, client, stage1_model, stage2_model, max_active=max_active)
        apply_counts = apply_ready_stage2(
            session, run, stage1_provider, stage2_provider, stage1_model, stage2_model
        )
        built = build_retry_chunks(session, run)
        if built:
            submit_prepared(
                session, run, client, stage1_model, stage2_model, max_active=max_active
            )
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
