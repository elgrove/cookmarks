import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.covers import has_cover
from app.db import SessionDep
from app.models.recipe import Recipe
from app.schemas.recipe import RecipeDetail

router = APIRouter(tags=["recipes"])


@router.get("/recipes/{recipe_id}", response_model=RecipeDetail)
def get_recipe(recipe_id: uuid.UUID, session: SessionDep) -> RecipeDetail:
    recipe = session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.keywords), joinedload(Recipe.book))
    )
    if recipe is None:
        raise HTTPException(status_code=404, detail="recipe not found")
    book = recipe.book
    return RecipeDetail(
        id=recipe.id,
        book_id=book.id,
        book_title=book.title,
        book_author=book.author,
        book_has_cover=has_cover(book),
        name=recipe.name,
        description=recipe.description,
        ingredients=recipe.ingredients,
        instructions=recipe.instructions,
        yields=recipe.yields,
        keywords=sorted(k.name for k in recipe.keywords),
        has_image=recipe.image is not None,
    )
