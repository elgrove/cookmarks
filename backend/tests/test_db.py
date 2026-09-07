import sqlite3
import threading
import time
from pathlib import Path

from sqlalchemy import create_engine, event, text

from app.db import configure_sqlite_connection


def test_configure_sqlite_connection_pragmas(tmp_path: Path) -> None:
    db_file = tmp_path / "test_pragmas.sqlite3"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _configure(dbapi_conn: sqlite3.Connection, _record: object) -> None:
        configure_sqlite_connection(dbapi_conn, _record)

    with engine.connect() as conn:
        fk = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert fk == 1

        jm = conn.execute(text("PRAGMA journal_mode")).scalar()
        assert str(jm).lower() == "wal"

        bt = conn.execute(text("PRAGMA busy_timeout")).scalar()
        assert bt == 5000

    engine.dispose()


def test_sqlite_concurrent_write_busy_timeout(tmp_path: Path) -> None:
    db_file = tmp_path / "test_busy.sqlite3"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _configure(dbapi_conn: sqlite3.Connection, _record: object) -> None:
        configure_sqlite_connection(dbapi_conn, _record)

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE writes (thread_id INTEGER, created_at REAL)"))

    errors: list[Exception] = []

    def writer(thread_id: int) -> None:
        try:
            with engine.begin() as conn:
                time.sleep(0.02)
                conn.execute(
                    text("INSERT INTO writes VALUES (:thread_id, :created_at)"),
                    {"thread_id": thread_id, "created_at": time.time()},
                )
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors

    with engine.connect() as conn:
        row_count = conn.execute(text("SELECT COUNT(*) FROM writes")).scalar()
        assert row_count == 8

    engine.dispose()
