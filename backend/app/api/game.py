import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser
from app.api.lists import favourite_list_id
from app.db import SessionDep
from app.models.game import GameDismissal
from app.models.recipe import Recipe
from app.models.recipe_list import RecipeListItem
from app.schemas.game import DismissState, GameRecipeIds

router = APIRouter(tags=["game"])


@router.post("/game/eligible", response_model=GameRecipeIds)
def eligible_recipes(body: GameRecipeIds, session: SessionDep, user: CurrentUser) -> GameRecipeIds:
    """Filter a candidate batch down to the caller's still-playable subset — not
    favourited, not dismissed — preserving input order. The deck sources are the
    existing recipe endpoints; this is the only game-specific read."""
    ids = body.recipe_ids
    dismissed = set(
        session.scalars(
            select(GameDismissal.recipe_id).where(
                GameDismissal.user_id == user.id, GameDismissal.recipe_id.in_(ids)
            )
        )
    )
    fav_id = favourite_list_id(session, user.id)
    favourited: set[uuid.UUID] = set()
    if fav_id is not None:
        favourited = set(
            session.scalars(
                select(RecipeListItem.recipe_id).where(
                    RecipeListItem.recipe_list_id == fav_id, RecipeListItem.recipe_id.in_(ids)
                )
            )
        )
    return GameRecipeIds(recipe_ids=[i for i in ids if i not in dismissed and i not in favourited])


@router.put("/game/dismissals/{recipe_id}", response_model=DismissState)
def dismiss_recipe(recipe_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> DismissState:
    if session.get(Recipe, recipe_id) is None:
        raise HTTPException(status_code=404, detail="recipe not found")
    already = session.scalar(
        select(GameDismissal.id).where(
            GameDismissal.user_id == user.id, GameDismissal.recipe_id == recipe_id
        )
    )
    if already is None:
        session.add(GameDismissal(user_id=user.id, recipe_id=recipe_id))
        try:
            session.commit()
        except IntegrityError:
            # A concurrent PUT won the unique constraint; the desired state holds.
            session.rollback()
    return DismissState(dismissed=True)
