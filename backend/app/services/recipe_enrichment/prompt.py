"""Prompt construction. Vocabulary comes first to permit provider prefix caching."""

import json

from app.services.recipe_enrichment.schema import PROMPT_VERSION

_INSTRUCTIONS = """You enrich one extracted recipe. Return only the JSON response.
For each line in the input, return an entry in i with the line id, singular UK-English canonical food name (n or null), and key ingredient flag (k). Never extract salt or pepper (return null for n); strip redundant nationality prefixes from common staples (write `wheat flour noodle` never `Chinese wheat flour noodle`).
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
  * Never extract salt or pepper: return null for n on lines that specify salt, black pepper, white pepper, or universal seasoning (e.g. `salt`, `sea salt`, `kosher salt`, `table salt`, `flaked salt`, `Maldon salt`, `Himalayan pink salt`, `fleur de sel`, `black pepper`, `white pepper`, `peppercorn`, `freshly ground black pepper`, `salt and black pepper`). Salt and pepper are present in virtually all food and must never be extracted as canonical ingredients. Distinct culinary spices like `Sichuan pepper`, `cayenne pepper`, and `chilli`, distinct specialty salts like `kala namak` (black salt), `smoked salt`, or `celery salt`, and sweet/bell peppers (e.g. `peppers`, `bell pepper`, `red pepper`, `green pepper`, `sweet pepper`) are NOT table seasonings and must be kept.
  * Use strictly British English (en-GB) vocabulary and spelling: write `chilli` never `chile` or `chili`, `coriander` never `cilantro`, `aubergine` never `eggplant`, `courgette` never `zucchini`, `spring onion` never `scallion` or `green onion`.
  * ALWAYS use strictly singular forms: write `egg` not `eggs`, `spring onion` not `spring onions`, `noodle` not `noodles`, `tomato` not `tomatoes`.
  * Exclude size adjectives (`large`, `small`, `medium`) and preparation/state adjectives (`roasted`, `baked`, `toasted`, `ground`, `steamed`, `peeled`, `crushed`, `chopped`, `diced`).
  * Strip redundant nationality and regional prefixes from common staples when they denote origin rather than a fundamentally distinct food item:
    - Write `wheat flour noodle` (never `Chinese wheat flour noodle` or `Japanese wheat flour noodle`), `egg noodle` (not `Chinese egg noodle`), `rice vermicelli` (not `Chinese rice vermicelli`), `plum tomato` (not `Italian plum tomato`), `dark soy sauce` (not `Chinese dark soy sauce`), `white rice` (not `Chinese white rice`).
    - If a staple has a recognised specific variety name, use the variety name without the nationality prefix: write `udon noodle` (not `Japanese udon noodle`), `soba noodle` (not `Japanese soba noodle`), `basmati rice` (not `Indian basmati rice`).
    - KEEP regional or nationality prefixes ONLY when they designate a protected origin, a distinct regional specialty, or a culinarily distinct variety with no generic equivalent: `Shaoxing wine` (or `Shaoxing rice wine`), `Dijon mustard`, `English mustard`, `Parmesan`, `Kalamata olive`, `Chinese five-spice`, `Chinese chive`, `Chinese cabbage`.
  * Preserve culinary specificity. Do not strip distinct varieties, products, or compound foods into generic parents: keep `plain flour` (not `flour`), `cheddar cheese` (not `cheese`), `madras curry powder` (not `curry powder`), `chicken stock` / `beef stock` (not `stock`), `mung bean sprout` (not `bean sprout`), `preserved sweet radish` (not `radish`), `vegetable oil` (not `oil`), `red pickled ginger` (not `ginger`), `red pepper` (not `pepper`), `sweet pepper` (not `pepper`). When an ingredient line lists sweet peppers (e.g. "peppers", "sweet peppers", "peppers (red, yellow or green)"), extract the vegetable name (e.g. `pepper`, `red pepper`, `green pepper`) — sweet peppers are culinary vegetables, not table pepper seasoning.
  * Exclude units of measurement: `clove` is a unit of measurement, so extract `garlic` (never `garlic clove`).

Do not decide which ingredients are key. Stage 2 owns all recipe-level interpretation.

Wire keys: i list of {id: line ID, n: canonical ingredient name or null}."""

