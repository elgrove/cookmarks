import pytest

from app.models import Recipe, RecipeFacet, RecipeFacetKind, RecipeIngredient
from app.models.recipe_fact import RecipeFacetValue
from app.services.recipe_facts import (
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
