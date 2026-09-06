from fastapi import APIRouter

from app.db import SessionDep
from app.schemas.config import ConfigRead, ConfigUpdate, ProviderInfo
from app.services.ai import get_config, provider_catalogue

router = APIRouter(tags=["config"])


def _providers() -> list[ProviderInfo]:
    return [ProviderInfo(name=name, requires_api_key=req) for name, req in provider_catalogue()]


@router.get("/config", response_model=ConfigRead)
def read_config(session: SessionDep) -> ConfigRead:
    """The current application settings. The API key is never returned — only whether one
    is set. Reading lazily materialises the singleton with defaults but doesn't persist it
    (the session isn't committed), so a first read reports defaults without a write."""
    return ConfigRead.from_config(get_config(session), _providers())


@router.patch("/config", response_model=ConfigRead)
def update_config(payload: ConfigUpdate, session: SessionDep) -> ConfigRead:
    """Apply a partial settings update. Only fields present in the request body are
    touched; for `api_key`, an empty string or null clears the stored key and a non-empty
    string sets or rotates it. Returns the updated (still key-free) view."""
    config = get_config(session)
    data = payload.model_dump(exclude_unset=True)

    if "ai_provider" in data:
        config.ai_provider = data["ai_provider"]
    if "assistant_provider" in data:
        config.assistant_provider = data["assistant_provider"]
    if "enrichment_stage1_provider" in data:
        config.enrichment_stage1_provider = data["enrichment_stage1_provider"]
    if "enrichment_stage2_provider" in data:
        config.enrichment_stage2_provider = data["enrichment_stage2_provider"]
    if "extraction_rate_limit_per_minute" in data:
        config.extraction_rate_limit_per_minute = data["extraction_rate_limit_per_minute"]
    if "api_key" in data:
        config.api_key = data["api_key"] or None
    if "assistant_api_key" in data:
        config.assistant_api_key = data["assistant_api_key"] or None
    if "enrichment_stage1_api_key" in data:
        config.enrichment_stage1_api_key = data["enrichment_stage1_api_key"] or None
    if "enrichment_stage2_api_key" in data:
        config.enrichment_stage2_api_key = data["enrichment_stage2_api_key"] or None

    session.commit()
    return ConfigRead.from_config(config, _providers())
