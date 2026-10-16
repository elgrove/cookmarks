"""Checkpoint cleanup (MY-211): terminal threads go, REVIEW stays resumable."""

import sqlite3
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings as app_settings
from app.db import configure_sqlite_connection
from app.models import Base, Book
from app.models.enums import AIProvider as AIProviderEnum
from app.models.enums import TaskStatus, TaskType
from app.models.task_run import TaskRun
from app.services.ai import upsert_provider_config
from app.services.extraction import graph
from app.services.extraction.checkpoints import (
    delete_run_checkpoint,
    delete_thread,
    list_threads,
    prune_completed_checkpoints,
    run_id_from_thread,
    thread_id_for_run,
)
from app.services.extraction.graph import get_extraction_graph
from app.tasks.extraction import (
    _mark_run_failed,
    extract_recipes_from_book,
    extract_recipes_from_book_task,
    resume_extraction,
)


def _make_engine(db_file: Path):
    engine = create_engine(
        f"sqlite:///{db_file}", connect_args={"check_same_thread": False, "timeout": 30}
    )

    @event.listens_for(engine, "connect")
    def _configure(dbapi_conn, _record) -> None:
        configure_sqlite_connection(dbapi_conn, _record)

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    engine = _make_engine(tmp_path / "test.sqlite3")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.services.extraction.graph.SessionLocal", factory)
    monkeypatch.setattr("app.tasks.extraction.SessionLocal", factory)
    # `checkpoints` reads the shared config singleton, so patching `db_path` here
    # repoints every helper at the throwaway database.
    monkeypatch.setattr(app_settings, "db_path", tmp_path / "test.sqlite3")
    yield factory
    engine.dispose()
    get_extraction_graph.cache_clear()


