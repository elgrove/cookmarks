import logging
import uuid
import zipfile
from typing import Literal
from uuid import UUID

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from ninja import Query, Router

from core.api.recipe_queries import build_recipe_queryset
from core.api.schemas import (
    AISearchIn,
    AISearchOut,
    KeywordsIn,
    MessageOut,
    PaginatedRecipes,
    RecipeDetail,
    RecipeSummary,
)
from core.models import (
    Book,
    Keyword,
    Recipe,
    RecipeList,
    RecipeListItem,
)
from core.services.embeddings import find_similar_recipes
from core.services.embeddings import search_recipes as vector_search_recipes

logger = logging.getLogger(__name__)

router = Router()


def _recipe_to_summary(recipe: Recipe) -> dict:
    return {
        "id": recipe.id,
        "book_id": recipe.book_id,
        "book_title": recipe.book.title,
        "book_clean_title": recipe.book.clean_title,
        "book_author": recipe.book.author,
        "order": recipe.order,
        "name": recipe.name,
        "clean_name": recipe.clean_name,
        "description": recipe.description,
        "yields": recipe.yields,
        "has_image": bool(recipe.image),
        "image": recipe.image or None,
        "keywords": [k.name for k in recipe.keywords.all()],
    }


def _neighbour(recipe: Recipe | None) -> dict | None:
    if not recipe:
        return None
    return {"id": recipe.id, "name": recipe.name, "clean_name": recipe.clean_name}


@router.get("", response=PaginatedRecipes)
def list_recipes(
    request,
    q: str = "",
    book: UUID | None = None,
    list: UUID | None = None,
    selected_lists: list[UUID] = Query(default_factory=list),
    selected_keywords: list[str] = Query(default_factory=list),
    vector_search: str = "",
    group_logic: Literal["and", "or"] = "or",
    sort: str = "",
    page: int = 1,
    page_size: int = 30,
    filter_field: list[str] = Query(default_factory=list),
    filter_op: list[str] = Query(default_factory=list),
    filter_value: list[str] = Query(default_factory=list),
    filter_group: list[str] = Query(default_factory=list),
    filter_logic: list[str] = Query(default_factory=list),
):
    # Compose filters from parallel arrays (matches frontend URL shape)
    filters = []
    for i, field in enumerate(filter_field):
        if i >= len(filter_value):
            break
        filters.append(
            {
                "field": field,
                "op": filter_op[i] if i < len(filter_op) else "contains",
                "value": filter_value[i],
                "group": (
                    int(filter_group[i])
                    if i < len(filter_group) and filter_group[i].isdigit()
                    else 0
                ),
                "logic": filter_logic[i] if i < len(filter_logic) else "or",
            }
        )

    selected_list_ids = [str(lid) for lid in selected_lists]
    if list and str(list) not in selected_list_ids:
        selected_list_ids.append(str(list))

    vector_search_ids: list[str] | None = None
    if vector_search:
        session_key = f"vector_search_{vector_search}"
        vector_data = request.session.get(session_key)
        if vector_data:
            vector_search_ids = vector_data.get("recipe_ids", [])

    results, has_searched = build_recipe_queryset(
        q=q,
        book_id=book,
        selected_lists=selected_list_ids,
        selected_keywords=selected_keywords,
        filters=filters,
        group_logic=group_logic,
        vector_search_ids=vector_search_ids,
        sort=sort,
    )

    if not has_searched:
        return {
            "items": [],
            "page": 1,
            "pages": 1,
            "total": 0,
            "page_size": page_size,
            "has_next": False,
            "has_previous": False,
        }

    paginator = Paginator(results, page_size)
    page_obj = paginator.get_page(page)

    return {
        "items": [_recipe_to_summary(r) for r in page_obj.object_list],
        "page": page_obj.number,
        "pages": paginator.num_pages,
        "total": paginator.count,
        "page_size": page_size,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }


