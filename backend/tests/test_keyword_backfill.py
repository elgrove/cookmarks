from sqlalchemy import select

from app.models import RecipeFacet, RecipeFacetKind, RecipeIngredient, RecipeList, RecipeListItem
from app.models.recipe_fact import RecipeCuisine, RecipeFacetValue
from app.services.keyword_backfill import KEYWORD_LIMIT, cuisine_display_names, propose_keywords
from app.services.recipe_facts import create_canonical_ingredient, upsert_facet_vocabulary
from app.services.vector_store import EMBEDDING_DIMENSIONS, VectorStore
from scripts.backfill_recipe_keywords import _reset_recipes


def test_propose_keywords_combines_facts_and_preserves_original_keywords(session) -> None:
    recipe = session.query(RecipeIngredient).first().recipe
    assert recipe is not None
    upsert_facet_vocabulary(session)
    session.flush()
    course = (
        session.query(RecipeFacetValue)
        .filter_by(kind=RecipeFacetKind.COURSE, value_id="main")
        .one()
    )
    method = (
        session.query(RecipeFacetValue)
        .filter_by(kind=RecipeFacetKind.METHOD, value_id="bake")
        .one()
    )
    ingredient = create_canonical_ingredient(session, "Aubergine")
    recipe.ingredients[0].canonical_ingredient = ingredient
    recipe.ingredients[0].is_key = True
    recipe.facets = [
        RecipeFacet(facet_value=course),
        RecipeFacet(facet_value=method, is_primary=True),
    ]
    recipe.cuisines = [RecipeCuisine(cuisine_id="italian")]
    session.flush()

    proposal = propose_keywords(recipe, ["Quick", "Vegetarian", "Italian"], cuisine_display_names())

    assert proposal.courses == ("main",)
    assert proposal.cuisines == ("italian",)
    assert proposal.key_ingredients == ("aubergine",)
    assert proposal.primary_methods == ("bake",)
    assert proposal.keywords == ("main", "italian", "aubergine", "bake", "quick", "vegetarian")


def test_propose_keywords_limits_key_ingredients_and_total_keywords(session) -> None:
    recipe = session.query(RecipeIngredient).first().recipe
    assert recipe is not None
    for index, line in enumerate(recipe.ingredients):
        ingredient = create_canonical_ingredient(session, f"Ingredient {index}")
        line.canonical_ingredient = ingredient
        line.is_key = True
    session.flush()

    proposal = propose_keywords(
        recipe, [f"Keyword {index}" for index in range(12)], cuisine_display_names()
    )

    assert len(proposal.key_ingredients) <= 3
    assert len(proposal.legacy_keywords) == 5
    assert len(proposal.keywords) <= KEYWORD_LIMIT


def test_reset_recipes_removes_links_and_vectors_but_keeps_the_book(session) -> None:
    recipe = session.query(RecipeIngredient).first().recipe
    assert recipe is not None
    book_id = recipe.book_id
    favourites = RecipeList(name="Favourites", is_default=True)
    session.add_all([favourites, RecipeListItem(recipe=recipe, recipe_list=favourites)])
    session.flush()
    VectorStore(session).upsert(recipe.id, [0.0] * EMBEDDING_DIMENSIONS)
    session.commit()

    summary = _reset_recipes(session, [recipe.id])
    session.commit()

    assert [(item.title, item.recipes, item.list_items, item.favourites) for item in summary] == [
        ("With Recipes", 1, 1, 1)
    ]
    assert session.get(type(recipe), recipe.id) is None
    assert session.scalar(select(RecipeListItem).where(RecipeListItem.recipe_id == recipe.id)) is None
    assert VectorStore(session).get_embedding(recipe.id) is None
    assert session.get(type(recipe.book), book_id) is not None
