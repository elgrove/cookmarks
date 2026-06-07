import logging

from sqlalchemy.orm import Session

from app.models.config import Config
from app.services.ai.base import AIProvider
from app.services.ai.gemini import GeminiProvider
from app.services.ai.openrouter import OpenRouterProvider
from app.services.ai.stub import StubProvider

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, type[AIProvider]] = {
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
    needs to render its provider dropdown and decide whether to show the API key field."""
    return [(name, cls.requires_api_key) for name, cls in _PROVIDERS.items()]


def get_config(session: Session) -> Config:
    """Return the singleton Config row (id=1), creating it if absent."""
    config = session.get(Config, 1)
    if config is None:
        config = Config(id=1)
        session.add(config)
        session.flush()
    return config


def get_ai_provider(session: Session) -> AIProvider | None:
    """Build the AI provider named in Config, or None if none is usable (no provider
    selected, unknown provider, or a network provider without an API key)."""
    config = get_config(session)
    if config.ai_provider is None:
        return None

    provider_cls = _PROVIDERS.get(config.ai_provider)
    if provider_cls is None:
        logger.warning(f"Unknown AI provider configured: {config.ai_provider}")
        return None

    if provider_cls.requires_api_key and not config.api_key:
        logger.warning(f"AI provider {config.ai_provider} configured without an API key")
        return None

    return provider_cls(config.api_key or "", config.model_overrides)