@router.post("/ai-search", response={200: AISearchOut, 400: MessageOut, 500: MessageOut})
def ai_search(request, data: AISearchIn):
    prompt = data.prompt.strip()
    if not prompt:
        return 400, {"detail": "Prompt is required"}

    try:
        recipes = vector_search_recipes(prompt, limit=data.limit)
    except Exception as e:
        logger.exception("Vector search failed")
        return 500, {"detail": f"AI search failed: {e!s}"}

    recipe_ids = [str(r.id) for r in recipes]
    search_key = uuid.uuid4().hex[:12]
    request.session[f"vector_search_{search_key}"] = {
        "query": prompt,
        "recipe_ids": recipe_ids,
        "timestamp": now().isoformat(),
    }
    return 200, {"search_key": search_key, "count": len(recipe_ids)}


def _neighbours_in_book(recipe: Recipe) -> tuple[Recipe | None, Recipe | None]:
    return recipe.get_previous_in_book(), recipe.get_next_in_book()


def _neighbours_in_list(
    recipe: Recipe, recipe_list: RecipeList
) -> tuple[Recipe | None, Recipe | None]:
    items = (
        RecipeListItem.objects.filter(recipe_list=recipe_list)
        .select_related("recipe")
        .order_by("id")
    )
    ids = [it.recipe_id for it in items]
    if recipe.id not in ids:
        return None, None
    idx = ids.index(recipe.id)
    prev_recipe = Recipe.objects.filter(id=ids[idx - 1]).first() if idx > 0 else None
    next_recipe = Recipe.objects.filter(id=ids[idx + 1]).first() if idx < len(ids) - 1 else None
    return prev_recipe, next_recipe


def _neighbours_in_search(
    recipe: Recipe, request, **search_kwargs
) -> tuple[Recipe | None, Recipe | None]:
    results, _ = build_recipe_queryset(**search_kwargs)

    if hasattr(results, "values_list"):
        ids = list(results.values_list("id", flat=True))
    else:
        ids = [r.id for r in results]

    if recipe.id not in ids:
        return None, None
    idx = ids.index(recipe.id)
    prev_recipe = Recipe.objects.filter(id=ids[idx - 1]).first() if idx > 0 else None
    next_recipe = Recipe.objects.filter(id=ids[idx + 1]).first() if idx < len(ids) - 1 else None
    return prev_recipe, next_recipe


@router.get("/{recipe_id}", response=RecipeDetail)
def get_recipe(
    request,
    recipe_id: UUID,
    context: Literal["book", "list", "search"] = "book",
    list_id: UUID | None = None,
    q: str = "",
    vector_search: str = "",
    selected_lists: list[UUID] = Query(default_factory=list),
    sort: str = "",
    group_logic: Literal["and", "or"] = "or",
    filter_field: list[str] = Query(default_factory=list),
    filter_op: list[str] = Query(default_factory=list),
    filter_value: list[str] = Query(default_factory=list),
    filter_group: list[str] = Query(default_factory=list),
    filter_logic: list[str] = Query(default_factory=list),
):
    recipe = get_object_or_404(
        Recipe.objects.select_related("book").prefetch_related("keywords", "recipe_lists"),
        id=recipe_id,
    )

    previous_recipe = next_recipe = None
    breadcrumb: dict | None = None

    if context == "list" and list_id:
        recipe_list = RecipeList.objects.filter(id=list_id).first()
        if recipe_list:
            previous_recipe, next_recipe = _neighbours_in_list(recipe, recipe_list)
            breadcrumb = {
                "type": "list",
                "list_id": recipe_list.id,
                "list_name": recipe_list.name,
            }

    if context == "search":
        filters = []
        for i, field in enumerate(filter_field):
            if i >= len(filter_value):
                break
            filters.append(
                {
                    "field": field,
                    "op": filter_op[i] if i < len(filter_op) else "contains",
                    "value": filter_value[i],
                    "group": (
                        int(filter_group[i])
                        if i < len(filter_group) and filter_group[i].isdigit()
                        else 0
                    ),
                    "logic": filter_logic[i] if i < len(filter_logic) else "or",
                }
            )

        vector_search_ids: list[str] | None = None
        if vector_search:
            data = request.session.get(f"vector_search_{vector_search}")
            if data:
                vector_search_ids = data.get("recipe_ids", [])

        previous_recipe, next_recipe = _neighbours_in_search(
            recipe,
            request,
            q=q,
            selected_lists=[str(lid) for lid in selected_lists],
            filters=filters,
            group_logic=group_logic,
            vector_search_ids=vector_search_ids,
            sort=sort or "name",
        )
        breadcrumb = {"type": "search"}

    # Fall back to book context if nothing else applied
    if previous_recipe is None and next_recipe is None and breadcrumb is None:
        previous_recipe, next_recipe = _neighbours_in_book(recipe)
        breadcrumb = {
            "type": "book",
            "book_id": recipe.book.id,
            "book_title": recipe.book.clean_title,
        }

    favourites = RecipeList.get_favourites()
    is_favourite = RecipeListItem.objects.filter(recipe=recipe, recipe_list=favourites).exists()

    return {
        "id": recipe.id,
        "book_id": recipe.book_id,
        "book_title": recipe.book.title,
        "book_clean_title": recipe.book.clean_title,
        "book_author": recipe.book.author,
        "order": recipe.order,
        "name": recipe.name,
        "clean_name": recipe.clean_name,
        "description": recipe.description,
        "yields": recipe.yields,
        "ingredients": recipe.ingredients or [],
        "instructions": recipe.instructions or [],
        "image": recipe.image or None,
        "keywords": [k.name for k in recipe.keywords.all()],
        "list_ids": [rl.id for rl in recipe.recipe_lists.all()],
        "is_favourite": is_favourite,
        "favourites_list_id": favourites.id,
        "previous_recipe": _neighbour(previous_recipe),
        "next_recipe": _neighbour(next_recipe),
        "breadcrumb": breadcrumb,
    }


