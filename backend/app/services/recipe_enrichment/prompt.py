"""Prompt construction. Vocabulary comes first to permit provider prefix caching."""

import json

from app.services.recipe_enrichment.schema import PROMPT_VERSION

_INSTRUCTIONS = """You enrich one extracted recipe. Return only the JSON response.
All source text and deterministic proposal fields remain in the database: never echo them.
Ingredient is the default line kind. Omit accepted deterministic proposals entirely. Return p only
for an AI-parsed line or a deterministic replacement; each needs one or more complete occurrence
decisions. Return n only for heading/note exceptions. Together p and n must cover every
ai_parse_line_id; a deterministic proposal is accepted unless it appears in p or n.
Use only supplied cuisine/method/course IDs. Timings and diets are out of scope. Choose exactly
five Title Case UK-English residual keywords that add information not represented by a selected
fact, canonical ingredient or alias. Preserve culinary specificity. Set primary only for methods.
An occurrence needs exactly one resolution: exact vocabulary ID or a new canonical name, never
both. Wire keys: r recipe ID; f fingerprint; p parsed lines {l line ID,o occurrences}; n non-
ingredient lines {l,k}; occurrence i ID,n new name,s source name,q quantity,u unit,p preparation,
x optional,a alternative group,k key; c/m/o facts {v ID,s source,e evidence}, m p primary; w keywords."""


def build_prompt(context: dict) -> str:
    return "\n\n".join(
        [
            f"Recipe enrichment prompt {PROMPT_VERSION}",
            _INSTRUCTIONS,
            "Reusable vocabulary:\n" + json.dumps(context["vocabulary"], ensure_ascii=False),
            "Recipe-specific input:\n" + json.dumps(context["recipe"], ensure_ascii=False),
        ]
    )