def _seed_checkpoint_tables(db_file: Path, thread_ids: list[str]) -> None:
    conn = sqlite3.connect(str(db_file), timeout=30)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            );
            CREATE TABLE IF NOT EXISTS writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            );
            """
        )
        for thread_id in thread_ids:
            checkpoint_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO checkpoints "
                "(thread_id, checkpoint_ns, checkpoint_id) VALUES (?, '', ?)",
                (thread_id, checkpoint_id),
            )
            conn.execute(
                "INSERT INTO writes "
                "(thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel) "
                "VALUES (?, '', ?, 'task', 0, 'channel')",
                (thread_id, checkpoint_id),
            )
        conn.commit()
    finally:
        conn.close()


def _make_run(
    session: Session,
    status: TaskStatus,
    completed_days_ago: int | None = None,
    calibre_id: int | None = None,
) -> TaskRun:
    cid = calibre_id if calibre_id is not None else uuid.uuid4().int % 1_000_000_000
    book = Book(
        calibre_id=cid,
        title="Checkpoint Book",
        author="Author",
        path=f"Author/Checkpoint Book ({cid})",
    )
    session.add(book)
    session.flush()
    run = TaskRun(task_type=TaskType.EXTRACTION, book_id=book.id, status=status)
    if completed_days_ago is not None:
        run.completed_at = datetime.now(UTC) - timedelta(days=completed_days_ago)
    elif status in (TaskStatus.DONE, TaskStatus.FAILED):
        run.completed_at = datetime.now(UTC)
    session.add(run)
    session.commit()
    return run


def test_thread_id_roundtrip() -> None:
    run_id = uuid.uuid4()
    assert run_id_from_thread(thread_id_for_run(run_id)) == run_id
    # The database stores ids unhyphenated; threads written hyphenated still match.
    assert run_id_from_thread(f"run_{str(run_id).replace('-', '')}") == run_id
    assert run_id_from_thread("eval_123") is None
    assert run_id_from_thread("run_not-a-uuid") is None


def test_delete_thread_is_noop_without_tables(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    assert delete_thread("run_whatever", db_path=missing) == (0, 0)
    empty = tmp_path / "empty.sqlite3"
    sqlite3.connect(str(empty)).close()
    assert delete_thread("run_whatever", db_path=empty) == (0, 0)


def test_prune_deletes_terminal_runs_but_keeps_review_and_active(
    db: sessionmaker[Session], tmp_path: Path
) -> None:
    db_file = tmp_path / "test.sqlite3"
    with db() as session:
        done = _make_run(session, TaskStatus.DONE)
        failed = _make_run(session, TaskStatus.FAILED)
        review = _make_run(session, TaskStatus.REVIEW)
        running = _make_run(session, TaskStatus.RUNNING)
        done_id, failed_id = str(done.id), str(review.id)
        _ = failed_id
        threads = [
            thread_id_for_run(done.id),
            thread_id_for_run(failed.id),
            thread_id_for_run(review.id),
            thread_id_for_run(running.id),
            "run_11111111-2222-3333-4444-555555555555",  # orphan, no TaskRun row
            "eval_some-eval-thread",  # not ours, always kept
        ]
        _seed_checkpoint_tables(db_file, threads)

    with db() as session:
        report = prune_completed_checkpoints(session, db_path=db_file)

    assert report.threads_found == 6
    assert report.threads_deleted == 3  # done + failed + orphan
    assert len(report.orphans_deleted) == 1
    assert sorted(report.kept_review) == [thread_id_for_run(review.id)]
    remaining = list_threads(db_file)
    assert thread_id_for_run(done.id) not in remaining
    assert thread_id_for_run(review.id) in remaining
    assert "eval_some-eval-thread" in remaining
    # The resume path still finds the REVIEW thread's run row untouched.
    with db() as session:
        assert session.get(TaskRun, review.id) is not None
        assert session.scalar(select(TaskRun).where(TaskRun.id == review.id)) is not None
    _ = done_id


def test_prune_dry_run_and_filters(
    db: sessionmaker[Session], tmp_path: Path
) -> None:
    db_file = tmp_path / "test.sqlite3"
    with db() as session:
        recent = _make_run(session, TaskStatus.DONE, completed_days_ago=1)
        old = _make_run(session, TaskStatus.DONE, completed_days_ago=30)
        threads = [thread_id_for_run(recent.id), thread_id_for_run(old.id)]
        _seed_checkpoint_tables(db_file, threads)

    with db() as session:
        dry = prune_completed_checkpoints(session, db_path=db_file, dry_run=True)
    assert dry.threads_deleted == 2
    assert len(list_threads(db_file)) == 2

    with db() as session:
        aged = prune_completed_checkpoints(
            session, db_path=db_file, older_than_days=7
        )
    assert aged.threads_deleted == 1
    remaining = list_threads(db_file)
    assert thread_id_for_run(old.id) not in remaining
    assert thread_id_for_run(recent.id) in remaining

    # Orphans are removed by default but survive with keep_orphans.
    _seed_checkpoint_tables(db_file, ["run_11111111-2222-3333-4444-555555555555"])
    with db() as session:
        kept = prune_completed_checkpoints(
            session, db_path=db_file, older_than_days=7, keep_orphans=True
        )
    assert kept.threads_deleted == 0
    assert "run_11111111-2222-3333-4444-555555555555" in list_threads(db_file)
    with db() as session:
        cleared = prune_completed_checkpoints(session, db_path=db_file)
    assert cleared.threads_deleted == 2  # the recent run plus the orphan
    assert len(list_threads(db_file)) == 0


def test_mark_run_failed_drops_its_thread(
    db: sessionmaker[Session], tmp_path: Path
) -> None:
    db_file = tmp_path / "test.sqlite3"
    with db() as session:
        run = _make_run(session, TaskStatus.RUNNING)
        run_id = str(run.id)
        _seed_checkpoint_tables(db_file, [thread_id_for_run(run.id)])

    _mark_run_failed(run_id, RuntimeError("kaboom"))

    with db() as session:
        stored = session.get(TaskRun, uuid.UUID(run_id))
        assert stored is not None
        assert stored.status == TaskStatus.FAILED
    assert thread_id_for_run(uuid.UUID(run_id)) not in list_threads(db_file)


def test_delete_run_checkpoint_removes_thread(
    db: sessionmaker[Session], tmp_path: Path
) -> None:
    db_file = tmp_path / "test.sqlite3"
    run_id = uuid.uuid4()
    _seed_checkpoint_tables(db_file, [thread_id_for_run(run_id)])
    assert thread_id_for_run(run_id) in list_threads(db_file)
    checkpoints, writes = delete_run_checkpoint(run_id, db_path=db_file)
    assert (checkpoints, writes) == (1, 1)
    assert thread_id_for_run(run_id) not in list_threads(db_file)


# --------------------------------------------------------------------------- #
# End-to-end: REVIEW keeps its thread, resume deletes it.
# --------------------------------------------------------------------------- #


_CONTAINERS = {
    "container": """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
    "opf": """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>E2E</dc:title></metadata>
  <manifest>
    <item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="c1"/><itemref idref="c2"/></spine>
</package>""",
}


