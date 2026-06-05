import uuid

from fastapi import APIRouter, HTTPException, status

from app.db import SessionDep
from app.models.book import Book
from app.models.enums import ExtractionStatus
from app.models.extraction import ExtractionRun
from app.schemas.extraction import ExtractionRunRead
from app.services.ai import get_config
from app.tasks.extraction import enqueue_extract_recipes

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
