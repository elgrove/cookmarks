import json
from decimal import Decimal
from typing import Any, ClassVar

from anthropic import Anthropic
from anthropic.types import TextBlock, ToolUseBlock

from app.services.ai.base import AIProvider, ModelRole, Usage

_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}


class AnthropicProvider(AIProvider):
    name = "ANTHROPIC"
    models: ClassVar[dict[ModelRole, str]] = {
        ModelRole.IMAGE_MATCH: "claude-sonnet-5",
        ModelRole.MANY_RECIPES_PER_FILE: "claude-sonnet-5",
        ModelRole.ONE_RECIPE_PER_FILE: "claude-sonnet-5",
        ModelRole.BLOCKS_OF_FILES: "claude-sonnet-5",
        ModelRole.BOOK_KEYWORDS: "claude-sonnet-5",
        ModelRole.KEYWORD_DEDUP: "claude-sonnet-5",
        ModelRole.ASSISTANT: "claude-sonnet-5",
        ModelRole.RECIPE_ENRICHMENT: "claude-sonnet-5",
        ModelRole.RECIPE_INGREDIENTS: "claude-haiku-4-5-20251001",
        ModelRole.RECIPE_INGREDIENTS_FALLBACK: "claude-haiku-4-5-20251001",
        ModelRole.RECIPE_SEMANTICS: "claude-haiku-4-5-20251001",
    }

    def __init__(self, api_key: str, model_overrides: dict[str, str] | None = None) -> None:
        super().__init__(api_key, model_overrides)
        self.client = Anthropic(api_key=api_key)

    def _complete(
        self, prompt: str, model: str, *, schema: dict | None = None, temp: float = 0
    ) -> tuple[str, Usage]:
        kwargs: dict[str, Any] = {}
        if schema is not None:
            kwargs["tools"] = [
                {
                    "name": "structured_output",
                    "description": "Output structured data matching the schema",
                    "input_schema": schema,
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": "structured_output"}

        extra_body: dict[str, Any] = {"temperature": temp}
        with self.client.messages.stream(
            model=model,
            max_tokens=32_000,
            messages=[{"role": "user", "content": prompt}],
            extra_body=extra_body,
            **kwargs,
        ) as stream:
            response = stream.get_final_message()
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        input_rate, output_rate = _PRICING.get(model, (0.0, 0.0))
        usage = Usage(
            cost_usd=Decimal(
                str(
                    (input_tokens / 1_000_000) * input_rate
                    + (output_tokens / 1_000_000) * output_rate
                )
            ),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=response.stop_reason,
        )
        for block in response.content:
            if isinstance(block, ToolUseBlock):
                return json.dumps(block.input), usage
        return "".join(
            block.text for block in response.content if isinstance(block, TextBlock)
        ), usage
