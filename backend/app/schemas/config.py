from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AIProvider

if TYPE_CHECKING:
    from app.models.config import Config


class ProviderInfo(BaseModel):
    """One selectable AI provider and whether it needs an API key — the catalogue the
    settings form renders its provider dropdown (and key-field logic) from."""

    name: str
    requires_api_key: bool


class ConfigRead(BaseModel):
    """The wire view of the singleton Config. The API key is deliberately absent — only
    the boolean `api_key_set` is exposed, so the secret is never serialised to the client."""

    ai_provider: AIProvider | None
    api_key_set: bool
    assistant_provider: AIProvider | None
    assistant_api_key_set: bool
    extraction_rate_limit_per_minute: int
    providers: list[ProviderInfo]

    @classmethod
    def from_config(cls, config: "Config", providers: list[ProviderInfo]) -> "ConfigRead":
        return cls(
            ai_provider=config.ai_provider,
            api_key_set=bool(config.api_key),
            assistant_provider=config.assistant_provider,
            assistant_api_key_set=bool(config.assistant_api_key),
            extraction_rate_limit_per_minute=config.extraction_rate_limit_per_minute,
            providers=providers,
        )


class ConfigUpdate(BaseModel):
    """A partial update of the Config. Every field is optional: only those actually
    present in the request body are applied (via model_fields_set), so omitting a field
    leaves it untouched. For `api_key`, an empty string or null clears the stored key,
    a non-empty string sets or rotates it."""

    model_config = ConfigDict(extra="forbid")

    ai_provider: AIProvider | None = None
    api_key: str | None = None
    assistant_provider: AIProvider | None = None
    assistant_api_key: str | None = None
    extraction_rate_limit_per_minute: int | None = Field(default=None, ge=1)
