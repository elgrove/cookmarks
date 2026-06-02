"""Gold and predicted recipes, reduced to one comparable shape.

`EvalRecipe` is the lightweight, app-free structure the scoring layer operates on.
Gold files use plain keys (``ingredients``); pipeline output uses schema.org aliases
(``recipeIngredients``). `to_eval_recipe` accepts either, so both sides score alike.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class EvalRecipe:
    name: str
    ingredients: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    yields: str | None = None
    image: str | None = None
    keywords: list[str] = field(default_factory=list)


def _first_str(d: dict, *keys: str) -> str | None:
    for key in keys:
        value = d.get(key)
        if value:
            return str(value)
    return None


def _first_list(d: dict, *keys: str) -> list[str]:
    for key in keys:
        value = d.get(key)
        if value:
            return [str(item) for item in value]
    return []


def to_eval_recipe(d: dict) -> EvalRecipe:
    """Build an EvalRecipe from a gold or predicted dict, tolerating both key styles."""
    return EvalRecipe(
        name=(_first_str(d, "name") or ""),
        ingredients=_first_list(d, "ingredients", "recipeIngredients"),
        instructions=_first_list(d, "instructions", "recipeInstructions"),
        yields=_first_str(d, "yields", "recipeYield"),
        image=_first_str(d, "image"),
        keywords=_first_list(d, "keywords"),
    )


def load_gold(path: Path) -> list[EvalRecipe]:
    return [to_eval_recipe(r) for r in json.loads(path.read_text())]


def from_predicted(raw_recipes: list[dict]) -> list[EvalRecipe]:
    return [to_eval_recipe(r) for r in raw_recipes]
