from fastapi import APIRouter, HTTPException, UploadFile, status

from app.db import SessionDep
from app.models.enums import TaskType
from app.schemas.ingest import IngestRequest, StagedBookRead, StageUrlRequest
from app.schemas.task_run import TaskRunRead
from app.services.ingest import (
    FileTooLargeError,
    IngestError,
    StagedFileMissingError,
    UnsupportedFormatError,
    stage_file,
    stage_url,
    staged_path,
)
from app.tasks.ingest import enqueue_ingest_book
from app.tasks.runs import create_task_run

router = APIRouter(prefix="/ingest", tags=["ingest"])


def _staged_response(staged: object) -> StagedBookRead:
    return StagedBookRead.model_validate(staged, from_attributes=True)


def _reject(exc: IngestError) -> HTTPException:
    """Map an ingest failure onto the status the UI reacts to. Everything else is the
    caller's fault in a way they can fix by choosing a different file."""
    if isinstance(exc, FileTooLargeError):
        return HTTPException(status_code=413, detail=str(exc))
    if isinstance(exc, UnsupportedFormatError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, StagedFileMissingError):
        return HTTPException(status_code=410, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@router.post("/stage/file", response_model=StagedBookRead)
def stage_upload(file: UploadFile) -> StagedBookRead:
    """Accept an uploaded book, check it really is one, and read what metadata it
    carries. Nothing reaches the library until the user confirms."""
    try:
        return _staged_response(stage_file(file.filename or "book", file.file))
    except IngestError as exc:
        raise _reject(exc) from exc


@router.post("/stage/url", response_model=StagedBookRead)
def stage_download(body: StageUrlRequest) -> StagedBookRead:
    """Same as an upload, for a direct download link. Admin-only, and the fetch runs
    server-side, so the link is trusted to the extent the admin is."""
    try:
        return _staged_response(stage_url(body.url))
    except IngestError as exc:
        raise _reject(exc) from exc


@router.post("", response_model=TaskRunRead, status_code=status.HTTP_202_ACCEPTED)
def confirm_ingest(body: IngestRequest, session: SessionDep) -> TaskRunRead:
    """Queue the confirmed book for ingestion. Every parameter rides on the run's
    `detail`, so the worker reads the job from its own row. Fire-and-forget: returns the
    queued run, and the page follows it in the runs list."""
    try:
        staged_path(body.staging_id)
    except IngestError as exc:
        raise _reject(exc) from exc

    run = create_task_run(
        session,
        TaskType.BOOK_INGEST,
        detail={
            "staging_id": body.staging_id,
            "title": body.title,
            "author": body.author,
            "extract": body.extract,
            "replace_book_id": str(body.replace_book_id) if body.replace_book_id else None,
        },
    )
    enqueue_ingest_book(str(run.id))
    return TaskRunRead.from_run(run)
