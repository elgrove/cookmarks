"""Run the extraction pipeline per task and score the output.

For each task (a pipeline role), every candidate model is pinned to *just that task*
via ``Config.model_overrides`` — other roles stay at the provider default — and run
against the books that exercise the task. The blocks task forces block extraction,
skipping the image-match check that can misjudge a book. A score difference is thus
attributable to that one task's model. Rich per-book artefacts land under ``runs/``;
one flat row per (run, task, model, book) is appended to the ledger.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.covers import epub_path
from app.models.book import Book
from app.models.enums import TaskStatus, TaskType
from app.models.task_run import TaskRun
from app.services.ai import ModelRole
from app.services.extraction.graph import get_extraction_graph
from evals.config import LEDGER_PATH, RUNS_DIR, EvalConfig, git_sha
from evals.data import from_predicted, load_gold
from evals.environment import bind_pipeline, build_eval_database, resolve_api_key, set_provider
from evals.matching import match_recipes
from evals.metrics import aggregate, score_pair
from evals.models import BookResult, BookSpec, CandidateModel, LedgerRecord, RecipeScore

logger = logging.getLogger(__name__)

_RESUME_ANSWER = {True: "has_images", False: "no_images"}


@dataclass
class RunMeta:
    resolved_model: str | None
    extraction_method: str | None
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    duration_s: float


def _run_status(factory: sessionmaker[Session], run_id: uuid.UUID) -> TaskStatus | None:
    with factory() as session:
        run = session.get(TaskRun, run_id)
        return run.status if run else None


def _create_run(
    factory: sessionmaker[Session], book_id: uuid.UUID, provider: str, *, force_block: bool
) -> uuid.UUID:
    with factory() as session:
        run = TaskRun(
            task_type=TaskType.EXTRACTION,
            book_id=book_id,
            provider_name=provider,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(UTC),
            # Pre-setting this makes analyse_epub skip the image-match check and choose
            # block extraction directly (when the book has separate image chapters).
            images_can_be_matched=True if force_block else None,
        )
        session.add(run)
        session.commit()
        return run.id


def _read_run_meta(factory: sessionmaker[Session], run_id: uuid.UUID, duration_s: float) -> RunMeta:
    with factory() as session:
        run = session.get(TaskRun, run_id)
        if run is None:
            raise RuntimeError(f"TaskRun {run_id} vanished")
        return RunMeta(
            resolved_model=run.model_name,
            extraction_method=run.extraction_method.value if run.extraction_method else None,
            cost_usd=float(run.cost_usd) if run.cost_usd is not None else None,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            duration_s=duration_s,
        )


def extract_book(
    factory: sessionmaker[Session], candidate: CandidateModel, book: BookSpec, *, force_block: bool
) -> tuple[list[dict], RunMeta]:
    """Run extraction for one book to completion and return (predicted recipes, meta).
    The candidate model is already pinned via Config; a review pause is auto-answered
    from the book's `has_photos`."""
    with factory() as session:
        book_row = session.scalar(select(Book).where(Book.calibre_id == book.calibre_id))
        if book_row is None:
            raise RuntimeError(f"Book {book.calibre_id} not seeded")
        book_id = book_row.id
        epub = str(epub_path(book_row))

    run_id = _create_run(factory, book_id, candidate.provider, force_block=force_block)
    graph = get_extraction_graph()
    gconf = {"configurable": {"thread_id": f"eval_{run_id}"}}

    started = time.monotonic()
    state = {
        "book_id": str(book_id),
        "epub_path": epub,
        "report_id": str(run_id),
        "already_tried": [],
    }
    result = graph.invoke(state, gconf)

    if _run_status(factory, run_id) == TaskStatus.REVIEW:
        answer = _RESUME_ANSWER[book.has_photos]
        logger.info(f"Review pause on {book.slug}: answering {answer!r}")
        graph.update_state(gconf, {"human_response": answer}, as_node="await_human")
        result = graph.invoke(None, gconf)

    duration = time.monotonic() - started
    raw_recipes = list(result.get("raw_recipes", [])) if result else []
    return raw_recipes, _read_run_meta(factory, run_id, duration)


def score_book(
    config: EvalConfig, book: BookSpec, raw_recipes: list[dict], meta: RunMeta
) -> BookResult:
    gold = load_gold(config.gold_path(book))
    predicted = from_predicted(raw_recipes)
    result = match_recipes(gold, predicted, config.fuzzy_threshold)

    recipe_scores: list[RecipeScore] = []
    field_scores = []
    for match in result.matches:
        scores = score_pair(
            gold[match.gold_index], predicted[match.predicted_index], config.weights
        )
        field_scores.append(scores)
        recipe_scores.append(
            RecipeScore(
                gold_name=gold[match.gold_index].name,
                predicted_name=predicted[match.predicted_index].name,
                matched=True,
                match_score=match.score,
                scores=scores,
            )
        )
    for index in result.unmatched_gold:
        recipe_scores.append(
            RecipeScore(
                gold_name=gold[index].name,
                predicted_name=None,
                matched=False,
                match_score=None,
                scores=None,
            )
        )

    return BookResult(
        book=book.slug,
        num_gold=len(gold),
        num_predicted=len(predicted),
        num_matched=len(result.matches),
        precision=result.precision,
        recall=result.recall,
        f1=result.f1,
        metrics=aggregate(field_scores),
        cost_usd=meta.cost_usd,
        input_tokens=meta.input_tokens,
        output_tokens=meta.output_tokens,
        duration_s=meta.duration_s,
        extraction_method=meta.extraction_method,
        recipe_scores=recipe_scores,
        hallucinated=[predicted[j].name for j in result.unmatched_predicted],
    )


