from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest

from app.services.ai.base import AIResponseError
from app.services.ai.gemini import GeminiProvider


def _provider_with_response(text: str, finish_reason: str | None) -> GeminiProvider:
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.client = MagicMock()
    candidates = (
        []
        if finish_reason is None
        else [SimpleNamespace(finish_reason=SimpleNamespace(name=finish_reason))]
    )
    provider.client.models.generate_content.return_value = SimpleNamespace(
        candidates=candidates,
        text=text,
        usage_metadata=None,
    )
    return provider


@pytest.mark.parametrize("text", ["Recipe text", ""])
def test_read_page_accepts_complete_response(text: str) -> None:
    provider = _provider_with_response(text, "STOP")
    result, usage = provider.read_page(b"jpeg", "image/jpeg")
    assert result == text
    assert usage.input_tokens is None


@pytest.mark.parametrize("finish_reason", ["MAX_TOKENS", "SAFETY"])
def test_read_page_rejects_incomplete_response(finish_reason: str) -> None:
    provider = _provider_with_response("partial", finish_reason)
    with pytest.raises(RuntimeError, match=f"finish_reason={finish_reason}"):
        provider.read_page(b"jpeg", "image/jpeg")


def test_read_page_retries_token_limit() -> None:
    provider = _provider_with_response("complete", "STOP")
    generate = cast(MagicMock, provider.client.models.generate_content)
    complete = generate.return_value
    limited = SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="MAX_TOKENS"))],
        text="partial",
        usage_metadata=None,
    )
    generate.side_effect = [limited, complete]
    result, _usage = provider.read_page(b"jpeg", "image/jpeg")
    assert result == "complete"


def test_read_page_rejects_missing_candidate() -> None:
    provider = _provider_with_response("", None)
    with pytest.raises(RuntimeError, match="no OCR candidate"):
        provider.read_page(b"jpeg", "image/jpeg")


def test_read_page_reports_usage_from_failed_retries() -> None:
    provider = _provider_with_response("partial", "MAX_TOKENS")
    generate = cast(MagicMock, provider.client.models.generate_content)
    generate.return_value.usage_metadata = SimpleNamespace(
        prompt_token_count=10,
        total_token_count=30,
    )
    with pytest.raises(AIResponseError) as caught:
        provider.read_page(b"jpeg", "image/jpeg")
    assert caught.value.usage.input_tokens == 20
    assert caught.value.usage.output_tokens == 40
