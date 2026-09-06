import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.enums import AIProvider, TaskStatus, TaskType
from app.models.task_run import TaskRun
from app.services.ai import get_config


def _book_id(client: TestClient, title: str) -> str:
    return next(b["id"] for b in client.get("/api/books").json() if b["title"] == title)


def _make_run(session: Session, book_id: str, status: TaskStatus, created_at: datetime) -> str:
    """Insert an extraction run in a given status; explicit created_at keeps the
    latest-run ordering deterministic."""
    run = TaskRun(
        task_type=TaskType.EXTRACTION,
        book_id=uuid.UUID(book_id),
        status=status,
        created_at=created_at,
    )
    session.add(run)
    session.commit()
    return str(run.id)


def test_list_runs_empty_when_none(client: TestClient) -> None:
    assert client.get("/api/task-runs").json() == []


def test_list_runs_newest_first_with_book_title(client: TestClient, session: Session) -> None:
    """The index returns every run across all books, newest first, each carrying its
    book's title so the admin view needs no second fetch."""
    owner = _book_id(client, "With Recipes")
    other = _book_id(client, "No Recipes Yet")
    oldest = _make_run(session, owner, TaskStatus.DONE, datetime(2024, 1, 1, tzinfo=UTC))
    middle = _make_run(session, other, TaskStatus.FAILED, datetime(2024, 2, 1, tzinfo=UTC))
    newest = _make_run(session, owner, TaskStatus.REVIEW, datetime(2024, 3, 1, tzinfo=UTC))

    body = client.get("/api/task-runs").json()
    assert [run["id"] for run in body] == [newest, middle, oldest]
    assert [run["status"] for run in body] == ["review", "failed", "done"]

    by_id = {run["id"]: run for run in body}
    assert by_id[oldest]["book_title"] == "With Recipes"
    assert by_id[middle]["book_title"] == "No Recipes Yet"
    # A run paused at REVIEW surfaces its pending question in the index too.
    assert by_id[newest]["pending_question"] is not None


def test_list_runs_supports_optional_limit_and_offset(
    client: TestClient, session: Session
) -> None:
    owner = _book_id(client, "With Recipes")
    oldest = _make_run(session, owner, TaskStatus.DONE, datetime(2024, 1, 1, tzinfo=UTC))
    middle = _make_run(session, owner, TaskStatus.FAILED, datetime(2024, 2, 1, tzinfo=UTC))
    newest = _make_run(session, owner, TaskStatus.REVIEW, datetime(2024, 3, 1, tzinfo=UTC))

    first_page = client.get("/api/task-runs", params={"limit": 2}).json()
    second_page = client.get("/api/task-runs", params={"limit": 2, "offset": 2}).json()

    assert [run["id"] for run in first_page] == [newest, middle]
    assert [run["id"] for run in second_page] == [oldest]


def test_list_runs_rejects_invalid_pagination(client: TestClient) -> None:
    assert client.get("/api/task-runs", params={"limit": 0}).status_code == 422
    assert client.get("/api/task-runs", params={"limit": 201}).status_code == 422
    assert client.get("/api/task-runs", params={"offset": -1}).status_code == 422


def test_trigger_creates_queued_run_and_dispatches(
    client: TestClient, session: Session, dispatched: list[tuple[Any, ...]], seeded_epubs: Path
) -> None:
    config = get_config(session)
    config.ai_provider = AIProvider.STUB
    session.commit()

    book_id = _book_id(client, "No Recipes Yet")
    res = client.post(f"/api/books/{book_id}/extract")

    assert res.status_code == 202
    body = res.json()
    assert body["book_id"] == book_id
    assert body["task_type"] == "extraction"
    assert body["status"] == "queued"
    assert body["provider_name"] == "STUB"
    assert body["detail"]["chapters_processed"] == 0
    assert body["detail"]["total_chapters"] == 0
    assert body["detail"]["recipes_found"] == 0
    assert body["errors"] == []
    assert body["completed_at"] is None

    # Persisted as a real queued row, not just echoed back.
    run = session.scalars(select(TaskRun)).one()
    assert run.status == TaskStatus.QUEUED
    assert str(run.book_id) == book_id

    # Dispatched to the worker exactly once, with (book_id, run_id).
    assert dispatched == [(book_id, body["id"])]


def test_trigger_unknown_book_404(client: TestClient, dispatched: list[tuple[Any, ...]]) -> None:
    res = client.post(f"/api/books/{uuid.uuid4()}/extract")
    assert res.status_code == 404
    assert dispatched == []


def test_re_extract_label_path_keeps_recipes(
    client: TestClient, session: Session, seeded_epubs: Path
) -> None:
    """Triggering a book that already has recipes still queues a run; identity is
    reconciled by the task, so this just confirms the endpoint doesn't gate on count."""
    book_id = _book_id(client, "With Recipes")
    res = client.post(f"/api/books/{book_id}/extract")
    assert res.status_code == 202
    assert res.json()["status"] == "queued"


def test_latest_run_null_when_never_extracted(client: TestClient) -> None:
    book_id = _book_id(client, "No Recipes Yet")
    res = client.get(f"/api/books/{book_id}/extraction")
    assert res.status_code == 200
    assert res.json() is None


