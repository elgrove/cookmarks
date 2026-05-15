from ninja import Router

from core.api.schemas import ConfigOut, ConfigPatch
from core.models import Config

router = Router()


def _mask(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "•" * len(api_key)
    return f"{api_key[:4]}{'•' * (len(api_key) - 8)}{api_key[-4:]}"


def _config_to_out(config: Config) -> dict:
    return {
        "ai_provider": config.ai_provider or "",
        "api_key_masked": _mask(config.api_key),
        "has_api_key": bool(config.api_key),
        "extraction_rate_limit_per_minute": config.extraction_rate_limit_per_minute,
        "is_configured": bool(config.ai_provider and config.api_key),
    }


@router.get("", response=ConfigOut)
def get_config(request):
    return _config_to_out(Config.get_solo())


@router.patch("", response=ConfigOut)
def update_config(request, data: ConfigPatch):
    config = Config.get_solo()
    if data.ai_provider is not None:
        config.ai_provider = data.ai_provider
    if data.api_key is not None:
        config.api_key = data.api_key
    if data.extraction_rate_limit_per_minute is not None:
        config.extraction_rate_limit_per_minute = data.extraction_rate_limit_per_minute
    config.save()
    return _config_to_out(config)
