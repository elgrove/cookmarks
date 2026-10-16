"""LangGraph checkpoint hygiene for extraction runs.

The extraction graph persists its state in the ``checkpoints`` and ``writes``
tables of the application SQLite database (via ``SqliteSaver``), keyed by a
deterministic thread id (``run_<run_id>``). Only runs paused for human review
need that state afterwards — a later resume reads it back. Completed and failed
runs can never resume, so their threads are dead weight (about 231 MiB on the
production volume when this was measured).

The ``run_`` thread prefix is reserved for extraction runs: any thread carrying
it with no matching TaskRun row is an orphan the maintenance pass reaps.
Anything else (eval threads, future tools) is left alone.

This module is the single place that maps threads to runs and deletes them.
The worker calls it automatically when a run reaches DONE or FAILED; the
``prune_checkpoints`` script reaps older threads as a maintenance pass.
REVIEW, RUNNING, QUEUED and WAITING threads are always kept.
"""

import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models.enums import TaskStatus
from app.models.task_run import TaskRun

logger = logging.getLogger(__name__)

RUN_THREAD_PREFIX = "run_"

TERMINAL_STATUSES = frozenset({TaskStatus.DONE, TaskStatus.FAILED})

# Mirrors the installed SqliteSaver schema (checkpoints + writes, no blob table).
# Re-check against langgraph's setup() when bumping the dependency.
CHECKPOINT_TABLES = ("checkpoints", "writes")


def thread_id_for_run(run_id: str | uuid.UUID) -> str:
    """Deterministic LangGraph thread id for an extraction run."""
    return f"{RUN_THREAD_PREFIX}{run_id}"


def run_id_from_thread(thread_id: str) -> uuid.UUID | None:
    """Parse the run id back out of a thread id, or None when it is not ours.

    Accepts the hyphenated form the worker writes (``str(run.id)``) as well as
    the unhyphenated form, so threads still match when ids are compared as raw
    database strings.
    """
    if not thread_id.startswith(RUN_THREAD_PREFIX):
        return None
    try:
        return uuid.UUID(thread_id[len(RUN_THREAD_PREFIX):])
    except ValueError:
        return None


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _tables_exist(conn: sqlite3.Connection) -> bool:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('checkpoints', 'writes')"
    ).fetchall()
    return len(rows) == 2


def list_threads(db_path: Path | None = None) -> set[str]:
    """All checkpoint thread ids held in the database. Empty when the tables do
    not exist yet (a fresh database that never ran extraction)."""
    path = db_path or settings.db_path
    if not path.exists():
        return set()
    conn = _connect(path)
    try:
        if not _tables_exist(conn):
            return set()
        threads: set[str] = set()
        for table in CHECKPOINT_TABLES:
            for (thread_id,) in conn.execute(f"SELECT DISTINCT thread_id FROM {table}"):
                threads.add(str(thread_id))
        return threads
    finally:
        conn.close()


def delete_thread(thread_id: str, db_path: Path | None = None) -> tuple[int, int]:
    """Delete one checkpoint thread. Returns (checkpoints, writes) rows removed.

    Never raises for a missing thread, a missing table, or a missing database —
    cleanup is best-effort and must not fail an extraction over a ledger entry.
    """
    path = db_path or settings.db_path
    if not path.exists():
        return (0, 0)
    conn = _connect(path)
    try:
        if not _tables_exist(conn):
            return (0, 0)
        checkpoints = conn.execute(
            "DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,)
        ).rowcount
        writes = conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,)).rowcount
        conn.commit()
        return (checkpoints or 0, writes or 0)
    except sqlite3.Error:
        logger.exception("Checkpoint delete failed for thread %s", thread_id)
        return (0, 0)
    finally:
        conn.close()


def delete_run_checkpoint(
    run_id: str | uuid.UUID, db_path: Path | None = None
) -> tuple[int, int]:
    """Delete the checkpoint thread belonging to one run id."""
    return delete_thread(thread_id_for_run(run_id), db_path=db_path)


