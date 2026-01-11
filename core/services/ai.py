import abc
import json
import logging
import time
from decimal import Decimal
from enum import Enum
from pathlib import Path

import requests
import tiktoken
from google import genai
from pydantic import ValidationError

from core.models import Config, RecipeData
from core.services.prompts import (
    DEDUPLICATE_KEYWORDS_PROMPT,
    EXTRACT_RECIPES_PROMPT,
    IMAGE_MATCH_CHECK_PROMPT,
)

logger = logging.getLogger(__name__)
logging.getLogger("google.genai").setLevel(logging.ERROR)

SCHEMA_PATH = Path(__file__).parent / "recipe_schema.json"

MAX_TIMEOUT = 600


class ExtractionMethod(Enum):
    MANY_RECIPES_PER_FILE = "many_recipes_per_file"
    ONE_RECIPE_PER_FILE = "one_recipe_per_file"
    BLOCKS_OF_FILES = "blocks_of_files"


def get_config():
    return Config.get_solo()


def load_recipe_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def count_tokens(text: str) -> int:
    encoding = tiktoken.encoding_for_model("gpt-4o")
    return len(encoding.encode(text))


class AIProvider(abc.ABC):
    NAME = NotImplemented

    IMAGE_MATCH_MODEL = NotImplemented
    EXTRACT_MANY_PER_FILE_MODEL = NotImplemented
    EXTRACT_ONE_PER_FILE_MODEL = NotImplemented
    EXTRACT_BLOCKS_MODEL = NotImplemented
    DEDUPLICATE_MODEL = NotImplemented
    EMBEDDING_MODEL = NotImplemented
    EMBEDDING_DIMENSIONS = NotImplemented

    def __init__(self) -> None:
        config = get_config()
        self.api_key = config.api_key

    @abc.abstractmethod
    def _get_completion(
        self, prompt: str, model: str, schema: dict | None = None, temp: float = 0
    ) -> tuple[str, dict]:
        pass

    @abc.abstractmethod
    def generate_embedding(self, text: str, task_type: str) -> list[float]:
        pass

    def check_if_can_match_images(self, sample_content: str) -> tuple[bool, dict]:
        prompt = IMAGE_MATCH_CHECK_PROMPT.format(sample_content=sample_content)
        response, usage = self._get_completion(prompt, model=self.IMAGE_MATCH_MODEL, temp=0)

        if response is None:
            logger.warning("Failed to check image matching, assuming no")
            return False, {"cost_usd": None, "input_tokens": None, "output_tokens": None}

        result = response.lower().strip().strip("\"'")
        if result not in ("yes", "no"):
            raise ValueError(f"Unexpected response '{response}'. Expected 'yes' or 'no'.")
        return result == "yes", usage

    def _get_model_for_extraction_method(self, method: ExtractionMethod) -> str:
        _map = {
            ExtractionMethod.BLOCKS_OF_FILES: self.EXTRACT_BLOCKS_MODEL,
            ExtractionMethod.MANY_RECIPES_PER_FILE: self.EXTRACT_MANY_PER_FILE_MODEL,
            ExtractionMethod.ONE_RECIPE_PER_FILE: self.EXTRACT_ONE_PER_FILE_MODEL,
        }
        return _map[method]

    def extract_recipes(self, content: str, model: str) -> tuple[list[RecipeData], dict]:
        schema = load_recipe_schema()
        prompt = EXTRACT_RECIPES_PROMPT.format(schema=json.dumps(schema), content=content)

        response, usage = self._get_completion(prompt, model=model, schema=schema, temp=0)

        if not response:
            return [], usage

        try:
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            raw_recipes = json.loads(response)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from AI response:\n{response}")
            return [], usage

        valid_recipes = []
        for i, recipe_data in enumerate(raw_recipes):
            try:
                recipe = RecipeData(**recipe_data)
                valid_recipes.append(recipe)
            except ValidationError as e:
                logger.warning(f"Skipping invalid recipe at index {i}: {e}")
                continue

        return valid_recipes, usage

    def deduplicate_keywords(self, keywords: list[str]) -> dict[str, str]:
        prompt = DEDUPLICATE_KEYWORDS_PROMPT.format(keywords=json.dumps(keywords))
        response, _ = self._get_completion(prompt, model=self.DEDUPLICATE_MODEL)

        if not response:
            return {}

        try:
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = json.loads(response.strip())
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from AI response: {response}")
            return {}

        return response


