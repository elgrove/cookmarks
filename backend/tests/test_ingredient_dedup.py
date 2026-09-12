"""Canonical ingredient deduplication: vocabulary, merge, and worker lifecycle."""

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base
from app.models.enums import TaskStatus, TaskType
from app.models.ingredient import CanonicalIngredient
from app.models.recipe import Recipe
from app.models.task_run import TaskRun
from app.services.ai import AIProvider, ModelRole, Usage
from app.services.ingredient_dedup import (
    DedupResult,
    _vocabulary_by_usage,
    apply_merges,
    deduplicate_ingredients,
    propose_merges,
)
from app.services.vocabulary_dedup import pre_deduplicate, resolve_chains, select_candidates
from app.tasks.celery_app import celery_app
from app.tasks.ingredient_dedup import (
    _last_cursor,
    dedup_ingredients_task,
    scheduled_dedup_ingredients,
)


class _MapProvider(AIProvider):
    name = "MAP"
    requires_api_key = False
    models: ClassVar[dict[ModelRole, str]] = {ModelRole.INGREDIENT_DEDUP: "map"}

    def __init__(self, mapping: dict[str, str]) -> None:
        super().__init__("")
        self.mapping = mapping

    def _complete(
        self, prompt: str, model: str, *, schema: dict | None = None, temp: float = 0
    ) -> tuple[str, Usage]:
        return json.dumps(self.mapping), Usage()


class _RawProvider(AIProvider):
    name = "RAW"
    requires_api_key = False
    models: ClassVar[dict[ModelRole, str]] = {ModelRole.INGREDIENT_DEDUP: "raw"}

    def __init__(self, response: str) -> None:
        super().__init__("")
        self.response = response

    def _complete(
        self, prompt: str, model: str, *, schema: dict | None = None, temp: float = 0
    ) -> tuple[str, Usage]:
        return self.response, Usage()


def _recipe(session: Session) -> Recipe:
    return session.scalars(select(Recipe).where(Recipe.name == "Recipe 0")).one()


def test_pre_deduplicate_folds_variants_and_existing_plural() -> None:
    survivors, merges = pre_deduplicate(
        ["Wheat Flour Noodle", "wheat  flour noodle", "Egg", "Eggs"]
    )

    assert survivors == ["Wheat Flour Noodle", "Egg"]
    assert merges == {"wheat  flour noodle": "Wheat Flour Noodle", "Eggs": "Egg"}


def test_resolve_chains_drops_cycles() -> None:
    assert resolve_chains({"A": "B", "B": "C", "Loop A": "Loop B", "Loop B": "Loop A"}) == {
        "A": "C",
        "B": "C",
    }


def test_select_candidates_rotates_and_wraps() -> None:
    first, cursor = select_candidates(
        ["Egg", "Flour", "Noodle", "Oil", "Salt"], None, candidate_window=2
    )
    second, cursor = select_candidates(
        ["Egg", "Flour", "Noodle", "Oil", "Salt"], cursor, candidate_window=2
    )
    third, cursor = select_candidates(
        ["Egg", "Flour", "Noodle", "Oil", "Salt"], cursor, candidate_window=2
    )

    assert first == ["Egg", "Flour"]
    assert second == ["Noodle", "Oil"]
    assert third == ["Salt", "Egg"]
    assert cursor == "Egg"


def test_vocabulary_orders_most_referenced_first(session: Session) -> None:
    recipe = _recipe(session)
    noodle = CanonicalIngredient(name="Noodle")
    salt = CanonicalIngredient(name="Salt")
    session.add_all([noodle, salt])
    session.flush()
    recipe.ingredients[0].canonical_ingredient = noodle
    recipe.ingredients[1].canonical_ingredient = noodle
    recipe.ingredients[2].canonical_ingredient = salt
    session.commit()

    assert _vocabulary_by_usage(session) == ["Noodle", "Salt"]


