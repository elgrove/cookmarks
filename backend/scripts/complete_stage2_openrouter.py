"""Complete Stage 2 recipe enrichment using OpenRouter (e.g. Muse Spark 1.3).

Loads recipes whose Stage 1 ingredient extraction succeeded but Stage 2 facet
and keyword assignment remains pending, runs concurrent Stage 2 requests,
validates the responses, and persists them atomically through apply_enrichment.

    cd backend && uv run python -m scripts.complete_stage2_openrouter [--concurrency 20] [--limit N]
"""

import argparse
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.enums import (
    EnrichmentBatchItemStatus,
    RecipeEnrichmentStatus,
    TaskStatus,
    TaskType,
)
from app.models.recipe import Recipe
from app.models.recipe_enrichment import RecipeEnrichmentState
from app.models.recipe_enrichment_batch import RecipeEnrichmentBatchItem
from app.models.task_run import TaskRun
from app.services.ai.base import Usage
from app.services.ai.openrouter import OpenRouterProvider
from app.services.recipe_enrichment.schema import (
    EnrichmentResponse,
    Stage1Response,
)
from app.services.recipe_enrichment.service import (
    apply_enrichment,
    build_stage2_context,
    deduplicate_ingredient_names,
)
from app.services.recipe_facts import upsert_facet_vocabulary
from evals.environment import resolve_api_key

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "meta/muse-spark-1.3-contributor"
DEFAULT_CONCURRENCY = 20


def _find_pending_stage1_items(
    session: Session, limit: int | None = None
) -> list[tuple[uuid.UUID, dict]]:
    """Return (recipe_id, stage1_response_dict) for all pending recipes."""
    subquery = (
        select(RecipeEnrichmentBatchItem)
        .join(
            RecipeEnrichmentState,
            RecipeEnrichmentState.recipe_id == RecipeEnrichmentBatchItem.recipe_id,
        )
        .where(
            RecipeEnrichmentState.status != RecipeEnrichmentStatus.COMPLETE,
            RecipeEnrichmentBatchItem.status == EnrichmentBatchItemStatus.SUCCEEDED,
        )
        .order_by(RecipeEnrichmentBatchItem.created_at.desc())
    )
    items = session.scalars(subquery).all()

    seen: set[uuid.UUID] = set()
    result: list[tuple[uuid.UUID, dict]] = []
    for item in items:
        if item.recipe_id in seen:
            continue
        stage1 = item.stage1_response or {}
        if not stage1.get("i"):
            continue
        seen.add(item.recipe_id)
        result.append((item.recipe_id, stage1))
        if limit and len(result) >= limit:
            break

    return result


