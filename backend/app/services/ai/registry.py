"""Who runs each AI task: provider configurations, task assignments, and resolution.

Administrators store one write-only API key per provider plus the usable model-ID
list in `ai_provider_configs`, and pin tasks to provider-and-model pairs in
`ai_task_assignments` (an ordered list for recipe-ingredient parsing, a single row
for every other task). Everything here resolves a task to a concrete provider
instance and model:

* an explicit assignment wins when its provider is still eligible (key stored,
  model still listed);
* otherwise the task falls back to the first eligible configured provider, in
  saved display order, that recommends a model for the role.

A provider with no stored key is not configured and is never eligible — except a
provider that needs no key (the offline stub), which resolves when explicitly
present. Fresh databases get one row per catalogue provider on first read, so the
settings UI always has something to render.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_config import AIProviderConfig, AITaskAssignment
from app.models.config import Config
from app.models.enums import AIProvider, ModelRole
from app.services.ai.anthropic import AnthropicProvider
from app.services.ai.base import AIProvider as AIProviderInstance
from app.services.ai.gemini import GeminiProvider
from app.services.ai.openrouter import OpenRouterProvider
from app.services.ai.stub import StubProvider

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, type[AIProviderInstance]] = {
    AnthropicProvider.name: AnthropicProvider,
    GeminiProvider.name: GeminiProvider,
    OpenRouterProvider.name: OpenRouterProvider,
    StubProvider.name: StubProvider,
}


def provider_requires_api_key(name: str) -> bool:
    """Whether the named provider needs an API key (unknown providers assumed to)."""
    provider_cls = _PROVIDERS.get(name)
    return provider_cls.requires_api_key if provider_cls else True


def provider_catalogue() -> list[tuple[str, bool]]:
    """The selectable providers as (name, requires_api_key) pairs — what the settings UI
    needs to render its provider rows and decide whether to show the API key field."""
    return [
        (name, cls.requires_api_key)
        for name, cls in _PROVIDERS.items()
        if name != StubProvider.name
    ]


def seed_model_ids(name: str) -> list[str]:
    """The starting usable-model list for a provider: the union of its current
    role recommendations, sorted for a stable display order."""
    provider_cls = _PROVIDERS.get(name)
    if provider_cls is None:
        return []
    return sorted(set(provider_cls.models.values()))


def recommendation(provider_name: str, role: ModelRole) -> str | None:
    """The provider's recommended model for a role, or None when it has none
    (Anthropic and OpenRouter recommend nothing for OCR, for example)."""
    provider_cls = _PROVIDERS.get(provider_name)
    if provider_cls is None:
        return None
    return provider_cls.models.get(role)


def all_recommendations() -> dict[str, dict[str, str]]:
    """Every provider's per-role recommendations ({provider: {role: model}}), so the
    settings UI can show the recommended pair under each task selector."""
    return {
        name: {role.value: model for role, model in cls.models.items()}
        for name, cls in _PROVIDERS.items()
        if name != StubProvider.name
    }


def get_config(session: Session) -> Config:
    """Return the singleton Config row (id=1), creating it if absent."""
    config = session.get(Config, 1)
    if config is None:
        config = Config(id=1)
        session.add(config)
        session.flush()
    return config


def ensure_provider_configs(session: Session) -> list[AIProviderConfig]:
    """One row per catalogue provider, creating missing ones keyless with the seeded
    model list. Flushes without committing — callers own the transaction, so reads
    can preview the rows without persisting them."""
    existing = {row.provider for row in session.scalars(select(AIProviderConfig)).all()}
    order = 0
    for row in session.scalars(select(AIProviderConfig).order_by(AIProviderConfig.display_order)):
        order = max(order, row.display_order + 1)
    for name, _requires_key in provider_catalogue():
        if name in existing:
            continue
        session.add(
            AIProviderConfig(
                provider=AIProvider(name),
                api_key=None,
                display_order=order,
                model_ids=seed_model_ids(name),
            )
        )
        order += 1
    session.flush()
    return list(
        session.scalars(select(AIProviderConfig).order_by(AIProviderConfig.display_order)).all()
    )


def get_provider_config(session: Session, name: str) -> AIProviderConfig | None:
    """The stored configuration for a provider, or None when never configured."""
    provider = AIProvider(name) if name in _PROVIDERS else None
    if provider is None:
        return None
    return session.get(AIProviderConfig, provider)


def _is_eligible(row: AIProviderConfig) -> bool:
    """A stored row counts as configured when it holds a key, or its provider needs
    none (the offline stub)."""
    if row.api_key:
        return True
    provider_cls = _PROVIDERS.get(row.provider.value)
    return provider_cls is not None and not provider_cls.requires_api_key


def _build(row: AIProviderConfig) -> AIProviderInstance:
    provider_cls = _PROVIDERS[row.provider.value]
    return provider_cls(row.api_key or "")


def eligible_providers(session: Session) -> list[AIProviderConfig]:
    """Configured provider rows in saved display order — the task-resolution order."""
    ensure_provider_configs(session)
    rows = session.scalars(
        select(AIProviderConfig).order_by(AIProviderConfig.display_order)
    ).all()
    # A test may register the stub explicitly; the catalogue never seeds it, but an
    # existing row counts all the same.
    extra = session.get(AIProviderConfig, AIProvider.STUB)
    ordered = list(rows)
    if extra is not None and all(row.provider != AIProvider.STUB for row in ordered):
        ordered.append(extra)
    return [row for row in ordered if _is_eligible(row)]


@dataclass(frozen=True)
class ResolvedTask:
    """A task's concrete provider instance and the model it must use."""

    provider: AIProviderInstance
    model: str


