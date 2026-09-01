"""Prompt construction. Vocabulary comes first to permit provider prefix caching."""

import json

from app.services.recipe_enrichment.schema import PROMPT_VERSION

_INSTRUCTIONS = """You enrich one extracted recipe. Return only JSON matching the schema.
Classify every supplied line. Every ingredient line needs one or more resolved occurrences.
Use only supplied cuisine/method/course IDs. Timings and diets are out of scope.
Choose exactly five Title Case UK-English residual keywords. They must add information not
already represented by a selected fact, canonical ingredient or alias. Preserve culinary
specificity; do not turn a specific product into a generic parent ingredient. Set is_primary
only for a method. For a line in deterministic_proposals, set accept_deterministic to true
only when accepting that exact proposal, and then omit occurrences. For every ai_parse_line_id,
omit accept_deterministic and supply occurrences instead. An occurrence must contain exactly one
resolution: use ingredient_id only for an exact supplied vocabulary ID; otherwise use
canonical_name only, never both."""


def build_prompt(context: dict) -> str:
    return "\n\n".join(
        [
            f"Recipe enrichment prompt {PROMPT_VERSION}",
            _INSTRUCTIONS,
            "Reusable vocabulary:\n" + json.dumps(context["vocabulary"], ensure_ascii=False),
            "Recipe-specific input:\n" + json.dumps(context["recipe"], ensure_ascii=False),
        ]
    )
