import logging

from fastapi import APIRouter, HTTPException

from app.schemas.ticket import TicketCreate, TicketResult
from app.services.linear import LinearError, create_issue, linear_configured

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tickets", tags=["tickets"])


def _build_description(ticket: TicketCreate) -> str:
    parts = [ticket.description.strip()] if ticket.description.strip() else []
    if ticket.page_url:
        parts.append(f"\n\n---\n**Reported from:** {ticket.page_url}")
    return "\n".join(parts) or "_No description provided._"


@router.get("/enabled")
def tickets_enabled() -> dict[str, bool]:
    """Whether the in-app ticket form should be offered — true only when the Linear
    integration is configured, so the footer link stays hidden otherwise."""
    return {"enabled": linear_configured()}


@router.post("", response_model=TicketResult, status_code=201)
def submit_ticket(ticket: TicketCreate) -> TicketResult:
    """File a ticket as an issue in the Cookmarks Linear project. Returns 503 if Linear
    is unreachable or unconfigured, so the UI can tell the user it didn't go through."""
    title = ticket.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="A ticket title is required")
    try:
        issue = create_issue(title, _build_description(ticket))
    except LinearError as exc:
        logger.warning("Ticket not filed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return TicketResult(identifier=issue["identifier"], url=issue["url"])