def _assignment_model(
    session: Session, role: ModelRole, position: int
) -> tuple[AIProviderConfig, str] | None:
    """An explicit assignment still worth honouring: its provider row exists, is
    eligible, and still lists the model. Anything else falls back to defaults."""
    assignment = session.get(AITaskAssignment, (role, position))
    if assignment is None:
        return None
    row = session.get(AIProviderConfig, assignment.provider)
    if row is None or not _is_eligible(row):
        return None
    if assignment.model_id not in (row.model_ids or []):
        return None
    return row, assignment.model_id


def resolve_task(session: Session, role: ModelRole) -> ResolvedTask | None:
    """Resolve one task to its provider instance and model: the explicit assignment
    when eligible, else the first eligible configured provider (in saved order) with
    a recommendation for the role. None when nothing can run the task."""
    explicit = _assignment_model(session, role, 0)
    if explicit is not None:
        row, model = explicit
        return ResolvedTask(provider=_build(row), model=model)
    for row in eligible_providers(session):
        model = recommendation(row.provider.value, role)
        # Only a model the administrator still lists is usable: a removed
        # recommendation must not silently keep serving the task.
        if model is not None and model in (row.model_ids or []):
            return ResolvedTask(provider=_build(row), model=model)
    return None


def resolve_ingredient_chain(session: Session) -> list[ResolvedTask]:
    """The ordered recipe-ingredient provider/model pairs: the explicit fallback
    list when any entry is still eligible, else the single default resolution."""
    rows = session.scalars(
        select(AITaskAssignment)
        .where(AITaskAssignment.role == ModelRole.RECIPE_INGREDIENTS)
        .order_by(AITaskAssignment.position)
    ).all()
    chain: list[ResolvedTask] = []
    for assignment in rows:
        row = session.get(AIProviderConfig, assignment.provider)
        if row is None or not _is_eligible(row):
            continue
        if assignment.model_id not in (row.model_ids or []):
            continue
        chain.append(ResolvedTask(provider=_build(row), model=assignment.model_id))
    if chain:
        return chain
    default = resolve_task(session, ModelRole.RECIPE_INGREDIENTS)
    return [default] if default is not None else []


