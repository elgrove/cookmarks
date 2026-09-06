"""Gemini Batch recipe-enrichment backfill (MY-175).

Chunk boundaries, keyed correlation, partial errors, bounded retry, staleness,
duplicate/missing rows, non-idempotent create windows, multi-chunk submission,
poll backoff, apply replay, resume selection, pilot gating, usage aggregation
and orphan pruning — plus one end-to-end run against a fake Batch client.
"""

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.enums import (
    AIProvider,
    EnrichmentBatchItemStatus,
    EnrichmentBatchStatus,
    RecipeEnrichmentStatus,
    TaskStatus,
    TaskType,
)
from app.models.ingredient import RecipeIngredient
from app.models.recipe import Keyword, Recipe
from app.models.recipe_enrichment import RecipeEnrichmentState
from app.models.recipe_enrichment_batch import RecipeEnrichmentBatch
from app.models.task_run import TaskRun
from app.services.ai import get_config
from app.services.ai.gemini_batch import RemoteBatchJob
from app.services.ai.stub import StubProvider
from app.services.recipe_enrichment.batch import (
    BATCH_CHUNK_MAX_BYTES,
    BATCH_MAX_ATTEMPTS,
    BATCH_PRICING,
    BATCH_PRICING_SNAPSHOT_VERSION,
    batch_cost_usd,
    correlate_results,
    display_name,
    job_key,
    plan_chunks,
    poll_countdown,
    request_key,
)
from app.services.recipe_enrichment.schema import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    TAXONOMY_VERSION,
    Stage1Response,
    Stage2Response,
)
from app.services.recipe_enrichment.service import source_fingerprint
from app.tasks.enrichment_backfill import (
    _delete_orphan_keywords,
    _recipe_map,
    build_retry_chunks,
    ingest_succeeded_batch,
    poll_backfill,
    prepare_stage_chunks,
    run_backfill_prepare_and_submit,
    select_backfill_recipe_ids,
    submit_prepared,
)
from app.tasks.runs import create_task_run


