from typing import Any

import httpx

from app.services.ai.openrouter import OpenRouterProvider


def test_complete_sends_strict_json_schema(monkeypatch: Any) -> None:
    """Structured requests must not be routed to a provider without schema support."""
    captured: dict[str, Any] = {}

    def fake_post(*args: Any, **kwargs: Any) -> httpx.Response:
        captured.update(kwargs["json"])
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": "{}"}}], "usage": {}},
        )

    monkeypatch.setattr("app.services.ai.openrouter.httpx.post", fake_post)
    provider = OpenRouterProvider(api_key="test-key")

    content, _usage = provider._complete(
        "Return JSON.", "openai/gpt-oss-120b", schema={"type": "object"}
    )

    assert content == "{}"
    assert captured["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "cookmarks_response", "strict": True, "schema": {"type": "object"}},
    }
    assert captured["provider"] == {"require_parameters": True}
    assert captured["max_tokens"] == 4_096
