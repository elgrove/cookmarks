import hashlib
import json
from decimal import Decimal
from typing import ClassVar

from app.services.ai.base import AIProvider, ModelRole, Usage
from app.services.prompts import DEDUPLICATE_KEYWORDS_PROMPT, IMAGE_MATCH_CHECK_PROMPT


class StubProvider(AIProvider):
    """Deterministic, offline provider for tests and local development: no network
    and no API key. It routes by prompt prefix and returns a single synthetic
    recipe whose name varies with the prompt, so distinct chapters/blocks don't
    collapse to one under title deduplication."""

    name = "STUB"
    requires_api_key = False
    models: ClassVar[dict[ModelRole, str]] = {
        ModelRole.IMAGE_MATCH: "stub-vision",
        ModelRole.MANY_RECIPES_PER_FILE: "stub-extract",
        ModelRole.ONE_RECIPE_PER_FILE: "stub-extract",
        ModelRole.BLOCKS_OF_FILES: "stub-extract",
    }

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

        suffix = hashlib.blake2b(prompt.encode("utf-8"), digest_size=4).hexdigest()
        recipe = {
            "name": f"Stub Recipe {suffix}",
            "description": "Synthetic recipe produced by StubProvider for offline dev.",
            "recipeIngredients": ["1 cup stub flour", "2 stub eggs"],
            "recipeInstructions": ["Combine ingredients.", "Cook until done."],
            "recipeYield": "Serves 4",
            "keywords": ["Stub", "Dev"],
        }
        return json.dumps([recipe]), usage
