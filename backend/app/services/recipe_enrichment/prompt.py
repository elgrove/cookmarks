"""Prompt construction. Vocabulary comes first to permit provider prefix caching."""

import json

from app.services.recipe_enrichment.schema import PROMPT_VERSION

_INSTRUCTIONS = """You enrich one extracted recipe. Return only the JSON response.
All source text and deterministic proposal fields remain in the database: never echo them.
Ingredient is the default line kind. Omit accepted deterministic proposals entirely. Return p only
for an AI-parsed line or a deterministic replacement; each needs one or more complete occurrence
decisions. Return n only for heading/note exceptions. Together p and n must cover every
ai_parse_line_id; a deterministic proposal is accepted unless it appears in p or n.
Before you return JSON, count p and n together: they must contain exactly one decision for every
listed ai_parse_line_id. These are opaque IDs: copy each supplied ID exactly once, even for
repeated ingredients, headings, or unmeasured food lines. Do not invent, shorten, or omit an ID.
Keep every value to the shortest useful source fragment; do not repeat input text, list
alternatives twice, or add explanations outside fact evidence.
In n, k must be exactly `heading` or `note`: no other value is valid. Use `heading` only for a
short ingredient-list section label. Use `note` for a serving suggestion or an open-ended comment
that is not a measured ingredient. A line that names a food remains an ingredient even when it is
optional, has no quantity, or is served at the table. Do not classify a food item as a note.
Use only supplied cuisine/method/course IDs. Timings and diets are out of scope. Choose zero to
five Title Case UK-English residual keywords. Include only useful keywords that add information
not represented by a selected fact, canonical ingredient or alias. Do not add filler keywords.
Preserve culinary specificity.

For every occurrence, output n with one singular UK-English canonical ingredient name. There is
no ingredient ID field. The application resolves n to an existing canonical ingredient or alias
locally, or creates it when it is genuinely new.

For q and u, retain the first stated quantity and unit; do not convert measurements. When a line
shows metric and imperial measures, use the first pair. Use common unit abbreviations: tsp, tbsp,
cup, g, kg, ml, litre, oz, lb, clove and pinch. Put preparation, such as peeled, chopped or
toasted, in p. Preserve a specific ingredient identity: do not turn a named variety, product or
prepared ingredient into a generic parent. Mark x true only when the source explicitly says it is
optional. For an either/or ingredient line, return one occurrence for each choice with the same a
value. Preserve compound quantities and ranges exactly, such as `1 tbsp plus 2 tsp` or `2 to 3`;
do not split them. Put `to taste` and a serving form such as `wedges` in p. Do not use an
alternative group for an ingredient with several descriptive words.

Methods are optional. Select a method only for a central, intentional cooking technique that
defines the prepared dish. Do not select a method for incidental preparation or handling such as
chopping, slicing, mixing, whisking, seasoning, drying, arranging, or serving. Set primary only
on the one method that is most central to the dish; send no primary flag when no method qualifies.

Decide cuisines, methods and courses from the title and instructions before you choose keywords.
Use an available cuisine ID only when the dish is explicitly named for, or is unmistakably from,
that cuisine. Choose a course ID when the recipe clearly serves as one. A named cuisine, method,
course, canonical ingredient, or close alias must not also be a residual keyword. When cooking
actions include both a central technique and incidental actions, report only the central technique.
The c list accepts only IDs from the supplied cuisine list, m only IDs from the method list, and o
only IDs from the course list. Never put a course such as `starter` in c or a method in either c
or o.
For every selected fact, set s to explicit only when the source states it directly; otherwise set
s to inferred. Give e the shortest supporting phrase copied verbatim from the recipe title, yield,
description or instructions. It must be one contiguous fragment of at most 12 words and 120
characters. Do not paraphrase, normalise, or join fragments. If you cannot copy supporting source
text exactly, omit the fact. Never use external culinary knowledge or an explanation in e.

Wire keys: r recipe ID; f fingerprint; p parsed lines {l line ID,o occurrences}; n non-
ingredient lines {l,k}; occurrence n canonical name,s source name,q quantity,u unit,p preparation,
x optional,a alternative group,k key; c/m/o facts {v ID,s source,e evidence}, m p primary; w keywords."""


def build_prompt(context: dict) -> str:
    return "\n\n".join(
        [
            f"Recipe enrichment prompt {PROMPT_VERSION}",
            _INSTRUCTIONS,
            "Reusable vocabulary:\n"
            + json.dumps(context["vocabulary"], ensure_ascii=False),
            "Recipe-specific input:\n"
            + json.dumps(context["recipe"], ensure_ascii=False),
        ]
    )