def require_task(
    session: Session, role: ModelRole, model_override: str | None = None
) -> tuple[AIProviderInstance, str]:
    """Resolve a task, preferring an explicit model (e.g. a run's pinned model).
    Raises RuntimeError when nothing can run the task — the worker's FAILED path."""
    resolved = resolve_task(session, role)
    if resolved is None:
        raise RuntimeError(f"No usable AI provider is configured for {role.value}")
    return resolved.provider, model_override or resolved.model


def resolve_embeddings(session: Session) -> AIProviderInstance | None:
    """The provider to embed with: the first eligible configured provider (in saved
    order) that can embed. Capability-based rather than role-based — embeddings are
    not a task administrators assign."""
    for row in eligible_providers(session):
        provider_cls = _PROVIDERS.get(row.provider.value)
        if provider_cls is not None and provider_cls.embedding_dimensions is not None:
            return _build(row)
    return None


def get_ai_provider(session: Session) -> AIProviderInstance | None:
    """The default provider instance: the first eligible configured provider in saved
    display order, or None when none is usable. Callers that need a task's model
    resolve through `resolve_task` instead."""
    rows = eligible_providers(session)
    return _build(rows[0]) if rows else None


def get_assistant_provider(session: Session) -> AIProviderInstance | None:
    """The assistant's provider instance under the persisted assignment, or None."""
    resolved = resolve_task(session, ModelRole.ASSISTANT)
    return resolved.provider if resolved is not None else None


def ai_ready(session: Session) -> bool:
    """Whether AI work can run at all: at least one configured provider holds an API
    key. Gates the extraction trigger and the assistant composer (and their UI)."""
    ensure_provider_configs(session)
    return bool(
        session.scalars(
            select(AIProviderConfig).where(
                AIProviderConfig.api_key.is_not(None), AIProviderConfig.api_key != ""
            )
        ).first()
    )


def ocr_ready(session: Session) -> bool:
    """Whether OCR can run: Gemini (the only OCR-capable provider until MY-190) is
    configured with a key. Gates PDF-only extraction."""
    row = session.get(AIProviderConfig, AIProvider.GEMINI)
    return bool(row is not None and row.api_key)


# -- Writes (shared by the config API; ValueError maps to a 422 response) --------


def set_provider_key(
    session: Session, provider: AIProvider, api_key: str | None
) -> AIProviderConfig:
    """Set (non-empty), clear (empty/None), or keep a provider's key. Surrounding
    whitespace is stripped — a blank key clears rather than configuring. Creates the
    provider row when missing."""
    row = session.get(AIProviderConfig, provider)
    if row is None:
        ensure_provider_configs(session)
        row = session.get(AIProviderConfig, provider)
    assert row is not None
    row.api_key = (api_key.strip() if api_key else "") or None
    session.flush()
    return row


def set_provider_order(session: Session, ordered: list[AIProvider]) -> None:
    """Persist a full provider display order. Must name every configured catalogue
    provider exactly once."""
    rows = {row.provider: row for row in ensure_provider_configs(session)}
    if sorted(ordered) != sorted(rows):
        raise ValueError("provider order must name every provider exactly once")
    for order, provider in enumerate(ordered):
        rows[provider].display_order = order
    session.flush()


def add_provider_models(
    session: Session, provider: AIProvider, model_ids: list[str]
) -> AIProviderConfig:
    """Append usable model IDs to a provider. Names must be non-empty, unique, and
    fit the 200-character column."""
    cleaned = [model.strip() for model in model_ids]
    if any(not model for model in cleaned):
        raise ValueError("model IDs must be non-empty")
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("model IDs must be unique")
    if any(len(model) > 200 for model in cleaned):
        raise ValueError("model IDs must fit in 200 characters")
    row = session.get(AIProviderConfig, provider)
    if row is None:
        ensure_provider_configs(session)
        row = session.get(AIProviderConfig, provider)
    assert row is not None
    existing = list(row.model_ids or [])
    duplicates = [model for model in cleaned if model in existing]
    if duplicates:
        raise ValueError(f"model already listed for {provider.value}: {duplicates[0]}")
    row.model_ids = existing + cleaned
    session.flush()
    return row


