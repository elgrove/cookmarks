import abc
import json
import logging
import time
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
    with open(SCHEMA_PATH, "r") as f:
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

    def __init__(self) -> None:
        config = get_config()
        self.api_key = config.api_key

    @abc.abstractmethod
    def _get_completion(self, prompt: str, model: str, schema: dict = None, temp: float = 0) -> tuple[str, dict]:
        pass

    def check_if_can_match_images(self, sample_content: str) -> bool:
        prompt = IMAGE_MATCH_CHECK_PROMPT.format(sample_content=sample_content)
        response, _ = self._get_completion(prompt, model=self.IMAGE_MATCH_MODEL, temp=0)

        if response is None:
            logger.warning("Failed to check image matching, assuming no")
            return False

        result = response.lower().strip().strip('"\'')
        if result not in ("yes", "no"):
            raise ValueError(f"Unexpected response '{response}'. Expected 'yes' or 'no'.")
        return result == "yes"

    def _get_model_for_extraction_method(self, method: ExtractionMethod) -> str:
        _map = {
            ExtractionMethod.BLOCKS_OF_FILES: self.EXTRACT_BLOCKS_MODEL,
            ExtractionMethod.MANY_RECIPES_PER_FILE: self.EXTRACT_MANY_PER_FILE_MODEL,
            ExtractionMethod.ONE_RECIPE_PER_FILE: self.EXTRACT_ONE_PER_FILE_MODEL,
        }
        return _map[method]

    def extract_recipes(self, content: str, method: ExtractionMethod) -> tuple[list[RecipeData], dict]:
        schema = load_recipe_schema()
        prompt = EXTRACT_RECIPES_PROMPT.format(schema=json.dumps(schema), content=content)

        model = self._get_model_for_extraction_method(method)
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
    DEDUPLICATE_MODEL = "google/gemini-2.5-flash-lite"

    def _get_completion(self, prompt, model, schema=None, temp=0):
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temp,
        }

        if model == "openai/gpt-oss-120b":
            payload['max_tokens'] = 110_000

        max_retries = 3
        backoff_factor = 1

        for attempt in range(1, max_retries + 1):
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=MAX_TIMEOUT,
            )
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                error_code = result.get("error", {}).get("code")

                if error_code in (500, 429) and attempt < max_retries:
                    sleep_time = backoff_factor * (2 ** (attempt - 1))
                    logger.warning(
                        f"OpenRouter returned error {error_code}: (attempt {attempt}/{max_retries}). Retrying in {sleep_time}s..."
                    )
                    time.sleep(sleep_time)
                    continue
                else:
                    raise ValueError(
                        f"OpenRouter API error: {result.get('error')}"
                    )
            try:
                response_content = result["choices"][0]["message"]["content"]
                usage_data = result.get("usage", {})
                usage_metadata = {
                    "cost_usd": usage_data.get("cost") or None,
                    "input_tokens": usage_data.get("prompt_tokens") or None,
                    "output_tokens": usage_data.get("completion_tokens") or None,
                }
                break
            except KeyError as e:
                if attempt < max_retries:
                    sleep_time = backoff_factor * (2 ** (attempt - 1))
                    logger.warning(
                        f"Unexpected response format from OpenRouter (attempt {attempt}/{max_retries}). Retrying in {sleep_time}s... Error: {e}. Response: {result}"
                    )
                    time.sleep(sleep_time)
                    continue
                else:
                    raise ValueError(
                        f"Unexpected response format from OpenRouter API: {e}. Response: {result}"
                    )

        return response_content or "", usage_metadata


class GeminiProvider(AIProvider):
    NAME = "GEMINI"

    IMAGE_MATCH_MODEL = "gemini-2.5-flash"
    EXTRACT_MANY_PER_FILE_MODEL = "gemini-2.5-flash"
    EXTRACT_ONE_PER_FILE_MODEL = "gemini-2.5-flash-lite"
    EXTRACT_BLOCKS_MODEL = "gemini-2.5-flash"
    DEDUPLICATE_MODEL = "gemini-2.5-flash-lite"

    def __init__(self) -> None:
        super().__init__()
        self.client = genai.Client(api_key=self.api_key)

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
        return response.text or "", usage_metadata