@router.delete("/{recipe_id}", response=MessageOut)
def delete_recipe(request, recipe_id: UUID):
    recipe = get_object_or_404(Recipe, id=recipe_id)
    name = recipe.name
    recipe.delete()
    return {"detail": f'Deleted recipe "{name}".'}


@router.post("/{recipe_id}/clear-image", response=MessageOut)
def clear_image(request, recipe_id: UUID):
    recipe = get_object_or_404(Recipe, id=recipe_id)
    recipe.image = ""
    recipe.save(update_fields=["image"])
    return {"detail": "Image removed from recipe."}


@router.put("/{recipe_id}/keywords", response=MessageOut)
def set_keywords(request, recipe_id: UUID, data: KeywordsIn):
    recipe = get_object_or_404(Recipe, id=recipe_id)
    names = [n.strip() for n in data.keywords if n and n.strip()]
    keywords = []
    for name in names:
        keyword, _ = Keyword.objects.get_or_create(name=name)
        keywords.append(keyword)
    recipe.keywords.set(keywords)
    return {"detail": "Keywords updated successfully."}


@router.post("/{recipe_id}/toggle-favourite", response={200: dict})
def toggle_favourite(request, recipe_id: UUID):
    recipe = get_object_or_404(Recipe, id=recipe_id)
    favourites = RecipeList.get_favourites()
    existing = RecipeListItem.objects.filter(recipe=recipe, recipe_list=favourites).first()
    if existing:
        existing.delete()
        return 200, {"is_favourite": False}
    RecipeListItem.objects.create(recipe=recipe, recipe_list=favourites)
    return 200, {"is_favourite": True}


@router.get("/{recipe_id}/similar", response=list[RecipeSummary])
def similar(request, recipe_id: UUID):
    recipe = get_object_or_404(Recipe, id=recipe_id)
    results = find_similar_recipes(recipe, limit=12)
    return [_recipe_to_summary(r) for r in results]


@router.get("/image/{book_id}/{path:image_path}", auth=None)
def get_recipe_image(request, book_id: UUID, image_path: str):
    from django.http import Http404

    book = get_object_or_404(Book, pk=book_id)
    epub_path = book.get_epub_path()
    if not epub_path or not epub_path.exists():
        raise Http404("EPUB file not found.")
    try:
        with zipfile.ZipFile(epub_path, "r") as epub:
            image_data = epub.read(image_path)
            return HttpResponse(image_data, content_type="image/jpeg")
    except KeyError as e:
        raise Http404(f"Image '{image_path}' not found in EPUB.") from e
