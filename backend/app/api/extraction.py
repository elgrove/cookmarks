import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.db import SessionDep
from app.models.book import Book
from app.models.enums import ExtractionStatus
from app.models.extraction import ExtractionRun
from app.schemas.extraction import ExtractionRunRead, ResumeRequest
from app.services.ai import get_config
from app.services.extraction.review import VALID_HUMAN_RESPONSES
from app.tasks.extraction import enqueue_extract_recipes, enqueue_resume_extraction

router = APIRouter(tags=["extraction"])


@router.post(
    "/books/{book_id}/extract",
    response_model=ExtractionRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_extraction(book_id: uuid.UUID, session: SessionDep) -> ExtractionRunRead:
    """Queue recipe extraction for a book. Creates the run row up front (so a trigger
    is recorded even before a worker picks it up) then dispatches the background task,
    which reconciles recipes by normalised name — favourites and list membership
    survive a re-extraction. Fire-and-forget: returns the queued run, doesn't wait."""
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")

    run = ExtractionRun(
        book_id=book.id,
        provider_name=get_config(session).ai_provider,
        status=ExtractionStatus.QUEUED,
    )
    session.add(run)
    session.commit()

    enqueue_extract_recipes(str(book.id), str(run.id))
    return ExtractionRunRead.from_run(run)


@router.get("/books/{book_id}/extraction", response_model=ExtractionRunRead | None)
def latest_run(book_id: uuid.UUID, session: SessionDep) -> ExtractionRunRead | None:
    """The book's most recent extraction run, or null if it's never been extracted.
    Fetched on the book page so a run paused at REVIEW can surface its pending question
    without a live view — the answer drives it to completion via the resume endpoint."""
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")

    run = session.scalars(
        select(ExtractionRun)
        .where(ExtractionRun.book_id == book_id)
        .order_by(ExtractionRun.created_at.desc())
        .limit(1)
    ).first()
    return ExtractionRunRead.from_run(run) if run is not None else None


@router.post(
    "/books/{book_id}/extract/{run_id}/resume",
    response_model=ExtractionRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_run(
    book_id: uuid.UUID, run_id: uuid.UUID, body: ResumeRequest, session: SessionDep
) -> ExtractionRunRead:
    """Answer the human-in-the-loop question on a paused run and resume it. Validates
    the run belongs to the book, the answer is a choice the graph offers, and the run
    is actually awaiting review; then dispatches the resume to the worker. Fire-and-
    forget: returns the run (still REVIEW until the worker picks it up)."""
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")

    run = session.get(ExtractionRun, run_id)
    if run is None or run.book_id != book_id:
        raise HTTPException(status_code=404, detail="extraction run not found")

    if body.response not in VALID_HUMAN_RESPONSES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid response; expected one of {sorted(VALID_HUMAN_RESPONSES)}",
        )

    if run.status != ExtractionStatus.REVIEW:
        raise HTTPException(status_code=409, detail="this extraction is not awaiting review")

    enqueue_resume_extraction(str(run.id), body.response)
    return ExtractionRunRead.from_run(run)
