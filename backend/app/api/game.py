import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser
from app.api.lists import favourite_list_id
from app.api.recipes import _shuffle_order
from app.db import SessionDep
from app.models.game import GameDismissal
from app.models.recipe import Recipe
from app.models.recipe_list import RecipeListItem
from app.schemas.game import DismissState, GameDeckCard, GameDeckPage, GameRecipeIds

router = APIRouter(tags=["game"])


@router.get("/game/deck", response_model=GameDeckPage)
def play_all_deck(
    session: SessionDep,
    user: CurrentUser,
    seed: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GameDeckPage:
    """The play-all deck: recipe ids + names in the seeded-shuffle order the
    search endpoint uses for `all=true`, without its cost. No book join, no
    keyword eager-load, no windowed total, no facets — the game reads ids only
    and filters them through the eligibility endpoint (MY-212)."""
    rows = session.execute(
        select(Recipe.id, Recipe.name)
        .order_by(*_shuffle_order(seed), Recipe.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return GameDeckPage(items=[GameDeckCard(id=rid, name=name) for rid, name in rows])


@router.post("/game/eligible", response_model=GameRecipeIds)
def eligible_recipes(body: GameRecipeIds, session: SessionDep, user: CurrentUser) -> GameRecipeIds:
    """Filter a candidate batch down to the caller's still-playable subset — not
    favourited, not dismissed — preserving input order. The play-all deck comes
    from GET /game/deck; the other deck sources are the existing recipe
    endpoints."""
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