def _enrich_single_recipe(
    recipe_id: uuid.UUID,
    stage1_dict: dict,
    provider: OpenRouterProvider,
    model: str,
    task_run_id: uuid.UUID | None,
) -> tuple[bool, Usage, str | None]:
    """Execute Stage 2 for a single recipe in its own database session."""
    try:
        stage1_response = Stage1Response.model_validate(stage1_dict)
        stage1_names = [i.name for i in stage1_response.ingredients if i.name]
        deduped = deduplicate_ingredient_names(stage1_names)

        with SessionLocal() as session:
            recipe = session.get(Recipe, recipe_id)
            if not recipe:
                return False, Usage(), f"recipe {recipe_id} not found"
            context = build_stage2_context(session, recipe, deduped)

        stage2_response, usage = provider.enrich_recipe_stage2(context, model)

        try:
            response = EnrichmentResponse.from_stages(stage1_response, stage2_response)
        except ValueError:
            stage2_response, retry_usage = provider.enrich_recipe_stage2(
                context, model, allow_truncate_keys=True
            )
            usage += retry_usage
            response = EnrichmentResponse.from_stages(stage1_response, stage2_response)

        with SessionLocal() as session:
            apply_enrichment(
                session,
                recipe_id,
                response,
                provider=provider,
                model=f"gemini-2.5-flash-lite->{model}",
                task_run_id=task_run_id,
            )
            session.commit()

        return True, usage, None

    except Exception as exc:
        return False, Usage(), str(exc)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Complete Stage 2 recipe enrichment using OpenRouter."
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Concurrent worker threads (default: {DEFAULT_CONCURRENCY}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum recipes to process (default: all pending).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"OpenRouter model to use (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count pending items and test setup without executing calls.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    api_key = resolve_api_key("OPENROUTER")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY could not be resolved.")
    provider = OpenRouterProvider(api_key=api_key)

    with SessionLocal() as session:
        upsert_facet_vocabulary(session)
        session.commit()

        candidates = _find_pending_stage1_items(session, limit=args.limit)
        total = len(candidates)
        logger.info(f"Found {total} recipe(s) pending Stage 2 enrichment.")

        latest_run = session.scalars(
            select(TaskRun)
            .where(TaskRun.task_type == TaskType.RECIPE_ENRICHMENT_BACKFILL)
            .order_by(TaskRun.created_at.desc())
        ).first()
        task_run_id = latest_run.id if latest_run else None

    if args.dry_run:
        logger.info("Dry run requested; stopping.")
        return

    if not candidates:
        logger.info("No pending recipes to process.")
        return

    started = time.monotonic()
    completed_count = 0
    success_count = 0
    error_count = 0
    total_cost = Decimal("0")
    total_in_tokens = 0
    total_out_tokens = 0
    lock = threading.Lock()

    logger.info(
        f"Starting Stage 2 backfill on {total} recipes using {args.model} "
        f"(concurrency: {args.concurrency})..."
    )

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(
                _enrich_single_recipe,
                recipe_id,
                stage1_dict,
                provider,
                args.model,
                task_run_id,
            ): recipe_id
            for recipe_id, stage1_dict in candidates
        }

        for future in as_completed(futures):
            recipe_id = futures[future]
            ok, usage, err = future.result()

            with lock:
                completed_count += 1
                if ok:
                    success_count += 1
                    if usage.cost_usd:
                        total_cost += usage.cost_usd
                    total_in_tokens += usage.input_tokens or 0
                    total_out_tokens += usage.output_tokens or 0
                else:
                    error_count += 1
                    logger.warning(f"Failed recipe {recipe_id}: {err}")

                if completed_count % 25 == 0 or completed_count == total:
                    elapsed = time.monotonic() - started
                    rate = completed_count / elapsed if elapsed > 0 else 0
                    logger.info(
                        f"[{completed_count}/{total}] "
                        f"ok: {success_count}, failed: {error_count}, "
                        f"cost: ${float(total_cost):.4f}, "
                        f"rate: {rate:.1f} r/s, elapsed: {elapsed:.1f}s"
                    )

    elapsed = time.monotonic() - started
    logger.info(
        f"Stage 2 backfill finished in {elapsed:.1f}s: "
        f"{success_count} succeeded, {error_count} failed. "
        f"Total tokens: in={total_in_tokens}, out={total_out_tokens}. "
        f"Total cost: ${float(total_cost):.4f}."
    )

    if task_run_id:
        with SessionLocal() as session:
            run = session.get(TaskRun, task_run_id)
            if run:
                detail = dict(run.detail or {})
                detail["applied"] = (detail.get("applied") or 0) + success_count
                detail["cost_estimate_usd"] = (
                    detail.get("cost_estimate_usd") or 0.0
                ) + float(total_cost)
                detail["input_tokens"] = (detail.get("input_tokens") or 0) + total_in_tokens
                detail["output_tokens"] = (detail.get("output_tokens") or 0) + total_out_tokens

                pending_remaining = session.scalars(
                    select(RecipeEnrichmentState).where(
                        RecipeEnrichmentState.status != RecipeEnrichmentStatus.COMPLETE
                    )
                ).all()
                if not pending_remaining:
                    run.status = TaskStatus.DONE
                    run.completed_at = datetime.now(UTC)
                    logger.info(f"Marked parent TaskRun {task_run_id} as DONE.")

                run.detail = detail
                session.commit()


if __name__ == "__main__":
    main()
