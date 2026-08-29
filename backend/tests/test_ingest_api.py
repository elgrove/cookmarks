"""The Add-book endpoints: staging a file, and confirming it into a queued run."""

import uuid
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.enums import TaskStatus, TaskType
from app.models.task_run import TaskRun
from app.tasks.ingest import _queue_extraction

EPUB_BYTES = b"PK\x03\x04" + b"\x00" * 64


@pytest.fixture(autouse=True)
def staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "staging"
    monkeypatch.setattr(settings, "ingest_staging_path", path)

    def _fake_cli(args: list[str], *, timeout: int = 0) -> str:
        assert args[0] == "ebook-meta"
        return "Title               : The Curry Guy\nAuthor(s)           : Dan Toombs\n"

    monkeypatch.setattr("app.services.ingest.run_cli", _fake_cli)
    return path


def _upload(client: TestClient, name: str, payload: bytes) -> Any:
    return client.post("/api/ingest/stage/file", files={"file": (name, payload)})


def test_upload_is_staged_with_its_metadata_read(client: TestClient, staging: Path) -> None:
    res = _upload(client, "The_Curry_Guy.epub", EPUB_BYTES)

    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "The Curry Guy"
    assert body["author"] == "Dan Toombs"
    assert body["format"] == "epub"
    assert (staging / f"{body['staging_id']}.epub").exists()


def test_a_pdf_is_staged_as_a_pdf(client: TestClient, staging: Path) -> None:
    res = _upload(client, "Scanned Cookbook.pdf", b"%PDF-1.7" + b"\x00" * 64)

    assert res.status_code == 200
    body = res.json()
    assert body["format"] == "pdf"
    assert (staging / f"{body['staging_id']}.pdf").exists()


def test_a_format_the_library_cannot_hold_is_refused(client: TestClient) -> None:
    res = _upload(client, "notes.docx", b"PK\x03\x04")

    assert res.status_code == 422


def test_a_file_pretending_to_be_a_book_is_refused(client: TestClient) -> None:
    res = _upload(client, "book.epub", b"plain text, not a zip")

    assert res.status_code == 422


def test_an_oversized_upload_is_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ingest_max_bytes", 8)

    res = _upload(client, "big.epub", EPUB_BYTES)

    assert res.status_code == 413


def test_confirm_queues_a_run_carrying_the_whole_job(
    client: TestClient, session: Session, ingest_dispatched: list[tuple[Any, ...]]
) -> None:
    staging_id = _upload(client, "The_Curry_Guy.epub", EPUB_BYTES).json()["staging_id"]

    res = client.post(
        "/api/ingest",
        json={
            "staging_id": staging_id,
            "title": "The Curry Guy",
            "author": "Dan Toombs",
            "extract": True,
        },
    )

    assert res.status_code == 202
    run = session.scalars(select(TaskRun)).one()
    assert run.task_type == TaskType.BOOK_INGEST
    assert run.status == TaskStatus.QUEUED
    # The worker reads the job off its own row; the payload is just the run id.
    assert run.detail == {
        "staging_id": staging_id,
        "title": "The Curry Guy",
        "author": "Dan Toombs",
        "extract": True,
        "replace_book_id": None,
    }
    assert ingest_dispatched == [(str(run.id),)]


def test_confirming_a_swept_file_is_gone_not_queued(
    client: TestClient, session: Session, ingest_dispatched: list[tuple[Any, ...]]
) -> None:
    res = client.post(
        "/api/ingest",
        json={"staging_id": str(uuid.uuid4()), "title": "Ghost", "author": "Nobody"},
    )

    assert res.status_code == 410
    assert session.scalars(select(TaskRun)).all() == []
    assert ingest_dispatched == []


def test_a_blank_title_is_not_a_book(client: TestClient) -> None:
    staging_id = _upload(client, "The_Curry_Guy.epub", EPUB_BYTES).json()["staging_id"]

    res = client.post(
        "/api/ingest", json={"staging_id": staging_id, "title": "", "author": "Dan Toombs"}
    )

    assert res.status_code == 422


def test_extract_after_add_is_queued_for_a_pdf(
    client: TestClient,
    session: Session,
    dispatched: list[tuple[Any, ...]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    book_dir = tmp_path / "Author One" / "With Recipes (1)"
    book_dir.mkdir(parents=True)
    (book_dir / "book.pdf").write_bytes(b"%PDF-1.7 not a real pdf, just bytes")
    monkeypatch.setattr(settings, "calibre_library_path", tmp_path)
    monkeypatch.setattr("app.tasks.ingest.SessionLocal", lambda: nullcontext(session))

    queued, skipped = _queue_extraction(1)

    assert (queued, skipped) == (True, None)
    assert len(dispatched) == 1
