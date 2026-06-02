import logging
from decimal import Decimal
from typing import ClassVar

from google import genai
from google.genai.types import GenerateContentConfigDict

from app.services.ai.base import AIProvider, ModelRole, Usage

logger = logging.getLogger(__name__)
logging.getLogger("google.genai").setLevel(logging.ERROR)

# USD per million tokens (input, output), used to derive cost from token counts.
_PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.0-flash-lite": (0.075, 0.30),
}


class GeminiProvider(AIProvider):
    name = "GEMINI"
    models: ClassVar[dict[ModelRole, str]] = {
        ModelRole.IMAGE_MATCH: "gemini-2.5-flash",
        ModelRole.MANY_RECIPES_PER_FILE: "gemini-2.5-flash-lite",
        ModelRole.ONE_RECIPE_PER_FILE: "gemini-2.5-flash-lite",
        ModelRole.BLOCKS_OF_FILES: "gemini-2.5-flash",
    }

    def __init__(self, api_key: str, model_overrides: dict[str, str] | None = None) -> None:
        super().__init__(api_key, model_overrides)
        self.client = genai.Client(
            api_key=api_key,
            http_options={
                "retry_options": {
                    "attempts": 5,
                    "http_status_codes": [429, 500, 502, 503, 504],
                }
            },
        )

    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> Decimal:
        input_rate, output_rate = _PRICING[model]
        cost = (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate
        return Decimal(str(cost))

    def _complete(
        self, prompt: str, model: str, *, schema: dict | None = None, temp: float = 0
    ) -> tuple[str, Usage]:
        config: GenerateContentConfigDict = {
            "response_mime_type": "application/json",
            "temperature": temp,
        }
        if schema:
            config["response_json_schema"] = schema

        response = self.client.models.generate_content(model=model, contents=prompt, config=config)

        usage = Usage()
        if response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            total_tokens = getattr(response.usage_metadata, "total_token_count", 0) or 0
            output_tokens = total_tokens - input_tokens
            usage = Usage(
                cost_usd=self._calculate_cost(model, input_tokens, output_tokens),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        return response.text or "", usage