class FakeBatchClient:
    """Scriptable stand-in for GeminiBatchClient: no network, full call log."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.files: dict[str, str] = {}
        self.jobs: dict[str, dict] = {}
        self.uploads: list[tuple[str, str]] = []
        self.created: list[str] = []
        self.cancelled: list[str] = []
        self._counter = 0

    def upload_jsonl(self, content: str, *, display_name: str) -> str:
        file_id = f"files/fake-{len(self.files)}"
        self.files[file_id] = content
        self.uploads.append((content, display_name))
        return file_id

    def create_job(self, *, model: str, input_file_id: str, display_name: str) -> RemoteBatchJob:
        self._counter += 1
        name = f"batches/fake-{self._counter}"
        self.jobs[name] = {
            "display_name": display_name,
            "state": "JOB_STATE_QUEUED",
            "output": None,
            "error": None,
        }
        self.created.append(name)
        return RemoteBatchJob(name=name, display_name=display_name, state="JOB_STATE_QUEUED")

    def find_by_display_name(self, display_name: str) -> list[RemoteBatchJob]:
        return [
            RemoteBatchJob(
                name=name,
                display_name=job["display_name"],
                state=job["state"],
                error=job["error"],
            )
            for name, job in self.jobs.items()
            if job["display_name"] == display_name
        ]

    def get_job(self, name: str) -> RemoteBatchJob:
        job = self.jobs[name]
        return RemoteBatchJob(
            name=name,
            display_name=job["display_name"],
            state=job["state"],
            error=job["error"],
            output_file_id=job["output"],
        )

    def complete_job(self, name: str, lines: list[str]) -> None:
        file_id = f"files/out-{name.split('/')[-1]}"
        self.files[file_id] = "\n".join(lines)
        self.jobs[name]["state"] = "JOB_STATE_SUCCEEDED"
        self.jobs[name]["output"] = file_id

    def fail_job(self, name: str, error: str = "remote exploded") -> None:
        self.jobs[name]["state"] = "JOB_STATE_FAILED"
        self.jobs[name]["error"] = error

    def download_lines(self, output_file_id: str) -> list[str]:
        return self.files[output_file_id].splitlines()

    def cancel_job(self, name: str) -> None:
        self.cancelled.append(name)


@pytest.fixture
def worker_session(session, monkeypatch):
    """Route every SessionLocal in the backfill path at the test database."""
    factory = sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.tasks.enrichment_backfill.SessionLocal", factory)
    monkeypatch.setattr("app.tasks.runs.SessionLocal", factory)
    return session


@pytest.fixture
def fake_client(monkeypatch):
    fake = FakeBatchClient()
    monkeypatch.setattr(
        "app.tasks.enrichment_backfill.GeminiBatchClient", lambda api_key: fake
    )
    stub = StubProvider("")
    monkeypatch.setattr(
        "app.tasks.enrichment_backfill.get_ai_provider", lambda session: stub
    )
    monkeypatch.setattr(
        "app.tasks.enrichment_backfill.get_recipe_enrichment_providers",
        lambda session: (stub, stub),
    )
    return fake


def _gemini_config(session) -> None:
    config = get_config(session)
    config.ai_provider = AIProvider.GEMINI
    config.api_key = "test-key"
    session.commit()


def _recipe(session, name: str = "Glorp Stew") -> Recipe:
    book_id = session.scalars(select(Recipe.book_id)).first()
    recipe = Recipe(
        book_id=book_id, order=99, name=name, instructions=["Simmer the glorp."]
    )
    recipe.ingredients = [RecipeIngredient(position=0, text="1 glorp of zzxxy")]
    recipe.enrichment_state = RecipeEnrichmentState(status=RecipeEnrichmentStatus.PENDING)
    session.add(recipe)
    session.commit()
    return recipe


def _backfill_run(session, **detail) -> TaskRun:
    run = create_task_run(session, TaskType.RECIPE_ENRICHMENT_BACKFILL, detail=detail or {})
    run.provider_name = "GEMINI"
    run.model_name = "stub-enrichment"
    session.commit()
    return run


def _stage1_line(session, recipe: Recipe, key: str) -> str:
    response = Stage1Response.model_validate(
        {
            "i": [
                {"id": f"{index:02d}", "n": "Glorp"}
                for index, _line in enumerate(recipe.ingredients, start=1)
            ],
        }
    )
    text = response.model_dump_json(by_alias=True)
    return json.dumps(
        {
            "key": key,
            "response": {
                "candidates": [{"content": {"parts": [{"text": text}]}}],
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 20,
                    "cachedContentTokenCount": 10,
                },
            },
        }
    )


def _stage2_line(session, recipe: Recipe, key: str) -> str:
    response = Stage2Response.model_validate(
        {
            "k": ["Glorp"] if recipe.ingredients else [],
            "c": [],
            "m": [{"v": "bake", "p": True}],
            "o": ["main"],
            "w": ["Cosy", "Hearty", "Rustic", "Sharing", "Winter"],
        }
    )
    text = response.model_dump_json(by_alias=True)
    return json.dumps(
        {
            "key": key,
            "response": {
                "candidates": [{"content": {"parts": [{"text": text}]}}],
                "usageMetadata": {"promptTokenCount": 200, "candidatesTokenCount": 30},
            },
        }
    )


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def test_plan_chunks_splits_by_count() -> None:
    groups = plan_chunks([10] * 501)
    assert [len(group) for group in groups] == [500, 1]


def test_plan_chunks_splits_by_bytes() -> None:
    groups = plan_chunks([BATCH_CHUNK_MAX_BYTES - 10, 20, 20])
    assert [len(group) for group in groups] == [1, 2]


def test_batch_pricing_snapshot_is_half_live() -> None:
    from app.services.ai.gemini import _PRICING

    live_in, live_out = _PRICING["gemini-2.5-flash"]
    snap_in, snap_out = BATCH_PRICING["gemini-2.5-flash"]
    assert snap_in == live_in / 2
    assert snap_out == live_out / 2
    assert batch_cost_usd("gemini-2.5-flash", 1_000_000, 1_000_000) == snap_in + snap_out
    assert BATCH_PRICING_SNAPSHOT_VERSION == "2026-08-31"


def test_request_key_carries_recipe_and_fingerprint() -> None:
    recipe_id = str(uuid.uuid4())
    key = request_key(recipe_id, "abcdef1234567890")
    assert key == f"{recipe_id}:abcdef123456"


def test_display_name_carries_run_chunk_and_attempt() -> None:
    run_id = str(uuid.uuid4())
    name = display_name(run_id, 3, "stage1", 2)
    assert run_id.replace("-", "")[:12] in name
    assert "c003" in name and "stage1" in name and "a2" in name
    assert job_key(run_id, 3, "stage1", 2).startswith(run_id)


def test_poll_countdown_grows_to_ceiling() -> None:
    assert poll_countdown(0) == 60
    assert poll_countdown(1) == 120
    assert poll_countdown(2) == 240
    assert poll_countdown(10) == 900


def test_correlate_results_reorders_by_key() -> None:
    lines = [
        json.dumps({"key": "b", "response": {"ok": True}}),
        json.dumps({"key": "a", "response": {"ok": True}}),
    ]
    by_key, problems = correlate_results(lines, {"a", "b"})
    assert sorted(by_key) == ["a", "b"]
    assert problems == []


def test_correlate_results_rejects_unknown_duplicate_missing() -> None:
    lines = [
        json.dumps({"key": "a", "response": {}}),
        json.dumps({"key": "a", "response": {}}),
        json.dumps({"key": "zzz", "response": {}}),
        "not json",
    ]
    by_key, problems = correlate_results(lines, {"a", "b"})
    assert sorted(by_key) == ["a"]
    assert any("duplicate key a" in problem for problem in problems)
    assert any("unknown key zzz" in problem for problem in problems)
    assert any("unparseable" in problem for problem in problems)
    assert any("missing key b" in problem for problem in problems)


# --------------------------------------------------------------------------- #
# Selection + prepare + submit
# --------------------------------------------------------------------------- #


def test_resume_selection_skips_current_recipes(worker_session) -> None:
    session = worker_session
    recipe = _recipe(session)
    assert recipe.id in select_backfill_recipe_ids(session)
    state = recipe.enrichment_state
    assert state is not None
    state.status = RecipeEnrichmentStatus.COMPLETE
    state.source_fingerprint = source_fingerprint(recipe)
    state.schema_version = SCHEMA_VERSION
    state.prompt_version = PROMPT_VERSION
    state.taxonomy_version = TAXONOMY_VERSION
    session.commit()
    assert recipe.id not in select_backfill_recipe_ids(session)


def test_prepare_persists_intent_before_submit(worker_session) -> None:
    session = worker_session
    recipe = _recipe(session)
    run = _backfill_run(session)
    batches = prepare_stage_chunks(
        session, run, [recipe.id], stage="stage1", attempt=1, first_chunk=0
    )
    assert len(batches) == 1
    batch = batches[0]
    assert batch.status is EnrichmentBatchStatus.PREPARING
    assert batch.provider_batch_id is None
    assert len(batch.items) == 1
    assert batch.items[0].status is EnrichmentBatchItemStatus.PENDING


def test_submit_adopts_existing_remote_job(worker_session, fake_client) -> None:
    session = worker_session
    recipe = _recipe(session)
    run = _backfill_run(session)
    prepare_stage_chunks(session, run, [recipe.id], stage="stage1", attempt=1, first_chunk=0)
    batch = session.scalars(select(RecipeEnrichmentBatch)).one()
    # An ambiguous earlier submission left a remote job behind.
    stray = fake_client.create_job(
        model="m", input_file_id="files/old", display_name=batch.display_name
    )
    submitted = submit_prepared(session, run, fake_client, "stub-ingredients", "stub-semantics")
    assert submitted == 1
    session.refresh(batch)
    assert batch.provider_batch_id == stray.name
    assert fake_client.uploads == []


def test_submit_adopts_one_duplicate_and_cancels_extras(worker_session, fake_client) -> None:
    session = worker_session
    recipe = _recipe(session)
    run = _backfill_run(session)
    prepare_stage_chunks(session, run, [recipe.id], stage="stage1", attempt=1, first_chunk=0)
    batch = session.scalars(select(RecipeEnrichmentBatch)).one()
    first = fake_client.create_job(model="m", input_file_id="f1", display_name=batch.display_name)
    second = fake_client.create_job(model="m", input_file_id="f2", display_name=batch.display_name)
    submit_prepared(session, run, fake_client, "stub-ingredients", "stub-semantics")
    session.refresh(batch)
    assert batch.provider_batch_id == first.name
    assert batch.duplicate_ids == [second.name]
    assert fake_client.cancelled == [second.name]


def test_submit_respects_max_active_jobs(worker_session, fake_client, monkeypatch) -> None:
    session = worker_session
    recipes = [_recipe(session, f"R{i}") for i in range(3)]
    run = _backfill_run(session)
    monkeypatch.setattr(
        "app.tasks.enrichment_backfill.plan_chunks", lambda sizes: [[0], [1], [2]]
    )
    prepare_stage_chunks(
        session, run, [recipe.id for recipe in recipes],
        stage="stage1", attempt=1, first_chunk=0,
    )
    submitted = submit_prepared(session, run, fake_client, "stub-ingredients", "stub-semantics", max_active=2)
    assert submitted == 2
    preparing = session.scalar(
        select(RecipeEnrichmentBatch).where(
            RecipeEnrichmentBatch.status == EnrichmentBatchStatus.PREPARING
        )
    )
    assert preparing is not None


# --------------------------------------------------------------------------- #
# Ingest + retry + staleness
# --------------------------------------------------------------------------- #


def test_ingest_partial_provider_errors_keep_good_items(worker_session) -> None:
    session = worker_session
    first, second = _recipe(session, "One"), _recipe(session, "Two")
    run = _backfill_run(session)
    prepare_stage_chunks(
        session, run, [first.id, second.id], stage="stage1", attempt=1, first_chunk=0
    )
    batch = session.scalars(select(RecipeEnrichmentBatch)).one()
    items = {str(item.recipe_id): item for item in batch.items}
    lines = [
        _stage1_line(session, first, items[str(first.id)].request_key),
        json.dumps({"key": items[str(second.id)].request_key, "error": {"message": "throttled"}}),
    ]
    batch.submitted_keys = [items[str(first.id)].request_key, items[str(second.id)].request_key]
    session.commit()
    ingest_succeeded_batch(session, batch, lines)
    assert items[str(first.id)].status is EnrichmentBatchItemStatus.SUCCEEDED
    assert items[str(first.id)].stage1_ingredients == ["Glorp"]
    assert items[str(second.id)].status is EnrichmentBatchItemStatus.FAILED
    assert batch.status is EnrichmentBatchStatus.SUCCEEDED


def test_retry_is_bounded_to_one(worker_session) -> None:
    session = worker_session
    recipe = _recipe(session)
    run = _backfill_run(session)
    prepare_stage_chunks(session, run, [recipe.id], stage="stage1", attempt=1, first_chunk=0)
    batch = session.scalars(select(RecipeEnrichmentBatch)).one()
    item = batch.items[0]
    item.status = EnrichmentBatchItemStatus.FAILED
    item.provider_error = "throttled"
    session.commit()
    assert build_retry_chunks(session, run) == 1
    session.refresh(item)
    assert item.attempt == 2
    assert item.status is EnrichmentBatchItemStatus.PENDING
    # A second failure is terminal: no further retry chunk.
    item.status = EnrichmentBatchItemStatus.FAILED
    session.commit()
    assert build_retry_chunks(session, run) == 0
    assert BATCH_MAX_ATTEMPTS == 2


def test_stale_items_never_retry_in_same_run(worker_session) -> None:
    session = worker_session
    recipe = _recipe(session)
    run = _backfill_run(session)
    prepare_stage_chunks(session, run, [recipe.id], stage="stage1", attempt=1, first_chunk=0)
    batch = session.scalars(select(RecipeEnrichmentBatch)).one()
    batch.items[0].status = EnrichmentBatchItemStatus.STALE
    session.commit()
    assert build_retry_chunks(session, run) == 0


def test_split_moves_every_item_off_the_deleted_batch(worker_session) -> None:
    from app.tasks.enrichment_backfill import _split_oversized

    session = worker_session
    recipe = _recipe(session)
    run = _backfill_run(session)
    prepare_stage_chunks(session, run, [recipe.id], stage="stage1", attempt=1, first_chunk=0)
    batch = session.scalars(select(RecipeEnrichmentBatch)).one()
    rows: dict[str, str] = {
        item.request_key: "x" * (BATCH_CHUNK_MAX_BYTES + 1) for item in batch.items
    }
    batch_id = batch.id
    _split_oversized(session, batch, rows)
    assert session.get(RecipeEnrichmentBatch, batch_id) is None
    survivors = session.scalars(
        select(RecipeEnrichmentBatch).where(RecipeEnrichmentBatch.task_run_id == run.id)
    ).all()
    assert len(survivors) == len(rows)
    assert {item.recipe_id for sibling in survivors for item in sibling.items} == {recipe.id}


def test_empty_selection_finishes_done_without_cutover(
    worker_session, fake_client, monkeypatch
) -> None:
    session = worker_session
    _gemini_config(session)
    monkeypatch.setattr(
        "app.tasks.enrichment_backfill.select_backfill_recipe_ids", lambda session: []
    )
    run = _backfill_run(session, max_active_jobs=4)
    _settle(session)
    progress = run_backfill_prepare_and_submit(str(run.id))
    session.refresh(run)
    assert run.status is TaskStatus.DONE
    assert progress["selected"] == 0
    assert "cutover_orphan_keywords_removed" not in progress
    assert fake_client.created == []


def test_repeated_poll_errors_fail_the_batch(worker_session, fake_client, monkeypatch) -> None:
    from app.tasks.enrichment_backfill import MAX_CONSECUTIVE_POLL_ERRORS, _refresh_submitted

    session = worker_session
    _gemini_config(session)
    _recipe(session)
    run = _backfill_run(session, max_active_jobs=4)
    _settle(session)
    run_backfill_prepare_and_submit(str(run.id))
    batch = session.scalars(select(RecipeEnrichmentBatch)).one()
    assert batch.provider_batch_id is not None
    monkeypatch.setattr(fake_client, "download_lines", lambda file_id: (_ for _ in ()).throw(
        RuntimeError("bad payload")))
    fake_client.complete_job(batch.provider_batch_id, ["{}"])
    for _ in range(MAX_CONSECUTIVE_POLL_ERRORS):
        _settle(session)
        _refresh_submitted(session, run, fake_client)
    session.refresh(batch)
    assert batch.status is EnrichmentBatchStatus.FAILED
    assert "poll failed" in (batch.last_error or "")


# --------------------------------------------------------------------------- #
# End to end against the fake
# --------------------------------------------------------------------------- #


def _complete_stage1(session, fake_client, batch) -> None:
    items = {item.request_key: item for item in batch.items}
    lines = []
    for key in batch.submitted_keys:
        item = items[key]
        recipe = session.get(Recipe, item.recipe_id)
        assert recipe is not None
        lines.append(_stage1_line(session, recipe, key))
    assert batch.provider_batch_id is not None
    fake_client.complete_job(batch.provider_batch_id, lines)


def _complete_stage2(session, fake_client, batch) -> None:
    items = {item.request_key: item for item in batch.items}
    lines = []
    for key in batch.submitted_keys:
        recipe = session.get(Recipe, items[key].recipe_id)
        assert recipe is not None
        lines.append(_stage2_line(session, recipe, key))
    assert batch.provider_batch_id is not None
    fake_client.complete_job(batch.provider_batch_id, lines)


def test_full_backfill_applies_two_waves_and_finishes_done(
    worker_session, fake_client
) -> None:
    session = worker_session
    _gemini_config(session)
    recipe = _recipe(session)
    run = _backfill_run(session, max_active_jobs=4)
    _settle(session)
    run_backfill_prepare_and_submit(str(run.id))

    stage1 = session.scalars(
        select(RecipeEnrichmentBatch).where(RecipeEnrichmentBatch.stage == "stage1")
    ).one()
    assert stage1.status is EnrichmentBatchStatus.SUBMITTED
    _complete_stage1(session, fake_client, stage1)
    _settle(session)
    poll_backfill(str(run.id))

    stage2 = session.scalars(
        select(RecipeEnrichmentBatch).where(RecipeEnrichmentBatch.stage == "stage2")
    ).one()
    assert stage2.status is EnrichmentBatchStatus.SUBMITTED
    _complete_stage2(session, fake_client, stage2)
    _settle(session)
    poll_backfill(str(run.id))

    session.refresh(run)
    assert run.status is TaskStatus.DONE
    session.refresh(recipe)
    assert recipe.enrichment_state is not None
    assert recipe.enrichment_state.status is RecipeEnrichmentStatus.COMPLETE
    assert {keyword.name for keyword in recipe.keywords} == {
        "Cosy", "Hearty", "Rustic", "Sharing", "Winter",
    }
    assert run.detail["applied"] == 4
    assert run.detail["pricing_snapshot_version"] == BATCH_PRICING_SNAPSHOT_VERSION
    assert run.detail["input_tokens"] > 0
    assert run.detail["cost_estimate_usd"] >= 0
    assert "cutover_orphan_keywords_removed" in run.detail


def test_source_change_mid_flight_marks_item_stale(worker_session, fake_client) -> None:
    session = worker_session
    _gemini_config(session)
    recipe = _recipe(session)
    run = _backfill_run(session, max_active_jobs=4)
    _settle(session)
    run_backfill_prepare_and_submit(str(run.id))
    stage1 = session.scalars(
        select(RecipeEnrichmentBatch).where(RecipeEnrichmentBatch.stage == "stage1")
    ).one()
    _complete_stage1(session, fake_client, stage1)
    _settle(session)
    poll_backfill(str(run.id))
    # The cook edits the recipe while the stage 2 job is remote.
    recipe.instructions = ["Completely different instructions."]
    session.commit()
    stage2 = session.scalars(
        select(RecipeEnrichmentBatch).where(RecipeEnrichmentBatch.stage == "stage2")
    ).one()
    _complete_stage2(session, fake_client, stage2)
    _settle(session)
    poll_backfill(str(run.id))
    session.refresh(run)
    assert run.status is TaskStatus.FAILED
    assert run.detail["stale"] == 1
    assert run.detail["applied"] == 3
    assert recipe.enrichment_state is not None
    assert recipe.enrichment_state.status is not RecipeEnrichmentStatus.COMPLETE


def test_terminal_failure_keeps_successes_and_reports_ids(
    worker_session, fake_client
) -> None:
    session = worker_session
    _gemini_config(session)
    _recipe(session, "Good")
    bad = _recipe(session, "Bad")
    run = _backfill_run(session, max_active_jobs=4)
    _settle(session)
    run_backfill_prepare_and_submit(str(run.id))
    stage1 = session.scalars(
        select(RecipeEnrichmentBatch).where(RecipeEnrichmentBatch.stage == "stage1")
    ).one()
    recipes = _recipe_map(session, [item.recipe_id for item in stage1.items])
    lines = []
    for item in stage1.items:
        if item.recipe_id == bad.id:
            lines.append(
                json.dumps({"key": item.request_key, "error": {"message": "arrant nonsense"}})
            )
        else:
            lines.append(_stage1_line(session, recipes[item.recipe_id], item.request_key))
    assert stage1.provider_batch_id is not None
    fake_client.complete_job(stage1.provider_batch_id, lines)
    _settle(session)
    poll_backfill(str(run.id))  # stage1 ingested; bad queued for retry
    retry = session.scalars(
        select(RecipeEnrichmentBatch).where(
            RecipeEnrichmentBatch.stage == "stage1",
            RecipeEnrichmentBatch.attempt == 2,
        )
    ).one()
    assert retry.status is EnrichmentBatchStatus.SUBMITTED
    assert retry.provider_batch_id is not None
    stage2 = session.scalars(
        select(RecipeEnrichmentBatch).where(
            RecipeEnrichmentBatch.stage == "stage2",
            RecipeEnrichmentBatch.status == EnrichmentBatchStatus.SUBMITTED,
        )
    ).one()
    _complete_stage2(session, fake_client, stage2)
    fake_client.complete_job(
        retry.provider_batch_id,
        [json.dumps({"key": key, "error": {"message": "still nonsense"}})
         for key in retry.submitted_keys],
    )
    _settle(session)
    poll_backfill(str(run.id))
    session.refresh(run)
    assert run.status is TaskStatus.FAILED
    assert run.detail["applied"] == 4
    assert run.detail["terminal_failed"] == 1
    assert any(failure["recipe_id"] == str(bad.id) for failure in run.detail["failures"])


# --------------------------------------------------------------------------- #
# Trigger gating (API)
# --------------------------------------------------------------------------- #


def _settle(session) -> None:
    """End the test session's transaction so worker SessionLocal writes succeed.

    The worker functions open their own sessions on the same SQLite file; an
    open read transaction here holds a SHARED lock that blocks their writes.
    """
    session.commit()
    session.expire_all()


def _done_pilot(session, **overrides) -> TaskRun:
    detail = {
        "seed": 172,
        "recipe_ids": [],
        "provider": "GEMINI->GEMINI",
        "stage1_model": "gemini-2.5-flash-lite",
        "stage2_model": "gemini-2.5-flash",
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
    }
    detail.update(overrides)
    run = TaskRun(
        task_type=TaskType.RECIPE_ENRICHMENT_PILOT,
        status=TaskStatus.DONE,
        detail=detail,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.commit()
    return run


def _gateway_config(session, provider: AIProvider = AIProvider.GEMINI) -> None:
    config = get_config(session)
    config.ai_provider = provider
    config.api_key = "test-key"
    session.commit()


def test_trigger_rejects_non_gemini_provider(client, session) -> None:
    _gateway_config(session, AIProvider.ANTHROPIC)
    pilot = _done_pilot(session)
    response = client.post(
        "/api/tasks/recipe-enrichment-backfill",
        json={"pilot_run_id": str(pilot.id), "confirm_pilot_reviewed": True},
    )
    assert response.status_code == 422


def test_trigger_requires_review_confirmation(client, session) -> None:
    _gateway_config(session)
    pilot = _done_pilot(session)
    response = client.post(
        "/api/tasks/recipe-enrichment-backfill",
        json={"pilot_run_id": str(pilot.id), "confirm_pilot_reviewed": False},
    )
    assert response.status_code == 422


def test_trigger_rejects_version_mismatch(client, session) -> None:
    _gateway_config(session)
    pilot = _done_pilot(session, prompt_version="v0")
    response = client.post(
        "/api/tasks/recipe-enrichment-backfill",
        json={"pilot_run_id": str(pilot.id), "confirm_pilot_reviewed": True},
    )
    assert response.status_code == 422


def test_trigger_rejects_model_mismatch(client, session) -> None:
    _gateway_config(session)
    pilot = _done_pilot(session, stage2_model="gemini-2.5-flash-lite")
    response = client.post(
        "/api/tasks/recipe-enrichment-backfill",
        json={"pilot_run_id": str(pilot.id), "confirm_pilot_reviewed": True},
    )
    assert response.status_code == 422


def test_trigger_queues_and_resume_rejects_while_active(
    client, session, enrichment_backfill_dispatched
) -> None:
    _gateway_config(session)
    pilot = _done_pilot(session)
    response = client.post(
        "/api/tasks/recipe-enrichment-backfill",
        json={"pilot_run_id": str(pilot.id), "confirm_pilot_reviewed": True},
    )
    assert response.status_code == 202
    assert response.json()["task"] == "recipe_enrichment_backfill"
    assert len(enrichment_backfill_dispatched) == 1
    conflict = client.post("/api/tasks/recipe-enrichment-backfill/resume", json={})
    assert conflict.status_code == 409


def test_resume_without_prior_backfill_requires_pilot_approval(
    client, session, enrichment_backfill_dispatched
) -> None:
    _gateway_config(session)
    refused = client.post("/api/tasks/recipe-enrichment-backfill/resume", json={})
    assert refused.status_code == 422
    pilot = _done_pilot(session)
    response = client.post(
        "/api/tasks/recipe-enrichment-backfill/resume",
        json={"pilot_run_id": str(pilot.id), "confirm_pilot_reviewed": True},
    )
    assert response.status_code == 202
    assert len(enrichment_backfill_dispatched) == 1


def test_resume_after_terminal_prior_needs_no_new_approval(
    client, session, enrichment_backfill_dispatched
) -> None:
    _gateway_config(session)
    prior = TaskRun(
        task_type=TaskType.RECIPE_ENRICHMENT_BACKFILL,
        status=TaskStatus.FAILED,
        detail={},
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    session.add(prior)
    session.commit()
    response = client.post("/api/tasks/recipe-enrichment-backfill/resume", json={})
    assert response.status_code == 202
    body = response.json()
    assert body["task"] == "recipe_enrichment_backfill"


# --------------------------------------------------------------------------- #
# Orphan pruning
# --------------------------------------------------------------------------- #


def test_orphan_prune_keeps_recipe_and_book_keywords(worker_session) -> None:
    from app.models.book import Book

    session = worker_session
    recipe = session.scalars(select(Recipe)).first()
    assert recipe is not None
    kept_recipe = Keyword(name="KeptRecipe")
    kept_book = Keyword(name="KeptBook")
    orphan = Keyword(name="OrphanTag")
    recipe.keywords.append(kept_recipe)
    book = session.scalars(select(Book)).first()
    assert book is not None
    book.keywords.append(kept_book)
    session.add(orphan)
    session.commit()
    assert _delete_orphan_keywords(session) == 1
    remaining = {keyword.name for keyword in session.scalars(select(Keyword)).all()}
    assert "OrphanTag" not in remaining
    assert {"KeptRecipe", "KeptBook"} <= remaining
