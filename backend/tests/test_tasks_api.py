"""The admin Tasks tab's on-demand book-keyword trigger: the POST endpoint (eligible
count + dispatch) and the library-wide backfill sweep it runs on the worker."""

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlite_vec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Book, Config, Recipe, TaskRun
from app.models.enums import AIProvider, TaskStatus, TaskType
from app.tasks.book_keywords import backfill_book_keywords


def _only_run(session: Session) -> TaskRun:
    return session.scalars(select(TaskRun)).one()


def test_trigger_default_queues_only_untagged_books(
    client: TestClient, session: Session, tasks_dispatched: list[tuple[Any, ...]]
) -> None:
    res = client.post("/api/tasks/book-keywords", json={})

    assert res.status_code == 202
    assert res.json() == {"task": "book_keywords", "status": "queued", "queued": 0}
    # A queued TaskRun is recorded and dispatched once with (run_id, regenerate=False).
    run = _only_run(session)
    assert run.task_type == TaskType.BOOK_KEYWORDS
    assert run.status == TaskStatus.QUEUED
    assert tasks_dispatched == [(str(run.id), False)]


def test_trigger_regenerate_queues_every_extracted_book(
    client: TestClient, session: Session, tasks_dispatched: list[tuple[Any, ...]]
) -> None:
    res = client.post("/api/tasks/book-keywords", json={"regenerate": True})

    assert res.status_code == 202
    # Regenerate counts every book with recipes, tagged or not — here, one.
    assert res.json() == {"task": "book_keywords", "status": "queued", "queued": 1}
    run = _only_run(session)
    assert tasks_dispatched == [(str(run.id), True)]


def test_trigger_dedup_reports_vocabulary_size_and_dispatches(
    client: TestClient, session: Session, dedup_dispatched: list[tuple[Any, ...]]
) -> None:
    res = client.post("/api/tasks/dedup-keywords")

    assert res.status_code == 202
    # The seeded vocabulary is Pasta, Quick, Italian — the count the task will analyse.
    assert res.json() == {"task": "keyword_dedup", "status": "queued", "queued": 3}
    run = _only_run(session)
    assert run.task_type == TaskType.KEYWORD_DEDUP
    assert dedup_dispatched == [(str(run.id),)]


def test_trigger_calibre_sync_records_run_and_dispatches(
    client: TestClient, session: Session, calibre_dispatched: list[tuple[Any, ...]]
) -> None:
    res = client.post("/api/tasks/calibre-sync")

    assert res.status_code == 202
    assert res.json() == {"task": "calibre_sync", "status": "queued", "queued": 0}
    run = _only_run(session)
    assert run.task_type == TaskType.CALIBRE_SYNC
    assert run.status == TaskStatus.QUEUED
    assert calibre_dispatched == [(str(run.id),)]


def test_trigger_recipe_enrichment_pilot_records_reproducible_sample(
    client: TestClient, session: Session, enrichment_pilot_dispatched: list[tuple[Any, ...]]
) -> None:
    res = client.post("/api/tasks/recipe-enrichment-pilot")

    assert res.status_code == 202
    run = _only_run(session)
    assert run.task_type == TaskType.RECIPE_ENRICHMENT_PILOT
    assert res.json() == {
        "task": "recipe_enrichment_pilot",
        "status": "queued",
        "queued": len(run.detail["recipe_ids"]),
    }
    assert run.detail["seed"] == 172
    assert run.detail["recipe_ids"]
    assert enrichment_pilot_dispatched == [(str(run.id),)]


# --- The sweep itself, against a throwaway DB the task's SessionLocal is patched onto.


@pytest.fixture
def task_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'tasks.sqlite3'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _configure(dbapi_conn: Any, _record: Any) -> None:
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    # The sweep and the run-lifecycle helpers each open their own session via
    # app.db.SessionLocal — point both at this throwaway DB.
    monkeypatch.setattr("app.tasks.book_keywords.SessionLocal", factory)
    monkeypatch.setattr("app.tasks.runs.SessionLocal", factory)
    monkeypatch.setattr("app.tasks.calibre_sync.SessionLocal", factory)
    yield factory
    engine.dispose()


def _queued_run(factory: sessionmaker[Session], task_type: TaskType) -> str:
    with factory() as session:
        run = TaskRun(task_type=task_type, status=TaskStatus.QUEUED)
        session.add(run)
        session.commit()
        return str(run.id)


def _seed_book(factory: sessionmaker[Session], *, provider: AIProvider | None) -> None:
    with factory() as session:
        if provider is not None:
            session.add(Config(id=1, ai_provider=provider))
        book = Book(calibre_id=1, title="A Book", author="An Author", path="A/Book (1)")
        session.add(book)
        session.flush()
        session.add(Recipe(book_id=book.id, order=0, name="A Recipe"))
        session.commit()


def test_backfill_tags_untagged_books(task_db: sessionmaker[Session]) -> None:
    _seed_book(task_db, provider=AIProvider.STUB)

    assert backfill_book_keywords(regenerate=False) == 1

    with task_db() as session:
        book = session.scalars(select(Book)).one()
        assert {k.name for k in book.keywords}  # tagged from the stub


def test_backfill_is_a_noop_without_a_provider(task_db: sessionmaker[Session]) -> None:
    _seed_book(task_db, provider=None)
    assert backfill_book_keywords(regenerate=True) == 0


# --- The task wrappers drive a queued TaskRun to DONE (with detail) or FAILED.


def test_book_keywords_task_completes_run_with_detail(task_db: sessionmaker[Session]) -> None:
    from app.tasks.book_keywords import backfill_book_keywords_task

    _seed_book(task_db, provider=AIProvider.STUB)
    run_id = _queued_run(task_db, TaskType.BOOK_KEYWORDS)

    detail = backfill_book_keywords_task(run_id, False)

    assert detail == {"books_tagged": 1, "regenerate": False}
    with task_db() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        assert run is not None
        assert run.status == TaskStatus.DONE
        assert run.started_at is not None and run.completed_at is not None
        assert run.detail == {"books_tagged": 1, "regenerate": False}


def test_calibre_sync_task_records_failure(
    task_db: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing Calibre library leaves a FAILED run carrying the error — the headline
    value of tracking every task run."""
    from app.tasks import calibre_sync

    monkeypatch.setattr(calibre_sync.settings, "calibre_library_path", tmp_path / "absent")
    run_id = _queued_run(task_db, TaskType.CALIBRE_SYNC)

    with pytest.raises(FileNotFoundError):
        calibre_sync.calibre_sync_task(run_id)

    with task_db() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        assert run is not None
        assert run.status == TaskStatus.FAILED
        assert run.errors
        assert run.completed_at is not None
