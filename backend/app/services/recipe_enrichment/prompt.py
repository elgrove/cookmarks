"""Prompt construction. Vocabulary comes first to permit provider prefix caching."""

import json

from app.services.recipe_enrichment.schema import PROMPT_VERSION

_INSTRUCTIONS = """You enrich one extracted recipe. Return only the JSON response.
For each line in the input, return an entry in i with the line id, singular UK-English canonical food name (n or null), and key ingredient flag (k).
Mark k true for one to three core ingredients that define the identity of the dish (such as the main protein, star vegetable, or signature flavour). Mark false for secondary, supporting, or seasoning ingredients.
If a line is a section heading, note, or contains no food ingredient, return null for n and false for k.
Always take the first ingredient when alternatives are listed.
Decide cuisines, methods, courses, and residual keywords using the recipe title, book title, author, instructions, and ingredients.
Methods are optional. Select a method only for a central, intentional cooking technique that defines the prepared dish. Set primary only on the one method that is most central to the dish; send no primary flag when no method qualifies.
Decide cuisines, methods and courses from the title and instructions before you choose keywords.
Use an available cuisine ID only when the dish is explicitly named for, or is unmistakably from, that cuisine.
Choose zero to five Title Case UK-English residual keywords. Include only useful keywords that add information not represented by a selected fact or canonical ingredient.

Wire keys: i list of {id: line ID, n: canonical name or null, k: key boolean}; c cuisine IDs; m methods {v ID, p primary}; o course IDs; w keywords."""


_STAGE1_INSTRUCTIONS = """You extract canonical food ingredient names from recipe ingredient lines. Return only valid JSON.
For each line in the input, return an entry in i with the line id and the singular UK-English canonical food name (n).
If a line is a section heading, note, or contains no food ingredient, return null for n.
Always take the first ingredient. If a line mentions alternatives (e.g. "butter or vegetable oil", "cooking spray or butter"), extract only the first mentioned ingredient ("butter", "cooking spray").
Do not extract quantities, units, or preparation methods.

For n:
- Singular UK-English canonical food name (e.g. `garlic`, `tofu`, `prawn`, `peanut`, `lime`, `aubergine`, `coriander`, `chilli`, `egg`, `spring onion`, `noodle`).
  * Use strictly British English (en-GB) vocabulary and spelling: write `chilli` never `chile` or `chili`, `coriander` never `cilantro`, `aubergine` never `eggplant`, `courgette` never `zucchini`, `spring onion` never `scallion` or `green onion`.
  * ALWAYS use strictly singular forms: write `egg` not `eggs`, `spring onion` not `spring onions`, `noodle` not `noodles`, `tomato` not `tomatoes`.
  * Exclude size adjectives (`large`, `small`, `medium`) and preparation/state adjectives (`roasted`, `baked`, `toasted`, `ground`, `steamed`, `peeled`, `crushed`, `chopped`, `diced`).
  * Preserve culinary specificity. Do not strip distinct varieties, products, or compound foods into generic parents: keep `plain flour` (not `flour`), `cheddar cheese` (not `cheese`), `madras curry powder` (not `curry powder`), `chicken stock` / `beef stock` (not `stock`), `mung bean sprout` (not `bean sprout`), `preserved sweet radish` (not `radish`), `vegetable oil` (not `oil`), `red pickled ginger` (not `ginger`), `red pepper` (not `pepper`).
  * Exclude units of measurement: `clove` is a unit of measurement, so extract `garlic` (never `garlic clove`).

Do not decide which ingredients are key. Stage 2 owns all recipe-level interpretation.

Wire keys: i list of {id: line ID, n: canonical ingredient name or null}."""

_STAGE2_INSTRUCTIONS = """You make recipe-level semantic decisions from extracted canonical ingredients and cooking instructions. Return only valid JSON.
Decide key ingredients, cuisines, cooking methods, courses, and residual keywords using the recipe title, book title, author, cooking instructions, and extracted ingredient list.

Key ingredients (k):
- Select one to three canonical ingredient names strictly from the supplied `ingredients` list that define the dish identity, such as the main protein, star vegetable, or signature flavour.
- Do not select seasoning, cooking oil, or a supporting ingredient.
- Every selected key ingredient MUST be an exact string from the supplied `ingredients` list.

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

Wire keys: k key ingredient names; c cuisine IDs; m methods {v ID, p primary}; o course IDs; w keywords."""


def build_stage1_prompt(context: dict) -> str:
    return "\n\n".join(
        [
            f"Recipe ingredient structuring prompt {PROMPT_VERSION}",
            _STAGE1_INSTRUCTIONS,
            "Recipe ingredient input:\n" + json.dumps(context["recipe"], ensure_ascii=False),
        ]
    )


def build_stage2_prompt(context: dict) -> str:
    return "\n\n".join(
        [
            f"Recipe facets prompt {PROMPT_VERSION}",
            _STAGE2_INSTRUCTIONS,
            "Reusable vocabulary:\n" + json.dumps(context["vocabulary"], ensure_ascii=False),
            "Recipe context:\n" + json.dumps(context["recipe"], ensure_ascii=False),
        ]
    )


def build_prompt(context: dict) -> str:
    return "\n\n".join(
        [
            f"Recipe enrichment prompt {PROMPT_VERSION}",
            _INSTRUCTIONS,
            "Reusable vocabulary:\n" + json.dumps(context["vocabulary"], ensure_ascii=False),
            "Recipe-specific input:\n" + json.dumps(context["recipe"], ensure_ascii=False),
        ]
    )