def remove_provider_models(
    session: Session, provider: AIProvider, model_ids: list[str]
) -> AIProviderConfig:
    """Remove usable model IDs from a provider. Rejects any model an assignment
    still references, so resolution can never point at an unlisted model."""
    if len(set(model_ids)) != len(model_ids):
        raise ValueError("model IDs must be unique")
    row = session.get(AIProviderConfig, provider)
    if row is None:
        raise ValueError(f"unknown provider: {provider.value}")
    for model in model_ids:
        used = session.scalars(
            select(AITaskAssignment).where(
                AITaskAssignment.provider == provider,
                AITaskAssignment.model_id == model,
            )
        ).first()
        if used is not None:
            raise ValueError(
                f"model {model} is still assigned to {used.role.value};"
                " reassign the task first"
            )
    remaining = [model for model in (row.model_ids or []) if model not in set(model_ids)]
    if len(remaining) + len(model_ids) != len(row.model_ids or []):
        missing = set(model_ids) - set(row.model_ids or [])
        raise ValueError(f"model not listed for {provider.value}: {sorted(missing)[0]}")
    row.model_ids = remaining
    session.flush()
    return row


def set_task_assignment(
    session: Session,
    role: ModelRole,
    entries: list[tuple[AIProvider, str]],
) -> None:
    """Replace a role's assignment rows. An empty list removes the assignment (the
    task falls back to default resolution). Only the recipe-ingredient role may hold
    more than one entry. Every entry must name a known provider row listing the model."""
    if role != ModelRole.RECIPE_INGREDIENTS and len(entries) > 1:
        raise ValueError(f"only {ModelRole.RECIPE_INGREDIENTS.value} takes fallbacks")
    if role == ModelRole.OCR:
        # Gemini is the sole OCR-capable provider until MY-190: the resolver must
        # never select Anthropic or OpenRouter for OCR, explicitly or by default.
        for provider, _model_id in entries:
            if recommendation(provider.value, ModelRole.OCR) is None:
                raise ValueError(f"{provider.value} cannot do OCR yet")
    ensure_provider_configs(session)
    for provider, model_id in entries:
        row = session.get(AIProviderConfig, provider)
        if row is None:
            raise ValueError(f"unknown provider: {provider.value}")
        if model_id not in (row.model_ids or []):
            raise ValueError(f"model {model_id} is not listed for {provider.value}")
    for existing in session.scalars(
        select(AITaskAssignment).where(AITaskAssignment.role == role)
    ).all():
        session.delete(existing)
    session.flush()
    for position, (provider, model_id) in enumerate(entries):
        session.add(
            AITaskAssignment(
                role=role, position=position, provider=provider, model_id=model_id
            )
        )
    session.flush()


def upsert_provider_config(
    session: Session,
    provider: AIProvider,
    *,
    api_key: str = "",
    model_ids: list[str] | None = None,
    display_order: int | None = None,
) -> AIProviderConfig:
    """Create-or-update one provider row in a single call — the seam tests (and the
    v1 import) use to configure offline providers without driving the API."""
    ensure_provider_configs(session)
    row = session.get(AIProviderConfig, provider)
    if row is None:
        row = AIProviderConfig(
            provider=provider,
            api_key=api_key or None,
            display_order=display_order if display_order is not None else 0,
            model_ids=model_ids if model_ids is not None else seed_model_ids(provider.value),
        )
        session.add(row)
    else:
        row.api_key = api_key or None
        if model_ids is not None:
            row.model_ids = model_ids
        if display_order is not None:
            row.display_order = display_order
    session.flush()
    return row