_STAGE2_INSTRUCTIONS = """You make recipe-level semantic decisions from extracted canonical ingredients and cooking instructions. Return only valid JSON.
Decide key ingredients, cuisines, cooking methods, courses, residual keywords, alternate name, and summary using the recipe title, book title, author, cooking instructions, and extracted ingredient list.

Key ingredients (k):
- Select one to three canonical ingredient names strictly from the supplied `ingredients` list that define the dish identity, such as the main protein, star vegetable, or signature flavour.
- Do not select seasoning, cooking oil, or a supporting ingredient.
- Every selected key ingredient MUST be an exact string from the supplied `ingredients` list.
- NEVER invent, infer, or select an ingredient (even if mentioned in the recipe title, description, or instructions) that is not in the supplied `ingredients` list. If a dish component (such as labneh, pastry, stock, or dressing) is prepared from scratch in the instructions rather than listed as an ingredient, you must select from the actual base ingredients supplied.
- Select at most three key ingredients. You MUST select between 1 and 3 items only; returning 4 or more items is strictly forbidden.

Cuisines (c):
- Select zero or more matching IDs strictly from the supplied `cuisines` list.
- Every selected cuisine MUST be an exact string from the supplied `cuisines` list (e.g. `afghan`, not `afghanistan`). Any value not in the list is invalid.
- NEVER invent or select a region, province, or city name (such as `shanghai`, `sichuan`, or `cantonese`) that is not present in the supplied `cuisines` list.
- Do not repeat cuisine IDs.
- Select a cuisine ID only when the dish is explicitly named for, or unmistakably from, that culinary tradition.
- General Western home baking (such as plain cakes, cookies, quick breads) without specific national tradition should have NO cuisine (c: []).

Methods (m):
- Select zero or more matching IDs strictly from the supplied `methods` list.
- Do not repeat method IDs.
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
- Do not repeat course IDs.
- Select only the primary intended role for the dish. Do not add `side` to an unambiguous main dish.

Residual Keywords (w):
- Choose zero to five Title Case UK-English keywords (e.g. `Sweet-Sour`, `Street Food`, `Layered`, `Sponge`, `Comfort Food`, `Warming`, `Picnic`).
- Keywords must add information NOT already present in selected cuisines, methods, courses, or ingredient names.
- Do NOT repeat any cuisine, method, course, or ingredient name in keywords.
- Do not add filler keywords.

Title descriptor decision (a and s):
- Return exactly one descriptor outcome. Never return both 'a' and 's'.
- Literal native-language description: if the title directly names ordinary food, ingredients, or a dish form in its native language and its English translation makes the dish self-descriptive, return that translation in Title Case UK-English as 'a'; set 's' to null. This is not a named dish. Examples: "Bharli Mirchi" -> a: "Stuffed Chillies", s: null; "Mouna Au Lait" -> a: "Milk Bread", s: null; "Patl\u0131can Biber Tavas\u0131 Yo\u011furtlu Sarm\u0131sakl\u0131 Ve Domates Soslu" -> a: "Fried Aubergine and Pepper with Tomato and Garlic Yoghurt Sauce", s: null.
- Named cultural dish, opaque title, or generic translation: if the title is a conventional dish name, regional name, loanword, or its literal English translation would still be too generic to explain the dish, set 'a' to null and provide 's'. Never translate a named dish word by word. Examples: "Bhel Puri" -> a: null, s: "Puffed rice with tamarind chutney"; "Gazpacho" -> a: null, s: "Chilled tomato and pepper soup"; "Pomodori Fritti" -> a: null, s: "Fried tomato slices with cornmeal crust".
- Self-descriptive English title: if the English title already tells the reader what food it is and its defining ingredient or sauce, set both 'a' and 's' to null. A simple cooking-method word does not make a title opaque. Examples: "Pickled Pears With Thyme, Chilli & Coriander", "Greek Breads With Green Onions", "Courgette Noodles With Callaloo Pesto", and "Simmered Mackerel With Radish".

Summary style (s):
- A cold, food-first descriptor of 3 to 12 words. It is a label, not a sentence: do not add a full stop.
- State only the food and its primary component or sauce. Do not describe the method, serving details, garnish, or extra ingredients unless needed to identify the food.
- For noodle dishes, name the noodle type or base grain, not the cooking method.
- Select details from the cooked dish, not from optional serving items. Prefer a defining herb, chilli, or sauce component over cheese, mayonnaise, lime, or other garnish.
- For a named sauce, include its colour and the one or two ingredients that distinguish it. Use a preparation word only when it identifies the dish form, such as a layered dish.
- Always provide a summary for:
  * Named cultural dishes, regional styles, and loanwords whose preparation is not obvious from English words (e.g. "Shakshuka", "Spanakopita", "Goulash", "Bouillabaisse", "Caponata", "Bibimbap", "Lentil Puris", "Elote").
  * Dishes named after a culinary style, glaze, or sauce (e.g. dishes featuring "Teriyaki", "Adobo", "Tikka", "Kung Pao", "Mole").
  * Dishes that combine an English ingredient with an obscure regional dish style (e.g. "Chicken Cafreal").
  * Regional noodle soups and noodle dishes (e.g. "Laksa", "Khao Soi", "Dan Dan Noodles").
  * Dishes whose title combines a foreign name and an English translation, but the dish is a complex regional preparation (e.g. "Hong Shao Rou (Red-braised Pork Belly)").
- Familiarity is not a reason to set summary to null. A named cultural dish or loanword always needs a summary.
- Style: Never start with "A" or "An". Describe the food directly, without praise or decorative language. Stop after the essential food components.
- FORBIDDEN WORDS: NEVER use any of these words or phrases in 's': "spiced", "ground", "coated", "with spices", "until tender", "rich", "deep", "complex", "classic", "fresh", "crisp", "creamy", "fragrant", "vibrant", "delicate", "luscious", "aromatic", "warming", "luxurious", "silky", "tender", "golden", "finished".

Wire keys: k key ingredient names; c cuisine IDs; m methods {v ID, p primary}; o course IDs; w keywords; a alternate name or null; s summary or null."""


