from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.db import SessionDep
from app.models.ai_config import AITaskAssignment
from app.models.enums import AIProvider
from app.schemas.config import (
    ConfigRead,
    ConfigUpdate,
)
from app.services.ai import (
    add_provider_models,
    all_recommendations,
    ensure_provider_configs,
    get_config,
    remove_provider_models,
    set_provider_key,
    set_provider_order,
    set_task_assignment,
)

router = APIRouter(tags=["config"])


def _read(session: SessionDep) -> ConfigRead:
    providers = ensure_provider_configs(session)
    assignments = list(
        session.scalars(
            select(AITaskAssignment).order_by(
                AITaskAssignment.role, AITaskAssignment.position
            )
        ).all()
    )
    return ConfigRead.from_state(
        providers,
        assignments,
        all_recommendations(),
        get_config(session).extraction_rate_limit_per_minute,
    )


@router.get("/config", response_model=ConfigRead)
def read_config(session: SessionDep) -> ConfigRead:
    """The current AI configuration. API keys are never returned — only whether one
    is stored per provider. Reading previews the seeded provider rows without
    persisting them (the session isn't committed)."""
    return _read(session)


@router.patch("/config", response_model=ConfigRead)
def update_config(payload: ConfigUpdate, session: SessionDep) -> ConfigRead:
    """Apply a partial configuration update: provider keys/orders/model lists, then
    the display order, then task assignments (validated against the updated lists).
    Only the sections present in the body are touched. Validation failures are 422."""
    data = payload.model_dump(exclude_unset=True)

    try:
        if "provider_configs" in data:
            seen: set[str] = set()
            for entry in payload.provider_configs or []:
                if entry.provider in seen:
                    raise ValueError(f"duplicate provider entry: {entry.provider.value}")
                seen.add(entry.provider)
                if entry.provider == AIProvider.STUB:
                    raise ValueError("the offline stub is not configurable")
                fields = entry.model_dump(exclude_unset=True)
                if "api_key" in fields:
                    set_provider_key(session, entry.provider, entry.api_key)
                if entry.add_models:
                    add_provider_models(session, entry.provider, entry.add_models)
                if entry.remove_models:
                    remove_provider_models(session, entry.provider, entry.remove_models)
        if "provider_order" in data and payload.provider_order is not None:
            if any(provider == AIProvider.STUB for provider in payload.provider_order):
                raise ValueError("the offline stub is not configurable")
            set_provider_order(session, list(payload.provider_order))
        if "task_assignments" in data:
            seen_roles: set[str] = set()
            for update in payload.task_assignments or []:
                if update.role in seen_roles:
                    raise ValueError(f"duplicate task entry: {update.role.value}")
                seen_roles.add(update.role)
                set_task_assignment(
                    session,
                    update.role,
                    [(entry.provider, entry.model_id) for entry in update.entries],
                )
        if "extraction_rate_limit_per_minute" in data:
            config = get_config(session)
            config.extraction_rate_limit_per_minute = data["extraction_rate_limit_per_minute"]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    session.commit()
    return _read(session)
