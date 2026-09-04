"""Prompt construction. Vocabulary comes first to permit provider prefix caching."""

import json

from app.services.recipe_enrichment.schema import PROMPT_VERSION

_INSTRUCTIONS = """You enrich one extracted recipe. Return only the JSON response.
Ingredient is the default line kind. Return p only for an ingredient line listed in ai_parse_line_ids;
each needs one or more complete occurrence decisions. Return n only for heading/note exceptions.
Together p and n must cover every ai_parse_line_id.
Before you return JSON, count p and n together: they must contain exactly one decision for every
listed ai_parse_line_id. These are opaque IDs: copy each supplied ID exactly once, even for
repeated ingredients, headings, or unmeasured food lines. Do not invent, shorten, or omit an ID.
Keep every value to the shortest useful source fragment; do not repeat input text or list
alternatives twice.
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
Mark k true for one to three core ingredients that define the identity of the dish (such as the
main protein, star vegetable, or signature flavour). Mark false for secondary, supporting, or
seasoning ingredients.

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

Wire keys: p parsed lines {l line ID,o occurrences}; n non-ingredient lines {l,k}; occurrence n canonical name,q quantity,u unit,p preparation,x optional,a alternative group,k key; c cuisine IDs; m methods {v ID,p primary}; o course IDs; w keywords."""


_STAGE1_INSTRUCTIONS = """You structure recipe ingredient lines into parsed components. Return only valid JSON.
Ingredient is the default line kind. Return p for each ingredient line listed in ai_parse_line_ids;
each needs one or more complete occurrence decisions. Return n only for heading/note exceptions.
Together p and n must cover every ai_parse_line_id exactly once.

Line ID contract:
- The l field must be the exact opaque ID string from ai_parse_line_ids (e.g. "894d5968-c679-5cbf-9c6c-5e99843f01d1").
- NEVER use line text or section names as the l value.
- NEVER invent new IDs or extra lines that are not listed in ai_parse_line_ids.

In n:
- k must be exactly `heading` or `note`.
- Use `heading` only when an existing supplied line is a section label.
- Use `note` for a serving suggestion, table condiment recommendation, or open-ended comment rather than a measured ingredient food item.
- Any line that names a specific measured food item is an ingredient (p).

For every occurrence in p:
- Exactly ONE occurrence per ingredient item.
  * When a line lists dual imperial and metric measurements (such as '6 ounces (170 g)' or '¼ cup (60 ml)'), output ONLY ONE occurrence using the FIRST stated measurement ('q: 6', 'u: oz'). NEVER create duplicate occurrences for metric conversions in parentheses.
- n: singular UK-English canonical food name (e.g. `garlic`, `tofu`, `shrimp`, `peanut`, `lime`, `aubergine`, `coriander`, `chilli`, `egg`, `spring onion`, `noodle`).
  * Use strictly British English (en-GB) vocabulary and spelling: write `chilli` never `chile` or `chili`, `coriander` never `cilantro`, `aubergine` never `eggplant`, `courgette` never `zucchini`, `spring onion` never `scallion` or `green onion`.
  * ALWAYS use strictly singular forms: write `egg` not `eggs`, `spring onion` not `spring onions`, `noodle` not `noodles`, `tomato` not `tomatoes`.
  * Size adjectives (`large`, `small`, `medium`) and preparation/state adjectives (`roasted`, `baked`, `toasted`, `ground`, `steamed`, `peeled`, `crushed`) belong in `p` (preparation), NOT in `n`.
  * Preserve culinary specificity. Do not strip distinct varieties, products, or compound foods into generic parents: keep `plain flour` (not `flour`), `cheddar cheese` (not `cheese`), `madras curry powder` (not `curry powder`), `chicken stock` / `beef stock` (not `stock`), `mung bean sprout` (not `bean sprout`), `preserved sweet radish` (not `radish`), `vegetable oil` (not `oil`), `red pickled ginger` (not `ginger`), `red pepper` (not `pepper`).
  * Specific food forms like `fillet`, `breast`, `thigh` are part of the name (e.g. `yellowtail fillet`, `chicken breast`).
  * `clove` is a unit of measurement (u: `clove`), NOT part of the food name: output n: `garlic`, u: `clove` (never `garlic clove`).
  * Examples: 'large shrimp, peeled' -> n: `shrimp`, p: `large, peeled`; 'roasted peanuts' -> n: `peanut`, p: `roasted`; 'baked tofu' -> n: `tofu`, p: `baked`; 'lime wedges' -> n: `lime`, p: `wedges`; 'garlic cloves' -> n: `garlic`, u: `clove`; '4 eggs' -> n: `egg`, q: `4`.
- q: first stated quantity (e.g. `1`, `2 1/2`, `200`, `2 to 3`). Keep compound amounts like `1 tbsp plus 2 tsp` intact.
- u: common unit abbreviation (`tsp`, `tbsp`, `cup`, `g`, `kg`, `ml`, `litre`, `oz`, `lb`, `clove`, `pinch`).
- p: preparation actions and descriptors (`chopped`, `diced`, `peeled`, `toasted`, `baked`, `roasted`, `to taste`, `for serving`).
- x: true only when source explicitly states optional.
- a: integer alternative group (`0`, `1`...) for either/or choices on the same line.
  * When a line offers choices joined by 'or' (e.g. 'palm sugar or dark brown sugar'; 'chicken or beef stock, or dashi'; 'ketchup or tonkatsu sauce'; 'sweetcorn cob, or tinned sweetcorn'), output one occurrence for EACH distinct alternative ingredient with the SAME `a` value (e.g. `a: 0`).
- k: true for 1 to 3 core star ingredients that define the dish identity (e.g. main protein, key vegetable, star flavour). False for seasoning, oil, or supporting ingredients.

Wire keys: p parsed lines {l line ID, o occurrences}; n non-ingredient lines {l, k}; occurrence {n canonical name, q quantity, u unit, p preparation, x optional, a alternative group, k key}."""

