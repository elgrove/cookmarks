import uuid

from pydantic import BaseModel, Field


class GameRecipeIds(BaseModel):
    """A batch of recipe ids, order preserved — the eligibility request (candidate
    cards from any deck source) and its response (the still-playable subset)."""

    recipe_ids: list[uuid.UUID] = Field(max_length=500)


class DismissState(BaseModel):
    """Whether the recipe is dismissed for the caller, after a dismissal write."""

    dismissed: bool
