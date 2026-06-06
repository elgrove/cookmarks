import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import AIProvider, ExtractionStatus
from app.models.extraction import ExtractionRun
from app.services.ai import get_config


def _book_id(client: TestClient, title: str) -> str:
    return next(b["id"] for b in client.get("/api/books").json() if b["title"] == title)


def test_trigger_creates_queued_run_and_dispatches(
    client: TestClient, session: Session, dispatched: list[tuple[Any, ...]]
) -> None:
    config = get_config(session)
    config.ai_provider = AIProvider.STUB
    session.commit()

    book_id = _book_id(client, "No Recipes Yet")
    res = client.post(f"/api/books/{book_id}/extract")

    assert res.status_code == 202
    body = res.json()
    assert body["book_id"] == book_id
    assert body["status"] == "queued"
    assert body["provider_name"] == "STUB"
    assert body["chapters_processed"] == 0
    assert body["total_chapters"] == 0
    assert body["recipes_found"] == 0
    assert body["errors"] == []
    assert body["completed_at"] is None

    # Persisted as a real queued row, not just echoed back.
    run = session.scalars(select(ExtractionRun)).one()
    assert run.status == ExtractionStatus.QUEUED
    assert str(run.book_id) == book_id

    # Dispatched to the worker exactly once, with (book_id, run_id).
    assert dispatched == [(book_id, body["id"])]


def test_trigger_unknown_book_404(client: TestClient, dispatched: list[tuple[Any, ...]]) -> None:
    res = client.post(f"/api/books/{uuid.uuid4()}/extract")
    assert res.status_code == 404
    assert dispatched == []


def test_re_extract_label_path_keeps_recipes(client: TestClient, session: Session) -> None:
    """Triggering a book that already has recipes still queues a run; identity is
    reconciled by the task, so this just confirms the endpoint doesn't gate on count."""
    book_id = _book_id(client, "With Recipes")
    res = client.post(f"/api/books/{book_id}/extract")
    assert res.status_code == 202
    assert res.json()["status"] == "queued"
