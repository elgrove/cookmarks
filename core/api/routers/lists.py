from uuid import UUID

from django.db.models import Count
from django.shortcuts import get_object_or_404
from ninja import Router

from core.api.schemas import MessageOut, RecipeListIn, RecipeListSummary
from core.models import Recipe, RecipeList, RecipeListItem

router = Router()


def _list_to_out(rl: RecipeList, recipe_count: int | None = None) -> dict:
    return {
        "id": rl.id,
        "name": rl.name,
        "is_default": rl.is_default,
        "recipe_count": (
            recipe_count if recipe_count is not None else getattr(rl, "recipe_count", 0)
        ),
    }


@router.get("", response=list[RecipeListSummary])
def list_lists(request, search: str = ""):
    qs = RecipeList.objects.annotate(recipe_count=Count("recipes")).all()
    if search:
        qs = qs.filter(name__icontains=search)
    return [_list_to_out(rl) for rl in qs]


@router.get("/favourites", response=RecipeListSummary)
def get_favourites(request):
    rl = RecipeList.get_favourites()
    return _list_to_out(rl, rl.recipes.count())


@router.post("", response={201: RecipeListSummary, 400: MessageOut})
def create_list(request, data: RecipeListIn):
    name = data.name.strip()
    if not name:
        return 400, {"detail": "List name is required"}
    rl = RecipeList.objects.create(name=name)
    return 201, _list_to_out(rl, 0)


@router.get("/{list_id}", response=RecipeListSummary)
def get_list(request, list_id: UUID):
    rl = get_object_or_404(RecipeList.objects.annotate(recipe_count=Count("recipes")), id=list_id)
    return _list_to_out(rl)


@router.delete("/{list_id}", response=MessageOut)
def delete_list(request, list_id: UUID):
    rl = get_object_or_404(RecipeList, id=list_id)
    name = rl.name
    rl.delete()
    return {"detail": f'Deleted list "{name}"'}


@router.post("/{list_id}/recipes/{recipe_id}", response={200: MessageOut, 409: MessageOut})
def add_recipe(request, list_id: UUID, recipe_id: UUID):
    rl = get_object_or_404(RecipeList, id=list_id)
    recipe = get_object_or_404(Recipe, id=recipe_id)
    _, created = RecipeListItem.objects.get_or_create(recipe=recipe, recipe_list=rl)
    if not created:
        return 409, {"detail": f'"{recipe.name}" is already in "{rl.name}"'}
    return 200, {"detail": f'Added "{recipe.name}" to "{rl.name}"'}


@router.delete("/{list_id}/recipes/{recipe_id}", response={200: MessageOut, 404: MessageOut})
def remove_recipe(request, list_id: UUID, recipe_id: UUID):
    rl = get_object_or_404(RecipeList, id=list_id)
    recipe = get_object_or_404(Recipe, id=recipe_id)
    deleted, _ = RecipeListItem.objects.filter(recipe=recipe, recipe_list=rl).delete()
    if not deleted:
        return 404, {"detail": f'"{recipe.name}" was not in "{rl.name}"'}
    return 200, {"detail": f'Removed "{recipe.name}" from "{rl.name}"'}
