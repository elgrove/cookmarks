import hashlib
import json
from decimal import Decimal
from typing import ClassVar

from app.services.ai.base import AIProvider, EmbedTask, ModelRole, Usage
from app.services.prompts import (
    BOOK_KEYWORDS_PROMPT,
    DEDUPLICATE_KEYWORDS_PROMPT,
    IMAGE_MATCH_CHECK_PROMPT,
)


def _hash_vector(text: str, dim: int) -> list[float]:
    """A deterministic pseudo-random vector for `text`: identical text yields an
    identical vector (so a query equal to a document is distance 0), different text
    diverges. No semantic meaning — enough to exercise the vec0 search path offline."""
    out: list[float] = []
    counter = 0
    while len(out) < dim:
        digest = hashlib.blake2b(f"{text}:{counter}".encode(), digest_size=64).digest()
        for i in range(0, len(digest), 4):
            if len(out) >= dim:
                break
            out.append(int.from_bytes(digest[i : i + 4], "big") / 0xFFFFFFFF * 2 - 1)
        counter += 1
    return out


class StubProvider(AIProvider):
    """Deterministic, offline provider for tests and local development: no network
    and no API key. It routes by prompt prefix and returns a single synthetic
    recipe whose name varies with the prompt, so distinct chapters/blocks don't
    collapse to one under title deduplication."""

    name = "STUB"
    requires_api_key = False
    models: ClassVar[dict[ModelRole, str]] = {
        ModelRole.IMAGE_MATCH: "stub-vision",
        ModelRole.OCR: "stub-vision",
        ModelRole.MANY_RECIPES_PER_FILE: "stub-extract",
        ModelRole.ONE_RECIPE_PER_FILE: "stub-extract",
        ModelRole.BLOCKS_OF_FILES: "stub-extract",
        ModelRole.BOOK_KEYWORDS: "stub-keywords",
        ModelRole.KEYWORD_DEDUP: "stub-dedup",
        ModelRole.ASSISTANT: "stub-assistant",
        ModelRole.RECIPE_ENRICHMENT: "stub-enrichment",
    }
    # Matches the production (Gemini) width so stub vectors share the vec0 table.
    embedding_dimensions: ClassVar[int] = 3072
    vision_model: ClassVar[str] = "stub-vision"

    def _complete(
        self, prompt: str, model: str, *, schema: dict | None = None, temp: float = 0
    ) -> tuple[str, Usage]:
        usage = Usage(cost_usd=Decimal("0"), input_tokens=0, output_tokens=0)

        if prompt.startswith(IMAGE_MATCH_CHECK_PROMPT[:40]):
            return "yes", usage

        if prompt.startswith(DEDUPLICATE_KEYWORDS_PROMPT[:40]):
            # Echo each keyword as its own canonical form: no merging.
            keywords = json.loads(prompt[prompt.rfind("[") : prompt.rfind("]") + 1])
            return json.dumps({k: k for k in keywords}), usage

        if prompt.startswith(BOOK_KEYWORDS_PROMPT[:40]):
            # Deterministic book tags that vary per book, so distinct books get
            # distinct keyword sets offline. A shared term ("Cookbook") plus a
            # per-book token exercises the shared-vocabulary join either way.
            token = hashlib.blake2b(prompt.encode("utf-8"), digest_size=3).hexdigest()
            return json.dumps(["Cookbook", "Stub Cuisine", f"Theme {token}"]), usage

        if prompt.startswith("Recipe ingredient structuring prompt"):
            recipe = json.loads(prompt.rsplit("Recipe ingredient input:\n", 1)[1])
            parsed_lines = []
            token = recipe["id"].split("-")[0]
            for index, line in enumerate(recipe["lines"], start=1):
                parsed_lines.append(
                    {
                        "l": line["id"],
                        "o": [
                            {"canonical_name": f"Stub Ingredient {token} {index}", "is_key": False}
                        ],
                    }
                )
            return json.dumps({"p": parsed_lines}), usage

        if prompt.startswith("Recipe facets prompt"):
            return json.dumps(
                {
                    "c": [],
                    "m": [],
                    "o": [],
                    "w": ["Cosy", "Fresh", "Outdoor", "Summer", "Weeknight"],
                }
            ), usage

        if prompt.startswith("Recipe enrichment prompt"):
            recipe = json.loads(prompt.rsplit("Recipe-specific input:\n", 1)[1])
            parsed_lines = []
            token = recipe["id"].split("-")[0]
            for index, line in enumerate(recipe["lines"], start=1):
                parsed_lines.append(
                    {
                        "l": line["id"],
                        "o": [
                            {"canonical_name": f"Stub Ingredient {token} {index}", "is_key": False}
                        ],
                    }
                )
            return json.dumps(
                {
                    "p": parsed_lines,
                    "w": ["Cosy", "Fresh", "Outdoor", "Summer", "Weeknight"],
                }
            ), usage

        suffix = hashlib.blake2b(prompt.encode("utf-8"), digest_size=4).hexdigest()
        recipe = {
            "name": f"Stub Recipe {suffix}",
            "description": "Synthetic recipe produced by StubProvider for offline dev.",
            "recipeIngredients": [{"text": "1 cup stub flour"}, {"text": "2 stub eggs"}],
            "recipeInstructions": ["Combine ingredients.", "Cook until done."],
            "recipeYield": "Serves 4",
            "keywords": ["Stub", "Dev"],
        }
        return json.dumps([recipe]), usage

    def embed(self, text: str, task: EmbedTask) -> list[float]:
        return _hash_vector(text, self.embedding_dimensions)

    def read_page(
        self, image: bytes, media_type: str, model: str | None = None
    ) -> tuple[str, Usage]:
        token = hashlib.blake2b(image, digest_size=4).hexdigest()
        return f"Stub cookbook page {token}", Usage(
            cost_usd=Decimal("0"), input_tokens=0, output_tokens=0
        )

    def embed_batch(self, texts: list[str], task: EmbedTask) -> list[list[float]]:
        return [_hash_vector(text, self.embedding_dimensions) for text in texts]