class OpenRouterProvider(AIProvider):
    NAME = "OPENROUTER"

    IMAGE_MATCH_MODEL = "google/gemini-2.5-flash"
    EXTRACT_MANY_PER_FILE_MODEL = "google/gemini-2.5-flash"
    EXTRACT_ONE_PER_FILE_MODEL = "openai/gpt-oss-120b"
    EXTRACT_BLOCKS_MODEL = "google/gemini-2.5-flash"
    DEDUPLICATE_MODEL = "google/gemini-2.5-flash"
    EMBEDDING_MODEL = None
    EMBEDDING_DIMENSIONS = None

    def generate_embedding(self, text: str, task_type: str) -> list[float] | None:
        logger.warning("OpenRouter does not yet support embeddings, use Gemini provider")
        return None

    def generate_embeddings_batch(
        self, texts: list[str], task_type: str
    ) -> list[list[float]] | None:
        logger.warning("OpenRouter does not yet support embeddings, use Gemini provider")
        return None

    def _get_completion(self, prompt, model, schema=None, temp=0):
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temp,
        }

        if model == "openai/gpt-oss-120b":
            payload["max_tokens"] = 110_000

        max_retries = 5
        backoff_factor = 2

        response_content = None
        usage_metadata = {}

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
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

                is_retryable = response.status_code in (429, 500, 502, 503, 504) or error_code in (
                    429,
                    500,
                )

                if is_retryable and attempt < max_retries:
                    sleep_time = backoff_factor * (2 ** (attempt - 1))
                    logger.warning(
                        f"OpenRouter returned retryable error (HTTP {response.status_code}, code {error_code}): attempt {attempt}/{max_retries}. Retrying in {sleep_time}s..."
                    )
                    time.sleep(sleep_time)
                    continue

                if error_data:
                    raise ValueError(f"OpenRouter API error: {error_data}")

                response.raise_for_status()
                response_content = result["choices"][0]["message"]["content"]
                usage_data = result.get("usage", {})
                raw_cost = usage_data.get("cost")
                usage_metadata = {
                    "cost_usd": Decimal(str(raw_cost)) if raw_cost else None,
                    "input_tokens": usage_data.get("prompt_tokens") or None,
                    "output_tokens": usage_data.get("completion_tokens") or None,
                }
                break

            except (requests.exceptions.RequestException, KeyError) as e:
                if attempt < max_retries:
                    sleep_time = backoff_factor * (2 ** (attempt - 1))
                    logger.warning(
                        f"OpenRouter request failed ({type(e).__name__}): {e}. Attempt {attempt}/{max_retries}. Retrying in {sleep_time}s..."
                    )
                    time.sleep(sleep_time)
                    continue
                else:
                    if isinstance(e, KeyError):
                        raise ValueError(
                            f"Unexpected response format from OpenRouter API: {e}. Response: {result}"
                        ) from e
                    raise

        return response_content or "", usage_metadata


class GeminiProvider(AIProvider):
    NAME = "GEMINI"

    IMAGE_MATCH_MODEL = "gemini-2.5-flash"
    EXTRACT_MANY_PER_FILE_MODEL = "gemini-2.5-flash-lite"
    EXTRACT_ONE_PER_FILE_MODEL = "gemini-2.5-flash-lite"
    EXTRACT_BLOCKS_MODEL = "gemini-2.5-flash"
    DEDUPLICATE_MODEL = "gemini-2.5-flash"
    EMBEDDING_MODEL = "gemini-embedding-001"
    EMBEDDING_DIMENSIONS = 3072

    def __init__(self) -> None:
        super().__init__()
        self.client = genai.Client(
            api_key=self.api_key,
            http_options={
                "retry_options": {
                    "attempts": 5,
                    "http_status_codes": [429, 500, 502, 503, 504],
                }
            },
        )

    def generate_embedding(self, text: str, task_type: str) -> list[float]:
        response = self.client.models.embed_content(
            model=self.EMBEDDING_MODEL,
            contents=text,
            config={"task_type": task_type},
        )
        return response.embeddings[0].values

    def generate_embeddings_batch(self, texts: list[str], task_type: str) -> list[list[float]]:
        response = self.client.models.embed_content(
            model=self.EMBEDDING_MODEL,
            contents=texts,
            config={"task_type": task_type},
        )
        return [embedding.values for embedding in response.embeddings]

    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> Decimal:
        pricing = {
            "gemini-2.5-flash": (0.30, 2.50),
            "gemini-2.5-flash-lite": (0.10, 0.40),
            "gemini-2.0-flash-lite": (0.075, 0.30),
        }
        input_rate, output_rate = pricing[model]
        cost_usd = (input_tokens / 1_000_000) * input_rate + (
            output_tokens / 1_000_000
        ) * output_rate
        return Decimal(str(cost_usd))

    def _get_completion(self, prompt, model, schema=None, temp=0):
        config = {
            "response_mime_type": "application/json",
            "temperature": temp,
        }
        if schema:
            config["response_json_schema"] = schema

        response = self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )

        usage_metadata = {}
        if response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            total_tokens = getattr(response.usage_metadata, "total_token_count", 0) or 0
            output_tokens = total_tokens - input_tokens
            cost = self._calculate_cost(model, input_tokens, output_tokens)

            usage_metadata = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
            }

        return response.text or "", usage_metadata


def get_ai_provider():
    config = get_config()
    if not config.ai_provider or not config.api_key:
        return None

    provider_map = {
        "OPENROUTER": OpenRouterProvider,
        "GEMINI": GeminiProvider,
    }
    provider_class = provider_map.get(config.ai_provider)
    if provider_class:
        return provider_class()
    return None
