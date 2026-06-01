import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.covers import has_cover
from app.db import SessionDep
from app.models.recipe import Recipe
from app.schemas.recipe import RecipeDetail, RecipeNeighbour

router = APIRouter(tags=["recipes"])

# Navigation orderings the page can be reached through. Only "book" is wired today;
# "search" / "list" arrive with those pages, so unknown contexts resolve to book.
SUPPORTED_CONTEXTS = {"book"}


def _book_neighbours(
    session: Session, recipe: Recipe
) -> tuple[RecipeNeighbour | None, RecipeNeighbour | None]:
    """The previous/next recipe in the owning book's stored order (Recipe.order)."""
    prev = session.execute(
        select(Recipe.id, Recipe.name)
        .where(Recipe.book_id == recipe.book_id, Recipe.order < recipe.order)
        .order_by(Recipe.order.desc())
        .limit(1)
    ).first()
    nxt = session.execute(
        select(Recipe.id, Recipe.name)
        .where(Recipe.book_id == recipe.book_id, Recipe.order > recipe.order)
        .order_by(Recipe.order.asc())
        .limit(1)
    ).first()
    return (
        RecipeNeighbour(id=prev.id, name=prev.name) if prev else None,
        RecipeNeighbour(id=nxt.id, name=nxt.name) if nxt else None,
    )


@router.get("/recipes/{recipe_id}", response_model=RecipeDetail)
def get_recipe(recipe_id: uuid.UUID, session: SessionDep, context: str = "book") -> RecipeDetail:
    recipe = session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.keywords), joinedload(Recipe.book))
    )
    if recipe is None:
        raise HTTPException(status_code=404, detail="recipe not found")
    book = recipe.book
    resolved_context = context if context in SUPPORTED_CONTEXTS else "book"
    previous, next_ = _book_neighbours(session, recipe)
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
        context=resolved_context,
        previous=previous,
        next=next_,
    )