def test_apply_merges_repoints_recipe_facts_and_removes_duplicate(session: Session) -> None:
    recipe = _recipe(session)
    scallion = CanonicalIngredient(name="Scallion")
    spring_onion = CanonicalIngredient(name="Spring onion")
    session.add_all([scallion, spring_onion])
    session.flush()
    recipe.ingredients[0].canonical_ingredient = scallion
    recipe.ingredients[1].canonical_ingredient = scallion
    session.commit()

    assert apply_merges(session, {"Scallion": "Spring onion"}) == 1
    session.commit()
    session.refresh(recipe.ingredients[0])
    session.refresh(recipe.ingredients[1])

    assert recipe.ingredients[0].canonical_ingredient_id == spring_onion.id
    assert recipe.ingredients[1].canonical_ingredient_id == spring_onion.id
    assert session.get(CanonicalIngredient, scallion.id) is None


def test_propose_merges_salvages_truncated_ai_response() -> None:
    provider = _RawProvider('{"scallion": "spring onion", "eggplant": "aub')

    merges, result = propose_merges(provider, ["scallion", "spring onion", "eggplant"])

    assert merges == {"scallion": "spring onion"}
    assert result.ai_truncated is True


def test_deduplicate_ingredients_uses_ai_map(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe = _recipe(session)
    scallion = CanonicalIngredient(name="Scallion")
    spring_onion = CanonicalIngredient(name="Spring onion")
    session.add_all([scallion, spring_onion])
    session.flush()
    recipe.ingredients[0].canonical_ingredient = scallion
    session.commit()
    monkeypatch.setattr(
        "app.services.ingredient_dedup.get_ai_provider",
        lambda _session: _MapProvider({"Scallion": "Spring onion"}),
    )

    result = deduplicate_ingredients(session)
    session.commit()

    assert result.vocabulary_in == 2
    assert result.merges_applied == 1
    assert result.vocabulary_removed == 1
    assert session.get(CanonicalIngredient, scallion.id) is None


def test_stub_ingredient_deduplication_is_a_deterministic_noop() -> None:
    from app.services.ai import StubProvider

    merges, _usage, truncated = StubProvider("").deduplicate_ingredients(
        ["Scallion", "Spring onion"], ["Scallion"]
    )

    assert merges == {"Scallion": "Scallion"}
    assert truncated is False


@pytest.fixture
def task_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite:///{tmp_path / 'ingredient-dedup.sqlite3'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.tasks.ingredient_dedup.SessionLocal", factory)
    monkeypatch.setattr("app.tasks.runs.SessionLocal", factory)
    yield factory
    engine.dispose()


def _done_run(factory: sessionmaker[Session], completed: datetime, cursor: str | None) -> None:
    with factory() as session:
        session.add(
            TaskRun(
                task_type=TaskType.INGREDIENT_DEDUP,
                status=TaskStatus.DONE,
                completed_at=completed,
                detail={"cursor_to": cursor},
            )
        )
        session.commit()


def test_last_cursor_skips_runs_without_a_cursor(task_db: sessionmaker[Session]) -> None:
    _done_run(task_db, datetime(2026, 9, 1, tzinfo=UTC), "Noodle")
    _done_run(task_db, datetime(2026, 9, 2, tzinfo=UTC), None)

    assert _last_cursor() == "Noodle"


def test_worker_completes_tracked_run(
    task_db: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with task_db() as session:
        run = TaskRun(task_type=TaskType.INGREDIENT_DEDUP, status=TaskStatus.QUEUED)
        session.add(run)
        session.commit()
        run_id = str(run.id)
    monkeypatch.setattr(
        "app.tasks.ingredient_dedup.run_dedup",
        lambda _cursor: DedupResult(vocabulary_in=4, merges_applied=1, vocabulary_removed=1),
    )

    detail = dedup_ingredients_task(run_id)

    with task_db() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        assert run is not None
        assert run.status == TaskStatus.DONE
        assert run.detail == detail
        assert detail["ingredients_in"] == 4


def test_scheduled_task_records_and_dispatches_run(
    task_db: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "app.tasks.ingredient_dedup.dedup_ingredients_task.delay",
        lambda run_id: calls.append(run_id),
    )

    scheduled_dedup_ingredients()

    with task_db() as session:
        run = session.scalars(select(TaskRun)).one()
        assert run.task_type == TaskType.INGREDIENT_DEDUP
        assert run.detail == {"scheduled": True}
        assert calls == [str(run.id)]


def test_ingredient_dedup_is_registered_for_weekly_beat() -> None:
    entry = celery_app.conf.beat_schedule["weekly-ingredient-dedup"]

    assert entry["task"] == "scheduled_dedup_ingredients"
