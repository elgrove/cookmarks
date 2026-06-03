import uuid

from pydantic import BaseModel, ConfigDict

from app.schemas.recipe import RecipeSummary


class ListSummary(BaseModel):
    """One list as it appears in the Lists index: name, default flag, size."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_default: bool
    recipe_count: int


class ListDetail(BaseModel):
    """A single list opened: its meta plus its recipes as a text-first index."""

    id: uuid.UUID
    name: str
    is_default: bool
    recipe_count: int
    recipes: list[RecipeSummary]


class ListMembership(BaseModel):
    """A list paired with whether a given recipe is in it — drives the
    add-to-list control's per-list toggle."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_default: bool
    contains: bool


class ListCreate(BaseModel):
    """Request body to create a list."""

    name: str


class ListRename(BaseModel):
    """Request body to rename a list."""

    name: str


class ListRecipeRef(BaseModel):
    """Request body to add a recipe to a list."""

    recipe_id: uuid.UUID


class FavouriteState(BaseModel):
    """The result of toggling a recipe's favourite star."""

    is_favourite: bool
