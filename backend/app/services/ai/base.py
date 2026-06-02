import abc
import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import ClassVar, TypeVar

from pydantic import ValidationError

from app.schemas.extraction import RecipeData
from app.services.prompts import EXTRACT_RECIPES_PROMPT, IMAGE_MATCH_CHECK_PROMPT

logger = logging.getLogger(__name__)

# Generous ceiling: a single block extraction can be a very large prompt.
MAX_TIMEOUT = 600

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "recipe_schema.json"
RECIPE_SCHEMA = json.loads(_SCHEMA_PATH.read_text())


class ModelRole(Enum):
    """The job a model is being asked to do. Each provider maps these roles to its
    own model names, so model selection is decoupled from the stored extraction
    method (file/block) and from any one provider's catalogue."""

    IMAGE_MATCH = "image_match"
    MANY_RECIPES_PER_FILE = "many_recipes_per_file"
    ONE_RECIPE_PER_FILE = "one_recipe_per_file"
    BLOCKS_OF_FILES = "blocks_of_files"


_Num = TypeVar("_Num", Decimal, int)


def _sum_optional(a: _Num | None, b: _Num | None) -> _Num | None:
    if a is None:
        return b
    if b is None:
        return a
    return a + b


@dataclass(frozen=True)
class Usage:
    """Token and cost accounting for one or more model calls. Each component is
    optional — None means 'not reported by the provider' and is preserved through
    accumulation, so adding usages never invents a zero where there was no datum."""

    cost_usd: Decimal | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            cost_usd=_sum_optional(self.cost_usd, other.cost_usd),
            input_tokens=_sum_optional(self.input_tokens, other.input_tokens),
            output_tokens=_sum_optional(self.output_tokens, other.output_tokens),
        )


def _strip_json_fence(text: str) -> str:
    """Strip a Markdown code fence some models wrap JSON in, despite instructions."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


class AIProvider(abc.ABC):
    """A pluggable AI backend. To add a provider: subclass this, set `name` and the
    `models` map, and implement `_complete`. The recipe-extraction and image-match
    helpers are shared so every provider behaves identically above the wire."""

    name: ClassVar[str]
    models: ClassVar[dict[ModelRole, str]]
    requires_api_key: ClassVar[bool] = True

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    @abc.abstractmethod
    def _complete(
        self, prompt: str, model: str, *, schema: dict | None = None, temp: float = 0
    ) -> tuple[str, Usage]:
        """Run one completion and return (raw_text, usage). `schema` is a JSON schema
        the provider may use to constrain output; `temp` is the sampling temperature."""

    def model_for(self, role: ModelRole) -> str:
        return self.models[role]

    def check_if_can_match_images(self, sample_content: str) -> tuple[bool, Usage]:
        prompt = IMAGE_MATCH_CHECK_PROMPT.format(sample_content=sample_content)
        response, usage = self._complete(prompt, self.model_for(ModelRole.IMAGE_MATCH), temp=0)

        if not response:
            logger.warning("Failed to check image matching, assuming no")
            return False, usage

        result = response.lower().strip().strip("\"'")
        if result not in ("yes", "no"):
            raise ValueError(f"Unexpected response '{response}'. Expected 'yes' or 'no'.")
        return result == "yes", usage

    def extract_recipes(self, content: str, model: str) -> tuple[list[RecipeData], Usage]:
        prompt = EXTRACT_RECIPES_PROMPT.format(schema=json.dumps(RECIPE_SCHEMA), content=content)
        response, usage = self._complete(prompt, model, schema=RECIPE_SCHEMA, temp=0)

        if not response:
            return [], usage

        try:
            raw_recipes = json.loads(_strip_json_fence(response))
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from AI response:\n{response}")
            return [], usage

        recipes: list[RecipeData] = []
        for i, recipe_data in enumerate(raw_recipes):
            try:
                recipes.append(RecipeData(**recipe_data))
            except ValidationError as e:
                logger.warning(f"Skipping invalid recipe at index {i}: {e}")
        return recipes, usage
