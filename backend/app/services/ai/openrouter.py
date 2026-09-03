import json
import logging
import time
from decimal import Decimal
from typing import Any, ClassVar

import httpx

from app.services.ai.base import MAX_TIMEOUT, AIProvider, ModelRole, Usage

logger = logging.getLogger(__name__)

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_RETRYABLE_STATUS = (429, 500, 502, 503, 504)
_MAX_RETRIES = 5
_BACKOFF_FACTOR = 2


class OpenRouterProvider(AIProvider):
    name = "OPENROUTER"
    models: ClassVar[dict[ModelRole, str]] = {
        ModelRole.IMAGE_MATCH: "google/gemini-2.5-flash",
        ModelRole.MANY_RECIPES_PER_FILE: "google/gemini-2.5-flash",
        ModelRole.ONE_RECIPE_PER_FILE: "openai/gpt-oss-120b",
        ModelRole.BLOCKS_OF_FILES: "google/gemini-2.5-flash",
        ModelRole.BOOK_KEYWORDS: "google/gemini-2.5-flash",
        ModelRole.KEYWORD_DEDUP: "google/gemini-2.5-flash",
        ModelRole.ASSISTANT: "google/gemini-2.5-flash",
        ModelRole.RECIPE_ENRICHMENT: "google/gemini-2.5-flash",
    }

    def _complete(
        self, prompt: str, model: str, *, schema: dict | None = None, temp: float = 0
    ) -> tuple[str, Usage]:
        payload: dict[str, object] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temp,
        }
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "cookmarks_response",
                    "strict": True,
                    "schema": schema,
                },
            }
            payload["provider"] = {"require_parameters": True}
            payload["max_tokens"] = 4_096
        elif model == "openai/gpt-oss-120b":
            payload["max_tokens"] = 110_000

        result: dict[str, Any] = {}
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = httpx.post(
                    _API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=MAX_TIMEOUT,
                )

                try:
                    result = response.json()
                except json.JSONDecodeError:
                    result = {}

                error_data = result.get("error", {})
                error_code = error_data.get("code")
                is_retryable = response.status_code in _RETRYABLE_STATUS or error_code in (429, 500)

                if is_retryable and attempt < _MAX_RETRIES:
                    sleep_time = _BACKOFF_FACTOR * (2 ** (attempt - 1))
                    logger.warning(
                        f"OpenRouter retryable error (HTTP {response.status_code}, "
                        f"code {error_code}): attempt {attempt}/{_MAX_RETRIES}. "
                        f"Retrying in {sleep_time}s..."
                    )
                    time.sleep(sleep_time)
                    continue

                if error_data:
                    raise ValueError(f"OpenRouter API error: {error_data}")

                response.raise_for_status()
                choice = result["choices"][0]
                content = choice["message"]["content"]
                usage_data = result.get("usage", {})
                raw_cost = usage_data.get("cost")
                usage = Usage(
                    cost_usd=Decimal(str(raw_cost)) if raw_cost else None,
                    input_tokens=usage_data.get("prompt_tokens") or None,
                    output_tokens=usage_data.get("completion_tokens") or None,
                    finish_reason=choice.get("finish_reason"),
                )
                return content or "", usage

            except (httpx.HTTPError, KeyError) as e:
                if attempt < _MAX_RETRIES:
                    sleep_time = _BACKOFF_FACTOR * (2 ** (attempt - 1))
                    logger.warning(
                        f"OpenRouter request failed ({type(e).__name__}): {e}. "
                        f"Attempt {attempt}/{_MAX_RETRIES}. Retrying in {sleep_time}s..."
                    )
                    time.sleep(sleep_time)
                    continue
                if isinstance(e, KeyError):
                    raise ValueError(
                        f"Unexpected response format from OpenRouter API: {e}. Response: {result}"
                    ) from e
                raise

        # Unreachable: the final attempt always returns or raises above.
        return "", Usage()
