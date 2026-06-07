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
from app.services.prompts import (
    BOOK_KEYWORDS_PROMPT,
    EXTRACT_RECIPES_PROMPT,
    IMAGE_MATCH_CHECK_PROMPT,
)

logger = logging.getLogger(__name__)

# Generous ceiling: a single block extraction can be a very large prompt.
MAX_TIMEOUT = 600

# Upper bound on book-level keywords kept from a generation, regardless of how many
# the model returns — book tags are a glance, not an index.
MAX_BOOK_KEYWORDS = 10

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
    BOOK_KEYWORDS = "book_keywords"


class EmbedTask(Enum):
    """What an embedding is for. Providers that distinguish (Gemini does) optimise
    the vector accordingly; the document and query sides of a search must agree."""

    DOCUMENT = "RETRIEVAL_DOCUMENT"
    QUERY = "RETRIEVAL_QUERY"


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


def _clean_keywords(raw: list[object], limit: int) -> list[str]:
    """Tidy a model's keyword list: keep non-empty strings, trim whitespace, drop
    case-insensitive duplicates (first spelling wins), and cap to `limit`."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        cleaned.append(name)
        if len(cleaned) >= limit:
            break
    return cleaned


class AIProvider(abc.ABC):
    """A pluggable AI backend. To add a provider: subclass this, set `name` and the
    `models` map, and implement `_complete`. The recipe-extraction and image-match
    helpers are shared so every provider behaves identically above the wire."""

    name: ClassVar[str]
    models: ClassVar[dict[ModelRole, str]]
    requires_api_key: ClassVar[bool] = True
    # Embedding capability. A provider that can embed sets both; the dimensions are
    # the vec0 table's fixed width, so they must match what's already stored.
    embedding_model: ClassVar[str | None] = None
    embedding_dimensions: ClassVar[int | None] = None

    def __init__(self, api_key: str, model_overrides: dict[str, str] | None = None) -> None:
        self.api_key = api_key
        # {ModelRole value: model name}; overrides the per-role default when present.
        self._model_overrides = model_overrides or {}

    @property
    def supports_embeddings(self) -> bool:
        return self.embedding_dimensions is not None

    def embed(self, text: str, task: EmbedTask) -> list[float]:
        """Embed one text into a vector. Raises if the provider can't embed."""
        raise NotImplementedError(f"{self.name} does not support embeddings")

    def embed_batch(self, texts: list[str], task: EmbedTask) -> list[list[float]]:
        """Embed many texts in one call. Raises if the provider can't embed."""
        raise NotImplementedError(f"{self.name} does not support embeddings")

    @abc.abstractmethod
    def _complete(
        self, prompt: str, model: str, *, schema: dict | None = None, temp: float = 0
    ) -> tuple[str, Usage]:
        """Run one completion and return (raw_text, usage). `schema` is a JSON schema
        the provider may use to constrain output; `temp` is the sampling temperature."""

    def model_for(self, role: ModelRole) -> str:
        return self._model_overrides.get(role.value) or self.models[role]

    def check_if_can_match_images(
        self, sample_content: str, model: str | None = None
    ) -> tuple[bool, Usage]:
        model = model or self.model_for(ModelRole.IMAGE_MATCH)
        prompt = IMAGE_MATCH_CHECK_PROMPT.format(sample_content=sample_content)
        response, usage = self._complete(prompt, model, temp=0)

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

    def generate_book_keywords(
        self, digest: str, model: str | None = None
    ) -> tuple[list[str], Usage]:
        """Generate book-level keywords (cuisine/theme/style) from a digest of the
        book's metadata and its recipes. Returns the cleaned, deduplicated names —
        an empty list if the model gives nothing usable."""
        model = model or self.model_for(ModelRole.BOOK_KEYWORDS)
        prompt = BOOK_KEYWORDS_PROMPT.format(digest=digest)
        response, usage = self._complete(prompt, model, temp=0)

        if not response:
            return [], usage

        try:
            raw = json.loads(_strip_json_fence(response))
        except json.JSONDecodeError:
            logger.error(f"Failed to decode book-keyword JSON from AI response:\n{response}")
            return [], usage

        if not isinstance(raw, list):
            logger.warning(f"Book-keyword response was not a JSON array: {raw!r}")
            return [], usage

        return _clean_keywords(raw, MAX_BOOK_KEYWORDS), usage
