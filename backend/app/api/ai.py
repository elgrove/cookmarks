"""AI readiness: whether AI work can start, for every signed-in user.

Key-free (no secrets in the response) and deliberately not admin-gated — the book
page and the assistant composer need it before they offer AI actions. The full
configuration surface stays admin-only in `app.api.config`.
"""

from fastapi import APIRouter

from app.db import SessionDep
from app.schemas.config import AIReadiness
from app.services.ai import ai_ready, ocr_ready

router = APIRouter(tags=["ai"])


@router.get("/ai/readiness", response_model=AIReadiness)
def read_readiness(session: SessionDep) -> AIReadiness:
    """Extraction and the assistant need any keyed provider; OCR needs Gemini (the
    only OCR-capable provider until MY-190)."""
    ready = ai_ready(session)
    return AIReadiness(
        extraction_available=ready,
        assistant_available=ready,
        ocr_available=ocr_ready(session),
    )
