import uuid

from pydantic import BaseModel, Field


class GameRecipeIds(BaseModel):
    """A batch of recipe ids, order preserved — the eligibility request (candidate
    cards from any deck source) and its response (the still-playable subset)."""

    recipe_ids: list[uuid.UUID] = Field(max_length=500)


class DismissState(BaseModel):
    """Whether the recipe is dismissed for the caller, after a dismissal write."""

    dismissed: bool


class GameDeckCard(BaseModel):
    """One play-all deck card: the id the eligibility check and the detail fetch
    need, plus the name shown while the detail loads. Nothing else — the game
    never renders keywords, book titles or facets (MY-212)."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str


class GameDeckPage(BaseModel):
    """A page of the play-all deck, in the seeded-shuffle order shared with the
    search endpoint's `all=true` mode. No total and no facets: the game pages
    until an empty batch, so counting the library would be pure overhead."""

    items: list[GameDeckCard]