def build_stage1_prompt(context: dict) -> str:
    return "\n\n".join(
        [
            f"Recipe ingredient structuring prompt {PROMPT_VERSION}",
            _STAGE1_INSTRUCTIONS,
            "Recipe ingredient input:\n" + json.dumps(context["recipe"], ensure_ascii=False),
        ]
    )


def build_stage2_prompts(context: dict) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for Stage 2."""
    system = "\n\n".join(
        [
            f"Recipe facets prompt {PROMPT_VERSION}",
            _STAGE2_INSTRUCTIONS,
            "Reusable vocabulary:\n" + json.dumps(context["vocabulary"], ensure_ascii=False),
        ]
    )
    user = (
        "Recipe context:\n"
        + json.dumps(context["recipe"], ensure_ascii=False)
        + "\n\nEnrich this recipe with key ingredients (1-3), cuisines, methods, courses, residual keywords, alternate name (a), and summary (s).\n"
        + "- Apply the title descriptor decision exactly: a literal native-language description gets English translation in \"a\" and null \"s\"; a named cultural dish or opaque title gets null \"a\" and a food-first \"s\"; a self-descriptive English title gets null for both.\n"
        + "- Do not translate a named dish word by word. Never return both \"a\" and \"s\"."
    )
    return system, user


def build_stage2_prompt(context: dict) -> str:
    system, user = build_stage2_prompts(context)
    return f"{system}\n\n{user}"


def build_prompt(context: dict) -> str:
    return "\n\n".join(
        [
            f"Recipe enrichment prompt {PROMPT_VERSION}",
            _INSTRUCTIONS,
            "Reusable vocabulary:\n" + json.dumps(context["vocabulary"], ensure_ascii=False),
            "Recipe-specific input:\n" + json.dumps(context["recipe"], ensure_ascii=False),
        ]
    )