def test_latest_run_returns_most_recent(client: TestClient, session: Session) -> None:
    book_id = _book_id(client, "No Recipes Yet")
    _make_run(session, book_id, TaskStatus.DONE, datetime(2024, 1, 1, tzinfo=UTC))
    newest = _make_run(session, book_id, TaskStatus.QUEUED, datetime(2024, 2, 1, tzinfo=UTC))

    body = client.get(f"/api/books/{book_id}/extraction").json()
    assert body["id"] == newest
    assert body["status"] == "queued"
    assert body["pending_question"] is None


def test_latest_run_review_surfaces_pending_question(client: TestClient, session: Session) -> None:
    book_id = _book_id(client, "No Recipes Yet")
    run_id = _make_run(session, book_id, TaskStatus.REVIEW, datetime(2024, 1, 1, tzinfo=UTC))

    body = client.get(f"/api/books/{book_id}/extraction").json()
    assert body["id"] == run_id
    assert body["status"] == "review"
    question = body["pending_question"]
    assert question is not None
    assert question["question"]
    assert [choice["value"] for choice in question["choices"]] == ["has_images", "no_images"]


def test_latest_run_unknown_book_404(client: TestClient) -> None:
    res = client.get(f"/api/books/{uuid.uuid4()}/extraction")
    assert res.status_code == 404


def test_resume_dispatches_and_returns_202(
    client: TestClient, session: Session, resume_dispatched: list[tuple[Any, ...]]
) -> None:
    book_id = _book_id(client, "No Recipes Yet")
    run_id = _make_run(session, book_id, TaskStatus.REVIEW, datetime(2024, 1, 1, tzinfo=UTC))

    res = client.post(
        f"/api/books/{book_id}/extract/{run_id}/resume", json={"response": "has_images"}
    )
    assert res.status_code == 202
    body = res.json()
    assert body["id"] == run_id
    # Still REVIEW on the row until the worker picks it up — fire-and-forget.
    assert body["status"] == "review"
    assert resume_dispatched == [(run_id, "has_images")]


def test_resume_invalid_response_422(
    client: TestClient, session: Session, resume_dispatched: list[tuple[Any, ...]]
) -> None:
    book_id = _book_id(client, "No Recipes Yet")
    run_id = _make_run(session, book_id, TaskStatus.REVIEW, datetime(2024, 1, 1, tzinfo=UTC))

    res = client.post(f"/api/books/{book_id}/extract/{run_id}/resume", json={"response": "maybe"})
    assert res.status_code == 422
    assert resume_dispatched == []


def test_resume_not_in_review_409(
    client: TestClient, session: Session, resume_dispatched: list[tuple[Any, ...]]
) -> None:
    book_id = _book_id(client, "No Recipes Yet")
    run_id = _make_run(session, book_id, TaskStatus.QUEUED, datetime(2024, 1, 1, tzinfo=UTC))

    res = client.post(
        f"/api/books/{book_id}/extract/{run_id}/resume", json={"response": "no_images"}
    )
    assert res.status_code == 409
    assert resume_dispatched == []


def test_resume_unknown_run_404(
    client: TestClient, resume_dispatched: list[tuple[Any, ...]]
) -> None:
    book_id = _book_id(client, "No Recipes Yet")
    res = client.post(
        f"/api/books/{book_id}/extract/{uuid.uuid4()}/resume", json={"response": "has_images"}
    )
    assert res.status_code == 404
    assert resume_dispatched == []


def test_resume_run_from_other_book_404(
    client: TestClient, session: Session, resume_dispatched: list[tuple[Any, ...]]
) -> None:
    """A run belonging to a different book can't be resumed via this book's URL."""
    owner = _book_id(client, "With Recipes")
    other = _book_id(client, "No Recipes Yet")
    run_id = _make_run(session, owner, TaskStatus.REVIEW, datetime(2024, 1, 1, tzinfo=UTC))

    res = client.post(
        f"/api/books/{other}/extract/{run_id}/resume", json={"response": "has_images"}
    )
    assert res.status_code == 404
    assert resume_dispatched == []


def test_a_pdf_only_book_can_be_extracted(
    client: TestClient,
    dispatched: list[tuple[Any, ...]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    book_dir = tmp_path / "Author One" / "With Recipes (1)"
    book_dir.mkdir(parents=True)
    (book_dir / "book.pdf").write_bytes(b"%PDF-1.7 not a real pdf, just bytes")
    monkeypatch.setattr(settings, "calibre_library_path", tmp_path)
    book_id = _book_id(client, "With Recipes")

    res = client.post(f"/api/books/{book_id}/extract")

    assert res.status_code == 202
    assert dispatched == [(book_id, res.json()["id"])]


def test_a_book_without_epub_or_pdf_cannot_be_extracted(
    client: TestClient,
    dispatched: list[tuple[Any, ...]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "calibre_library_path", tmp_path)
    book_id = _book_id(client, "With Recipes")
    res = client.post(f"/api/books/{book_id}/extract")
    assert res.status_code == 422
    assert "EPUB or PDF" in res.json()["detail"]
    assert dispatched == []
