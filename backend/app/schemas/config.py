from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AIProvider, ModelRole

if TYPE_CHECKING:
    from app.models.ai_config import AIProviderConfig, AITaskAssignment


class ProviderConfigRead(BaseModel):
    """One provider's settings as the client sees them. The API key itself is never
    serialised — only whether one is stored."""

    provider: AIProvider
    api_key_set: bool
    display_order: int
    model_ids: list[str]


class TaskAssignmentRead(BaseModel):
    """One pinned task entry: which provider-and-model pair handles the role at this
    position (position 0, except the recipe-ingredient fallback chain)."""

    role: ModelRole
    position: int
    provider: AIProvider
    model_id: str


class ConfigRead(BaseModel):
    """The wire view of the AI configuration: provider rows in display order, task
    assignments in (role, position) order, every provider's per-role recommendations
    (so the UI can show the recommended pair under each selector), and the one
    non-AI setting."""

    providers: list[ProviderConfigRead]
    task_assignments: list[TaskAssignmentRead]
    recommendations: dict[str, dict[str, str]]
    extraction_rate_limit_per_minute: int

    @classmethod
    def from_state(
        cls,
        providers: "list[AIProviderConfig]",
        assignments: "list[AITaskAssignment]",
        recommendations: dict[str, dict[str, str]],
        rate_limit: int,
    ) -> "ConfigRead":
        return cls(
            providers=[
                ProviderConfigRead(
                    provider=row.provider,
                    api_key_set=bool(row.api_key),
                    display_order=row.display_order,
                    model_ids=list(row.model_ids or []),
                )
                for row in providers
            ],
            task_assignments=[
                TaskAssignmentRead(
                    role=row.role,
                    position=row.position,
                    provider=row.provider,
                    model_id=row.model_id,
                )
                for row in assignments
            ],
            recommendations=recommendations,
            extraction_rate_limit_per_minute=rate_limit,
        )


class ProviderConfigUpdate(BaseModel):
    """One provider's changes. `api_key` is tri-state: omitted keeps the stored key,
    null/empty clears it, a value sets or rotates it. Display order moves through
    `provider_order` on ConfigUpdate, so there is exactly one ordering mechanism."""

    model_config = ConfigDict(extra="forbid")

    provider: AIProvider
    api_key: str | None = Field(default=None, max_length=200)
    add_models: list[str] | None = None
    remove_models: list[str] | None = None


class TaskAssignmentEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: AIProvider
    model_id: str = Field(max_length=200)


class TaskAssignmentUpdate(BaseModel):
    """Replace a role's assignment rows. An empty `entries` removes the assignment
    (the task falls back to default resolution). Only the recipe-ingredient role
    accepts more than one entry."""

    model_config = ConfigDict(extra="forbid")

    role: ModelRole
    entries: list[TaskAssignmentEntry] = []


class ConfigUpdate(BaseModel):
    """A partial update. Only the sections present are applied, in order: provider
    rows (keys, orders, model lists), then the provider display order, then task
    assignments (validated against the updated model lists) — so one request can add
    a model and immediately assign it."""

    model_config = ConfigDict(extra="forbid")

    provider_configs: list[ProviderConfigUpdate] | None = None
    provider_order: list[AIProvider] | None = None
    task_assignments: list[TaskAssignmentUpdate] | None = None
    extraction_rate_limit_per_minute: int | None = Field(default=None, ge=1)


class AIReadiness(BaseModel):
    """Whether AI work can start — no secrets, safe for every signed-in user.
    Extraction and the assistant need any keyed provider; OCR needs Gemini
    (the only OCR-capable provider until MY-190)."""

    extraction_available: bool
    assistant_available: bool
    ocr_available: bool
