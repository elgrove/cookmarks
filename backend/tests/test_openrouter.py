from typing import Any

import httpx

from app.services.ai.openrouter import OpenRouterProvider
from app.services.recipe_enrichment.schema import ENRICHMENT_JSON_SCHEMA


def test_complete_sends_strict_json_schema(monkeypatch: Any) -> None:
    """Structured requests must not be routed to a provider without schema support."""
    captured: dict[str, Any] = {}

    def fake_post(*args: Any, **kwargs: Any) -> httpx.Response:
        captured.update(kwargs["json"])
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                "usage": {},
            },
        )

    monkeypatch.setattr("app.services.ai.openrouter.httpx.post", fake_post)
    provider = OpenRouterProvider(api_key="test-key")

    content, usage = provider._complete(
        "Return JSON.", "openai/gpt-oss-120b", schema={"type": "object"}
    )

    assert content == "{}"
    assert usage.finish_reason == "stop"
    assert captured["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "cookmarks_response", "strict": True, "schema": {"type": "object"}},
    }
    assert captured["provider"] == {"require_parameters": True}
    assert captured["max_tokens"] == 4_096


def test_complete_uses_larger_bound_for_gemma_enrichment(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_post(*args: Any, **kwargs: Any) -> httpx.Response:
        captured.update(kwargs["json"])
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                "usage": {},
            },
        )

    monkeypatch.setattr("app.services.ai.openrouter.httpx.post", fake_post)
    provider = OpenRouterProvider(api_key="test-key")

    provider._complete(
        "Return JSON.", "google/gemma-4-31b-it", schema=ENRICHMENT_JSON_SCHEMA
    )

    assert captured["max_tokens"] == 8_192
