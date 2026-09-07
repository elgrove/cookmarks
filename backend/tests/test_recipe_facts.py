import json
from collections import defaultdict
from pathlib import Path

import pytest

from app.models import Recipe, RecipeFacet, RecipeFacetKind, RecipeIngredient
from app.models.recipe_fact import RecipeFacetValue
from app.services.recipe_enrichment.schema import _CUISINE_ALIASES
from app.services.recipe_facts import (
    accepted_cuisine_ids,
    create_ingredient,
    upsert_facet_vocabulary,
    validate_recipe_facets,
)


def test_canonical_names_share_one_folded_namespace(session) -> None:
    create_ingredient(session, "Olive Oil")
    with pytest.raises(ValueError, match="already exists"):
        create_ingredient(session, "olive oil")


def test_line_positions_allow_duplicate_verbatim_text(session) -> None:
    recipe = Recipe(
        book_id=session.query(Recipe).first().book_id, order=99, name="Duplicate", instructions=[]
    )
    recipe.ingredients = [
        RecipeIngredient(position=0, text="salt"),
        RecipeIngredient(position=1, text="salt"),
    ]
    session.add(recipe)
    session.commit()
    assert [line.text for line in recipe.ingredients] == ["salt", "salt"]


def test_recipe_facet_primary_rules(session) -> None:
    upsert_facet_vocabulary(session)
    session.flush()
    method = session.query(RecipeFacetValue).filter_by(kind=RecipeFacetKind.METHOD).first()
    course = session.query(RecipeFacetValue).filter_by(kind=RecipeFacetKind.COURSE).first()
    recipe = session.query(Recipe).first()
    assert method is not None and course is not None
    with pytest.raises(ValueError, match="only a method"):
        validate_recipe_facets(
            [
                RecipeFacet(
                    recipe_id=recipe.id,
                    facet_value_id=course.id,
                    facet_value=course,
                    is_primary=True,
                )
            ]
        )
    validate_recipe_facets(
        [
            RecipeFacet(
                recipe_id=recipe.id, facet_value_id=method.id, facet_value=method, is_primary=True
            )
        ]
    )


def test_accepted_cuisines_include_british_and_australian() -> None:
    accepted = accepted_cuisine_ids()
    assert "british" in accepted
    assert "australian" in accepted
    assert "english" in accepted
    assert "scottish" in accepted
    assert "welsh" in accepted
    assert "irish" in accepted


def test_cuisine_aliases_all_resolve_to_accepted_cuisines() -> None:
    accepted = accepted_cuisine_ids()
    invalid = {k: v for k, v in _CUISINE_ALIASES.items() if v not in accepted}
    assert not invalid, f"Invalid alias targets: {invalid}"
    assert _CUISINE_ALIASES["britain"] == "british"
    assert _CUISINE_ALIASES["argentina"] == "argentine"
    assert _CUISINE_ALIASES["nepal"] == "nepali"
    assert _CUISINE_ALIASES["bangladesh"] == "bengali"
    assert _CUISINE_ALIASES["saudi arabia"] == "arabian-peninsula"


def test_cuisine_edges_reference_valid_labels_without_cycles() -> None:
    data_dir = Path(__file__).parent.parent / "app" / "data" / "cuisines"
    labels = set(json.loads((data_dir / "labels.json").read_text()))
    edges = json.loads((data_dir / "edges.json").read_text())

    missing = [(c, p) for c, p in edges if c not in labels or p not in labels]
    assert not missing, f"Edges referencing missing labels: {missing}"

    graph: dict[str, list[str]] = defaultdict(list)
    for child, parent in edges:
        graph[child].append(parent)

    visited: set[str] = set()
    rec_stack: set[str] = set()

    def has_cycle(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if has_cycle(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.remove(node)
        return False

    for node in list(graph):
        if node not in visited:
            assert not has_cycle(node), f"Cycle detected in cuisine hierarchy at {node}"

