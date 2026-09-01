import logging
from decimal import Decimal
from typing import ClassVar, cast

from google import genai
from google.genai import types
from google.genai.types import ContentListUnion, GenerateContentConfigDict

from app.services.ai.base import AIProvider, AIResponseError, EmbedTask, ModelRole, Usage
from app.services.prompts import READ_PAGE_PROMPT
from app.services.recipe_enrichment.schema import ENRICHMENT_JSON_SCHEMA

logger = logging.getLogger(__name__)
logging.getLogger("google.genai").setLevel(logging.ERROR)

# USD per million tokens (input, output), used to derive cost from token counts.
_PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.0-flash-lite": (0.075, 0.30),
}


def _candidate_text(response: object, candidate: object) -> str:
    try:
        text = getattr(response, "text", None)
        if text is not None:
            return text
    except Exception:
        pass
    content = getattr(candidate, "content", None)
    parts = getattr(content, "parts", None) or []
    return "".join(getattr(part, "text", "") or "" for part in parts)


class GeminiProvider(AIProvider):
    name = "GEMINI"
    models: ClassVar[dict[ModelRole, str]] = {
        ModelRole.IMAGE_MATCH: "gemini-2.5-flash",
        ModelRole.OCR: "gemini-2.5-flash",
        ModelRole.MANY_RECIPES_PER_FILE: "gemini-2.5-flash-lite",
        ModelRole.ONE_RECIPE_PER_FILE: "gemini-2.5-flash-lite",
        ModelRole.BLOCKS_OF_FILES: "gemini-2.5-flash",
        ModelRole.BOOK_KEYWORDS: "gemini-2.5-flash",
        ModelRole.KEYWORD_DEDUP: "gemini-2.5-flash",
        ModelRole.ASSISTANT: "gemini-2.5-flash",
        ModelRole.RECIPE_ENRICHMENT: "gemini-2.5-flash",
    }
    embedding_model: ClassVar[str] = "gemini-embedding-001"
    embedding_dimensions: ClassVar[int] = 3072
    vision_model: ClassVar[str] = "gemini-2.5-flash"

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
            if schema is ENRICHMENT_JSON_SCHEMA:
                config["thinking_config"] = {"thinking_budget": 0}

        response = self.client.models.generate_content(model=model, contents=prompt, config=config)

        usage = Usage()
        if response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            candidate_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
            thinking_tokens = getattr(response.usage_metadata, "thoughts_token_count", 0) or 0
            output_tokens = candidate_tokens + thinking_tokens
            usage = Usage(
                cost_usd=self._calculate_cost(model, input_tokens, output_tokens),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                candidate_tokens=candidate_tokens,
                thinking_tokens=thinking_tokens,
            )

        candidates = response.candidates or []
        finish_reason = candidates[0].finish_reason if candidates else None
        reason = getattr(finish_reason, "name", finish_reason)
        if reason is not None and reason != "STOP":
            logger.warning(
                f"{model} stopped with finish_reason={reason} after "
                f"{usage.output_tokens if usage.output_tokens is not None else 'unreported'} "
                "output token(s); the reply is incomplete"
            )

        return response.text or "", usage

    def read_page(
        self, image: bytes, media_type: str, model: str | None = None
    ) -> tuple[str, Usage]:
        resolved_model = model or self.vision_model
        usage = Usage()
        max_attempts = 2
        for attempt in range(max_attempts):
            temperature = 0.2 if attempt > 0 else 0.0
            response = self.client.models.generate_content(
                model=resolved_model,
                contents=[
                    READ_PAGE_PROMPT,
                    types.Part.from_bytes(data=image, mime_type=media_type),
                ],
                config={"temperature": temperature, "max_output_tokens": 16_384},
            )
            if response.usage_metadata:
                input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                total_tokens = getattr(response.usage_metadata, "total_token_count", 0) or 0
                output_tokens = total_tokens - input_tokens
                usage += Usage(
                    cost_usd=self._calculate_cost(resolved_model, input_tokens, output_tokens),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            candidates = response.candidates or []
            if not candidates:
                raise AIResponseError(f"{resolved_model} returned no OCR candidate", usage)
            finish_reason = candidates[0].finish_reason
            reason = getattr(finish_reason, "name", finish_reason)
            if reason == "STOP":
                return _candidate_text(response, candidates[0]), usage
            if reason == "RECITATION":
                if attempt < max_attempts - 1:
                    logger.info(f"{resolved_model} hit RECITATION finish_reason; retrying OCR")
                    continue
                text = _candidate_text(response, candidates[0])
                logger.warning(
                    f"{resolved_model} stopped OCR with finish_reason=RECITATION; "
                    f"returning partial text ({len(text)} chars)"
                )
                return text, usage
            if reason != "MAX_TOKENS":
                raise AIResponseError(
                    f"{resolved_model} stopped OCR with finish_reason={reason}", usage
                )
        raise AIResponseError(f"{resolved_model} stopped OCR with finish_reason=MAX_TOKENS", usage)

    def embed(self, text: str, task: EmbedTask) -> list[float]:
        response = self.client.models.embed_content(
            model=self.embedding_model, contents=text, config={"task_type": task.value}
        )
        embeddings = response.embeddings or []
        if not embeddings or embeddings[0].values is None:
            raise RuntimeError("Gemini returned no embedding")
        return list(embeddings[0].values)

    def embed_batch(self, texts: list[str], task: EmbedTask) -> list[list[float]]:
        response = self.client.models.embed_content(
            model=self.embedding_model,
            contents=cast(ContentListUnion, texts),
            config={"task_type": task.value},
        )
        embeddings = response.embeddings or []
        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"Gemini returned {len(embeddings)} embeddings for {len(texts)} texts"
            )
        out: list[list[float]] = []
        for embedding in embeddings:
            if embedding.values is None:
                raise RuntimeError("Gemini returned an empty embedding")
            out.append(list(embedding.values))
        return out
