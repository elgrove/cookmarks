import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import SessionDep
from app.models.book import Book
from app.models.recipe import Recipe
from app.models.recipe_list import RecipeList, RecipeListItem
from app.schemas.recipe import RecipeSummary
from app.schemas.recipe_list import (
    FavouriteState,
    ListCreate,
    ListDetail,
    ListMembership,
    ListRecipeRef,
    ListRename,
    ListSummary,
)

router = APIRouter(tags=["lists"])

# Lists order with the default Favourites pinned first, then alphabetically.
_LIST_ORDER = (RecipeList.is_default.desc(), func.lower(RecipeList.name))


def get_or_create_favourites(session: Session) -> RecipeList:
    """The single default Favourites list, created on first use. Mirrors v1's
    `RecipeList.get_favourites`; called from the list reads so the default always
    appears even on a fresh database."""
    favourites = session.scalar(select(RecipeList).where(RecipeList.is_default.is_(True)))
    if favourites is None:
        favourites = RecipeList(name="Favourites", is_default=True)
        session.add(favourites)
        session.commit()
        session.refresh(favourites)
    return favourites


def favourite_list_id(session: Session) -> uuid.UUID | None:
    """The default list's id without creating it — a pure read for the star state."""
    return session.scalar(select(RecipeList.id).where(RecipeList.is_default.is_(True)))


def _recipe_summaries(session: Session, list_id: uuid.UUID) -> list[RecipeSummary]:
    rows = session.execute(
        select(Recipe, Book)
        .join(RecipeListItem, RecipeListItem.recipe_id == Recipe.id)
        .join(Book, Recipe.book_id == Book.id)
        .where(RecipeListItem.recipe_list_id == list_id)
        .order_by(RecipeListItem.position, RecipeListItem.created_at.desc())
        .options(selectinload(Recipe.keywords))
    ).all()
    return [
        RecipeSummary(
            id=recipe.id,
            name=recipe.name,
            book_id=book.id,
            book_title=book.title,
            book_author=book.author,
            keywords=sorted(k.name for k in recipe.keywords),
        )
        for recipe, book in rows
    ]


@router.get("/lists", response_model=list[ListSummary])
def list_lists(session: SessionDep) -> list[ListSummary]:
    get_or_create_favourites(session)
    counts = (
        select(RecipeListItem.recipe_list_id, func.count().label("n"))
        .group_by(RecipeListItem.recipe_list_id)
        .subquery()
    )
    rows = session.execute(
        select(RecipeList, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.recipe_list_id == RecipeList.id)
        .order_by(*_LIST_ORDER)
    ).all()
    return [
        ListSummary(id=lst.id, name=lst.name, is_default=lst.is_default, recipe_count=count)
        for lst, count in rows
    ]


@router.post("/lists", response_model=ListSummary, status_code=status.HTTP_201_CREATED)
def create_list(body: ListCreate, session: SessionDep) -> ListSummary:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="list name is required")
    lst = RecipeList(name=name, is_default=False)
    session.add(lst)
    session.commit()
    session.refresh(lst)
    return ListSummary(id=lst.id, name=lst.name, is_default=lst.is_default, recipe_count=0)


@router.get("/lists/{list_id}", response_model=ListDetail)
def get_list(list_id: uuid.UUID, session: SessionDep) -> ListDetail:
    lst = session.get(RecipeList, list_id)
    if lst is None:
        raise HTTPException(status_code=404, detail="list not found")
    recipes = _recipe_summaries(session, list_id)
    return ListDetail(
        id=lst.id,
        name=lst.name,
        is_default=lst.is_default,
        recipe_count=len(recipes),
        recipes=recipes,
    )


@router.patch("/lists/{list_id}", response_model=ListSummary)
def rename_list(list_id: uuid.UUID, body: ListRename, session: SessionDep) -> ListSummary:
    lst = session.get(RecipeList, list_id)
    if lst is None:
        raise HTTPException(status_code=404, detail="list not found")
    if lst.is_default:
        raise HTTPException(status_code=409, detail="the Favourites list cannot be renamed")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="list name is required")
    lst.name = name
    session.commit()
    count = session.scalar(
        select(func.count()).where(RecipeListItem.recipe_list_id == list_id)
    )
    return ListSummary(id=lst.id, name=lst.name, is_default=lst.is_default, recipe_count=count or 0)


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(list_id: uuid.UUID, session: SessionDep) -> Response:
    lst = session.get(RecipeList, list_id)
    if lst is None:
        raise HTTPException(status_code=404, detail="list not found")
    if lst.is_default:
        raise HTTPException(status_code=409, detail="the Favourites list cannot be deleted")
    session.delete(lst)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/lists/{list_id}/recipes", status_code=status.HTTP_204_NO_CONTENT)
def add_to_list(list_id: uuid.UUID, body: ListRecipeRef, session: SessionDep) -> Response:
    lst = session.get(RecipeList, list_id)
    if lst is None:
        raise HTTPException(status_code=404, detail="list not found")
    if session.get(Recipe, body.recipe_id) is None:
        raise HTTPException(status_code=404, detail="recipe not found")
    # Idempotent: adding a recipe already in the list is a no-op (the unique
    # constraint on (list, recipe) would otherwise raise).
    exists = session.scalar(
        select(RecipeListItem.id).where(
            RecipeListItem.recipe_list_id == list_id,
            RecipeListItem.recipe_id == body.recipe_id,
        )
    )
    if exists is None:
        session.add(RecipeListItem(recipe_list_id=list_id, recipe_id=body.recipe_id))
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/lists/{list_id}/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_from_list(
    list_id: uuid.UUID, recipe_id: uuid.UUID, session: SessionDep
) -> Response:
    item = session.scalar(
        select(RecipeListItem).where(
            RecipeListItem.recipe_list_id == list_id,
            RecipeListItem.recipe_id == recipe_id,
        )
    )
    if item is not None:
        session.delete(item)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/recipes/{recipe_id}/lists", response_model=list[ListMembership])
def recipe_lists(recipe_id: uuid.UUID, session: SessionDep) -> list[ListMembership]:
    if session.get(Recipe, recipe_id) is None:
        raise HTTPException(status_code=404, detail="recipe not found")
    get_or_create_favourites(session)
    member_ids = set(
        session.scalars(
            select(RecipeListItem.recipe_list_id).where(RecipeListItem.recipe_id == recipe_id)
        ).all()
    )
    lists = session.scalars(select(RecipeList).order_by(*_LIST_ORDER)).all()
    return [
        ListMembership(
            id=lst.id, name=lst.name, is_default=lst.is_default, contains=lst.id in member_ids
        )
        for lst in lists
    ]


@router.post("/recipes/{recipe_id}/favourite", response_model=FavouriteState)
def toggle_favourite(recipe_id: uuid.UUID, session: SessionDep) -> FavouriteState:
    if session.get(Recipe, recipe_id) is None:
        raise HTTPException(status_code=404, detail="recipe not found")
    favourites = get_or_create_favourites(session)
    item = session.scalar(
        select(RecipeListItem).where(
            RecipeListItem.recipe_list_id == favourites.id,
            RecipeListItem.recipe_id == recipe_id,
        )
    )
    if item is None:
        session.add(RecipeListItem(recipe_list_id=favourites.id, recipe_id=recipe_id))
        session.commit()
        return FavouriteState(is_favourite=True)
    session.delete(item)
    session.commit()
    return FavouriteState(is_favourite=False)