_STAGE2_INSTRUCTIONS = """You classify recipe facets and select descriptive residual keywords. Return only valid JSON.
Decide cuisines, cooking methods, and courses using the recipe title, book title, author, cooking instructions, and ingredients list.

Cuisines (c):
- Select zero or more matching IDs strictly from the supplied `cuisines` list.
- Every selected cuisine MUST be an exact string from the supplied `cuisines` list (e.g. `afghan`, not `afghanistan`). Any value not in the list is invalid.
- Select a cuisine ID only when the dish is explicitly named for, or unmistakably from, that culinary tradition.
- General Western home baking (such as plain cakes, cookies, quick breads) without specific national tradition should have NO cuisine (c: []).

Methods (m):
- Select zero or more matching IDs strictly from the supplied `methods` list.
- Select a method only for a central, intentional cooking technique that defines the prepared dish (e.g. bake, grill, simmer, fry, roast, stir-fry).
- Teriyaki and cooking fish, meat, or vegetables in oil in a skillet or pan on the stovetop is `fry` (pan-fry), NOT `sear`. Do NOT select `sear` for pan-fried fish or meat.
- For soups, stews, curries, and braises where a sauce, broth, or dish cooks gently on the stove, the primary method is `simmer` (not `boil` or `fry`).
- Initial softening, sautéing, or frying of base aromatics (such as onions, garlic, shallots, spices, or ginger) or browning/searing protein in a pan or pot before simmering or making a soup/stew is part of `simmer` or `boil`, NOT an independent `fry` or `sear` method.
- In a stir-fry, all wok cooking actions are part of `stir-fry`—do not add `sear`, `fry`, or `boil` for soaking/blanching noodles.
- For boiled noodles, pasta, or boiling in a pot of water/broth, include `boil` or `simmer`.
- For baked desserts and cakes, the central method is `bake`. Do not select `sear` or `fry` for stove-top melting or browning of butter.
- Do not select a method for incidental handling, intermediate prep, or sub-components (chopping, mixing, resting, assembling, serving).
- Set primary (p: true) on at most ONE method that is most central to the dish.

Courses (o):
- Select zero or more matching IDs strictly from the supplied `courses` list (breakfast, brunch, starter, main, side, dessert, snack, drink, component).
- Select only the primary intended role for the dish. Do not add `side` to an unambiguous main dish.

Residual Keywords (w):
- Choose zero to five Title Case UK-English keywords (e.g. `Sweet-Sour`, `Street Food`, `Layered`, `Sponge`, `Comfort Food`, `Warming`, `Picnic`).
- Keywords must add information NOT already present in selected cuisines, methods, courses, or ingredient names.
- Do NOT repeat any cuisine, method, course, or ingredient name in keywords.
- Do not add filler keywords.

Wire keys: c cuisine IDs; m methods {v ID, p primary}; o course IDs; w keywords."""


def build_stage1_prompt(context: dict) -> str:
    return "\n\n".join(
        [
            f"Recipe ingredient structuring prompt {PROMPT_VERSION}",
            _STAGE1_INSTRUCTIONS,
            "Recipe ingredient input:\n"
            + json.dumps(context["recipe"], ensure_ascii=False),
        ]
    )


def build_stage2_prompt(context: dict) -> str:
    return "\n\n".join(
        [
            f"Recipe facets prompt {PROMPT_VERSION}",
            _STAGE2_INSTRUCTIONS,
            "Reusable vocabulary:\n"
            + json.dumps(context["vocabulary"], ensure_ascii=False),
            "Recipe context:\n"
            + json.dumps(context["recipe"], ensure_ascii=False),
        ]
    )


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