def _to_ledger(
    run_id: str,
    timestamp: str,
    git_sha: str | None,
    task: str,
    candidate: CandidateModel,
    br: BookResult,
) -> LedgerRecord:
    return LedgerRecord(
        run_id=run_id,
        timestamp=timestamp,
        git_sha=git_sha,
        task=task,
        model_id=candidate.id,
        provider=candidate.provider,
        model=candidate.model,
        book=br.book,
        num_gold=br.num_gold,
        num_predicted=br.num_predicted,
        num_matched=br.num_matched,
        precision=br.precision,
        recall=br.recall,
        f1=br.f1,
        composite_mean=br.metrics.get("composite_mean", 0.0),
        ingredients_jaccard_mean=br.metrics.get("ingredients_jaccard_mean", 0.0),
        instructions_jaccard_mean=br.metrics.get("instructions_jaccard_mean", 0.0),
        cost_usd=br.cost_usd,
        input_tokens=br.input_tokens,
        output_tokens=br.output_tokens,
        duration_s=br.duration_s,
    )


def _safe(name: str) -> str:
    return name.replace("/", "_").replace(":", "_")


def _write_artefacts(
    run_dir: Path, task: str, model_id: str, br: BookResult, raw_recipes: list[dict]
) -> None:
    book_dir = run_dir / task / _safe(model_id) / br.book
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "scores.json").write_text(br.model_dump_json(indent=2))
    (book_dir / "predicted.json").write_text(json.dumps(raw_recipes, indent=2, ensure_ascii=False))


def _append_ledger(records: list[LedgerRecord]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(record.model_dump_json() + "\n")


def _book_line(task: str, model_id: str, br: BookResult) -> str:
    cost = f"${br.cost_usd:.4f}" if br.cost_usd is not None else "—"
    return (
        f"  {task:22s} {model_id:34s} {br.book:14s} "
        f"F1={br.f1:.3f} comp={br.metrics.get('composite_mean', 0.0):.3f} "
        f"{br.num_matched}/{br.num_gold} matched, {len(br.hallucinated)} extra "
        f"| {cost} {br.duration_s:.0f}s [{br.extraction_method}]"
    )


def run_eval(
    config: EvalConfig,
    task_roles: list[str] | None = None,
    model_ids: list[str] | None = None,
    book_slugs: list[str] | None = None,
) -> tuple[str, list[LedgerRecord]]:
    """Build the eval DB, run the selected tasks x models x books, write artefacts + ledger."""
    tasks = [config.task(r) for r in task_roles] if task_roles else config.tasks

    needed = {slug for task in tasks for slug in task.books if not book_slugs or slug in book_slugs}
    factory = build_eval_database([config.book(s).calibre_id for s in needed])
    bind_pipeline(factory)

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    timestamp = datetime.now(UTC).isoformat()
    sha = git_sha()
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    records: list[LedgerRecord] = []
    for task in tasks:
        ModelRole(task.role)  # validate the role exists before pinning
        force_block = task.role == ModelRole.BLOCKS_OF_FILES.value
        candidates = [c for c in task.models if not model_ids or c.id in model_ids]
        slugs = [s for s in task.books if not book_slugs or s in book_slugs]
        for candidate in candidates:
            try:
                key = resolve_api_key(candidate.provider)
            except RuntimeError as exc:
                logger.warning(f"Skipping {candidate.id}: {exc}")
                continue
            set_provider(factory, candidate.provider, key, {task.role: candidate.model})
            for slug in slugs:
                book = config.book(slug)
                logger.info(f"Running {task.role} / {candidate.id} / {slug}")
                raw_recipes, meta = extract_book(factory, candidate, book, force_block=force_block)
                br = score_book(config, book, raw_recipes, meta)
                _write_artefacts(run_dir, task.role, candidate.id, br, raw_recipes)
                records.append(_to_ledger(run_id, timestamp, sha, task.role, candidate, br))
                print(_book_line(task.role, candidate.id, br))

    _append_ledger(records)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "timestamp": timestamp,
                "git_sha": sha,
                "tasks": [t.role for t in tasks],
            },
            indent=2,
        )
    )
    return run_id, records