def db_size_stats(db_path: Path | None = None) -> dict[str, int]:
    """File size and free-page accounting for the maintenance report."""
    path = db_path or settings.db_path
    size_bytes = path.stat().st_size if path.exists() else 0
    stats: dict[str, int] = {
        "size_bytes": size_bytes,
        "page_size": 0,
        "page_count": 0,
        "freelist_count": 0,
        "free_bytes": 0,
    }
    if not path.exists():
        return stats
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
        stats.update(
            {
                "page_size": page_size,
                "page_count": page_count,
                "freelist_count": freelist,
                "free_bytes": page_size * freelist,
            }
        )
        return stats
    finally:
        conn.close()


@dataclass
class PruneReport:
    """What a prune pass found and removed."""

    threads_found: int = 0
    threads_deleted: int = 0
    checkpoints_deleted: int = 0
    writes_deleted: int = 0
    threads_kept: int = 0
    kept_review: list[str] = field(default_factory=list)
    kept_active: list[str] = field(default_factory=list)
    orphans_deleted: list[str] = field(default_factory=list)
    dry_run: bool = False


def count_thread_rows(thread_id: str, db_path: Path | None = None) -> tuple[int, int]:
    """Count checkpoint/write rows for a thread without deleting them."""
    path = db_path or settings.db_path
    if not path.exists():
        return (0, 0)
    conn = _connect(path)
    try:
        if not _tables_exist(conn):
            return (0, 0)
        checkpoints = conn.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread_id,)
        ).fetchone()[0]
        writes = conn.execute(
            "SELECT COUNT(*) FROM writes WHERE thread_id = ?", (thread_id,)
        ).fetchone()[0]
        return (checkpoints, writes)
    finally:
        conn.close()


def prune_completed_checkpoints(
    session: Session,
    *,
    db_path: Path | None = None,
    dry_run: bool = False,
    older_than_days: int | None = None,
    keep_orphans: bool = False,
) -> PruneReport:
    """Delete checkpoint threads whose runs reached DONE or FAILED.

    REVIEW, RUNNING, QUEUED and WAITING threads are always kept, as are threads
    that do not belong to extraction runs (for example eval threads). Threads
    with no matching TaskRun are orphans — typically runs deleted with their
    book — and are removed unless ``keep_orphans`` is set.

    ``older_than_days`` restricts the pass to runs completed more than that many
    days ago (by ``completed_at``; a terminal run without one counts as old).
    Without it every terminal thread is eligible.
    """
    path = db_path or settings.db_path
    report = PruneReport(dry_run=dry_run)
    threads = sorted(list_threads(path))
    report.threads_found = len(threads)
    if not threads:
        return report

    cutoff: datetime | None = None
    if older_than_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

    for thread_id in threads:
        run_id = run_id_from_thread(thread_id)
        if run_id is None:
            report.threads_kept += 1
            continue
        run = session.get(TaskRun, run_id)
        if run is None:
            if keep_orphans:
                report.threads_kept += 1
                continue
            if dry_run:
                checkpoints, writes = count_thread_rows(thread_id, db_path=path)
                report.checkpoints_deleted += checkpoints
                report.writes_deleted += writes
            else:
                checkpoints, writes = delete_thread(thread_id, db_path=path)
                report.checkpoints_deleted += checkpoints
                report.writes_deleted += writes
            report.threads_deleted += 1
            report.orphans_deleted.append(thread_id)
            continue
        if run.status not in TERMINAL_STATUSES:
            report.threads_kept += 1
            if run.status == TaskStatus.REVIEW:
                report.kept_review.append(thread_id)
            else:
                report.kept_active.append(thread_id)
            continue
        if cutoff is not None and run.completed_at is not None:
            completed = run.completed_at
            if completed.tzinfo is None:
                completed = completed.replace(tzinfo=UTC)
            if completed > cutoff:
                report.threads_kept += 1
                continue
        if dry_run:
            checkpoints, writes = count_thread_rows(thread_id, db_path=path)
            report.checkpoints_deleted += checkpoints
            report.writes_deleted += writes
        else:
            checkpoints, writes = delete_thread(thread_id, db_path=path)
            report.checkpoints_deleted += checkpoints
            report.writes_deleted += writes
        report.threads_deleted += 1

    return report
