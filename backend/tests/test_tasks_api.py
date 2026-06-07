"""The admin Tasks tab's on-demand book-keyword trigger: the POST endpoint (eligible
count + dispatch) and the library-wide backfill sweep it runs on the worker."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlite_vec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Book, Config, Recipe
from app.models.enums import AIProvider
from app.tasks.book_keywords import backfill_book_keywords


def test_trigger_default_queues_only_untagged_books(
    client: TestClient, tasks_dispatched: list[tuple[Any, ...]]
) -> None:
    res = client.post("/api/tasks/book-keywords", json={})

    assert res.status_code == 202
    assert res.json() == {"task": "book_keywords", "status": "queued", "queued": 0}
    # The one recipe-bearing book is already tagged, so nothing is eligible by default.
    # Dispatched once, not regenerating.
    assert tasks_dispatched == [(False,)]


def test_trigger_regenerate_queues_every_extracted_book(
    client: TestClient, tasks_dispatched: list[tuple[Any, ...]]
) -> None:
    res = client.post("/api/tasks/book-keywords", json={"regenerate": True})

    assert res.status_code == 202
    # Regenerate counts every book with recipes, tagged or not — here, one.
    assert res.json() == {"task": "book_keywords", "status": "queued", "queued": 1}
    assert tasks_dispatched == [(True,)]


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
    # The sweep opens its own session via app.db.SessionLocal — point it at this DB.
    monkeypatch.setattr("app.tasks.book_keywords.SessionLocal", factory)
    yield factory
    engine.dispose()


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
