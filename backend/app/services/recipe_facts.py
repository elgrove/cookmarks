"""Repository-backed validation and writes for controlled recipe facts."""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import RecipeFacetKind
from app.models.ingredient import Ingredient, IngredientAlias
from app.models.recipe_fact import RecipeFacet, RecipeFacetValue
from app.text import fold

_ASSET = Path(__file__).parent.parent / "data" / "recipe_facets" / "v1.json"
_CUISINES = Path(__file__).parent.parent / "data" / "cuisines" / "labels.json"


def facet_vocabulary() -> tuple[str, list[dict[str, str]]]:
    data = json.loads(_ASSET.read_text())
    entries = data["facets"]
    ids = {(entry["kind"], entry["id"]) for entry in entries}
    names = [fold(entry["name"]) for entry in entries]
    if len(ids) != len(entries) or len(set(names)) != len(names):
        raise ValueError("recipe facet vocabulary contains duplicate IDs or names")
    return data["version"], entries


def upsert_facet_vocabulary(session: Session) -> None:
    version, entries = facet_vocabulary()
    existing = {
        (value.kind.value, value.value_id): value
        for value in session.scalars(select(RecipeFacetValue))
    }
    for entry in entries:
        key = (entry["kind"], entry["id"])
        prior = existing.get(key)
        if prior is not None:
            if prior.name != entry["name"] or prior.kind.value != entry["kind"]:
                raise ValueError(f"recipe facet {entry['id']} changed incompatibly")
            continue
        session.add(
            RecipeFacetValue(
                kind=RecipeFacetKind(entry["kind"]),
                value_id=entry["id"],
                name=entry["name"],
                vocabulary_version=version,
            )
        )


def validate_recipe_facets(facts: list[RecipeFacet]) -> None:
    primary = [fact for fact in facts if fact.is_primary]
    if len(primary) > 1:
        raise ValueError("a recipe may have at most one primary method")
    if any(
        fact.is_primary and fact.facet_value.kind is not RecipeFacetKind.METHOD for fact in facts
    ):
        raise ValueError("only a method may be primary")


def accepted_cuisine_ids() -> set[str]:
    return {fold(name).replace(" ", "-") for name in json.loads(_CUISINES.read_text())}


def validate_cuisine_id(cuisine_id: str) -> None:
    if cuisine_id not in accepted_cuisine_ids():
        raise ValueError(f"unknown accepted cuisine: {cuisine_id}")


def create_ingredient(session: Session, name: str) -> Ingredient:
    """Create a canonical ingredient only when no alias already owns its folded name."""
    folded = fold(name)
    if session.scalar(select(IngredientAlias).where(IngredientAlias.name_folded == folded)):
        raise ValueError("canonical ingredient collides with an existing alias")
    if session.scalar(select(Ingredient).where(Ingredient.name_folded == folded)):
        raise ValueError("canonical ingredient already exists")
    ingredient = Ingredient(name=name)
    session.add(ingredient)
    session.flush()
    return ingredient


def add_ingredient_alias(session: Session, ingredient: Ingredient, name: str) -> IngredientAlias:
    """Add an accepted synonym, rejecting canonical/alias namespace collisions."""
    folded = fold(name)
    if session.scalar(select(Ingredient).where(Ingredient.name_folded == folded)):
        raise ValueError("ingredient alias collides with a canonical ingredient")
    if session.scalar(select(IngredientAlias).where(IngredientAlias.name_folded == folded)):
        raise ValueError("ingredient alias already exists")
    alias = IngredientAlias(ingredient_id=ingredient.id, name=name)
    session.add(alias)
    session.flush()
    return alias