def _write_epub(path: Path) -> None:
    import zipfile

    chapter = (
        "<html><body><h1>Soup</h1><p>Just water.</p></body></html>",
        "<html><body><h1>Stew</h1><p>Just fire.</p></body></html>",
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml", _CONTAINERS["container"])
        archive.writestr("content.opf", _CONTAINERS["opf"])
        for index, body in enumerate(chapter, start=1):
            archive.writestr(f"chapter{index}.xhtml", body)


@pytest.fixture
def e2e(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[sessionmaker[Session], Path]]:
    db_file = tmp_path / "app.sqlite3"
    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(app_settings, "db_path", db_file)
    monkeypatch.setattr(app_settings, "calibre_library_path", library)

    engine = _make_engine(db_file)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.services.extraction.graph.SessionLocal", factory)
    monkeypatch.setattr("app.tasks.extraction.SessionLocal", factory)
    graph.SessionLocal = factory
    get_extraction_graph.cache_clear()
    yield factory, library
    get_extraction_graph.cache_clear()
    engine.dispose()


def test_completed_run_drops_checkpoint_but_review_keeps_it(
    e2e: tuple[sessionmaker[Session], Path],
) -> None:
    factory, library = e2e
    with factory() as session:
        upsert_provider_config(session, AIProviderEnum.STUB, api_key="test-key")
        session.commit()
        book = Book(
            calibre_id=1,
            title="E2E Cookbook",
            author="Stub Author",
            path="Stub Author/E2E (1)",
        )
        session.add(book)
        session.commit()
        book_id = str(book.id)

    book_dir = library / "Stub Author" / "E2E (1)"
    book_dir.mkdir(parents=True)
    _write_epub(book_dir / "book.epub")

    assert "paused for review" in extract_recipes_from_book(book_id).lower()
    with factory() as session:
        run = session.scalars(select(TaskRun)).one()
        assert run.status == TaskStatus.REVIEW
        run_id = str(run.id)
    # The paused run must stay resumable: its thread survives the pause.
    assert thread_id_for_run(run_id) in list_threads()

    assert "Extracted 2 recipes" in resume_extraction(run_id, "no_images")
    with factory() as session:
        run = session.scalars(select(TaskRun)).one()
        assert run.status == TaskStatus.DONE
    # Completion drops the thread; nothing resumable is left behind.
    assert thread_id_for_run(run_id) not in list_threads()


def test_failed_task_drops_checkpoint(
    e2e: tuple[sessionmaker[Session], Path],
) -> None:
    factory, library = e2e
    with factory() as session:
        upsert_provider_config(session, AIProviderEnum.STUB, api_key="test-key")
        session.commit()
        book = Book(calibre_id=2, title="Corrupt", author="A", path="A/Corrupt (2)")
        session.add(book)
        run = TaskRun(task_type=TaskType.EXTRACTION, book_id=book.id, status=TaskStatus.QUEUED)
        session.add(run)
        session.commit()
        book_id, run_id = str(book.id), str(run.id)

    book_dir = library / "A" / "Corrupt (2)"
    book_dir.mkdir(parents=True)
    (book_dir / "book.epub").write_bytes(b"not a zip file at all")

    with pytest.raises(ValueError, match="missing or corrupt"):
        extract_recipes_from_book_task(book_id, run_id)

    with factory() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        assert run is not None
        assert run.status == TaskStatus.FAILED
    assert thread_id_for_run(run_id) not in list_threads()
