import pytest

from app.models import IngredientLine, Recipe, RecipeFacet, RecipeFacetKind
from app.models.recipe_fact import RecipeFacetValue
from app.services.recipe_facts import (
    add_ingredient_alias,
    create_ingredient,
    upsert_facet_vocabulary,
    validate_recipe_facets,
)


def test_canonical_and_alias_names_share_one_folded_namespace(session) -> None:
    olive_oil = create_ingredient(session, "Olive Oil")
    add_ingredient_alias(session, olive_oil, "huile d'olive")
    with pytest.raises(ValueError, match="alias"):
        create_ingredient(session, "Huile d'olive")
    with pytest.raises(ValueError, match="canonical"):
        add_ingredient_alias(session, olive_oil, "OLIVE OIL")


def test_line_positions_allow_duplicate_verbatim_text(session) -> None:
    recipe = Recipe(
        book_id=session.query(Recipe).first().book_id, order=99, name="Duplicate", instructions=[]
    )
    recipe.ingredients_verbatim = [
        IngredientLine(position=0, text="salt"),
        IngredientLine(position=1, text="salt"),
    ]
    session.add(recipe)
    session.commit()
    assert [line.text for line in recipe.ingredients_verbatim] == ["salt", "salt"]


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
