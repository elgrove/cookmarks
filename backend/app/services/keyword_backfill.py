"""Derive flat recipe keywords from the retained enrichment facts."""

import json
from dataclasses import dataclass
from pathlib import Path

from app.models.enums import RecipeFacetKind
from app.models.recipe import Recipe
from app.text import fold

_CUISINE_LABELS = Path(__file__).parent.parent / "data" / "cuisines" / "labels.json"
KEYWORD_LIMIT = 10
KEY_INGREDIENT_LIMIT = 3
LEGACY_KEYWORD_LIMIT = 5


@dataclass(frozen=True)
class KeywordProposal:
    """The tags selected for one recipe, split out for dry-run review."""

    courses: tuple[str, ...]
    cuisines: tuple[str, ...]
    key_ingredients: tuple[str, ...]
    primary_methods: tuple[str, ...]
    legacy_keywords: tuple[str, ...]
    keywords: tuple[str, ...]


def cuisine_display_names() -> dict[str, str]:
    """Map stored cuisine IDs to their approved display labels."""
    labels = json.loads(_CUISINE_LABELS.read_text())
    return {fold(label).replace(" ", "-"): label for label in labels}


def _ordered_unique(values: list[str], *, limit: int | None = None) -> tuple[str, ...]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        name = " ".join(value.split()).lower()
        folded = fold(name)
        if not folded or folded in seen:
            continue
        seen.add(folded)
        unique.append(name)
        if limit is not None and len(unique) == limit:
            break
    return tuple(unique)


def propose_keywords(
    recipe: Recipe,
    legacy_keywords: list[str],
    cuisine_labels: dict[str, str] | None = None,
) -> KeywordProposal:
    """Build the deterministic ten-keyword discovery list for ``recipe``.

    Structured facts lead the list because they are controlled vocabulary. Flat tags
    from the first extraction then preserve useful descriptors such as occasion,
    season, heat, and dietary properties until the ten-keyword limit is reached.
    """
    labels = cuisine_labels or cuisine_display_names()
    courses = _ordered_unique(
        sorted(
            (
                fact.facet_value.name
                for fact in recipe.facets
                if fact.facet_value.kind is RecipeFacetKind.COURSE
            ),
            key=fold,
        )
    )
    cuisine_names: list[str] = []
    for cuisine in recipe.cuisines:
        try:
            cuisine_names.append(labels[cuisine.cuisine_id])
        except KeyError as exc:
            raise ValueError(
                f"recipe {recipe.id} has unknown cuisine ID {cuisine.cuisine_id!r}"
            ) from exc
    cuisines = _ordered_unique(sorted(cuisine_names, key=fold))
    key_ingredients = _ordered_unique(
        [
            line.canonical_ingredient.name
            for line in recipe.ingredients
            if line.is_key and line.canonical_ingredient is not None
        ],
        limit=KEY_INGREDIENT_LIMIT,
    )
    primary_methods = _ordered_unique(
        sorted(
            (
                fact.facet_value.name
                for fact in recipe.facets
                if fact.facet_value.kind is RecipeFacetKind.METHOD and fact.is_primary
            ),
            key=fold,
        )
    )
    legacy = _ordered_unique(sorted(legacy_keywords, key=fold), limit=LEGACY_KEYWORD_LIMIT)
    keywords = _ordered_unique(
        [*courses, *cuisines, *key_ingredients, *primary_methods, *legacy],
        limit=KEYWORD_LIMIT,
    )
    return KeywordProposal(
        courses=courses,
        cuisines=cuisines,
        key_ingredients=key_ingredients,
        primary_methods=primary_methods,
        legacy_keywords=legacy,
        keywords=keywords,
    )
