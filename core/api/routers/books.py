import random
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import Case, Count, Value, When
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django_q.tasks import async_task
from ninja import Query, Router

from core.api.schemas import (
    BookDetailOut,
    ExtractIn,
    MessageOut,
    PaginatedBooks,
)
from core.models import Book, Config, ExtractionReport
from core.services.ai import GeminiProvider, OpenRouterProvider

router = Router()


def _book_to_out(book: Book, recipe_count: int | None = None) -> dict:
    return {
        "id": book.id,
        "calibre_id": book.calibre_id,
        "title": book.title,
        "clean_title": book.clean_title,
        "author": book.author,
        "pubdate": book.pubdate,
        "isbn": book.isbn or "",
        "description": book.description or "",
        "recipe_count": (
            recipe_count if recipe_count is not None else getattr(book, "recipe_count", 0)
        ),
    }


def _available_models_for(provider_name: str) -> list[str]:
    provider_map = {"OPENROUTER": OpenRouterProvider, "GEMINI": GeminiProvider}
    provider_class = provider_map.get(provider_name)
    if not provider_class:
        return []
    attrs = [
        "IMAGE_MATCH_MODEL",
        "EXTRACT_MANY_PER_FILE_MODEL",
        "EXTRACT_ONE_PER_FILE_MODEL",
        "EXTRACT_BLOCKS_MODEL",
        "DEDUPLICATE_MODEL",
    ]
    models = set()
    for attr in attrs:
        model = getattr(provider_class, attr, None)
        if model and model != NotImplemented:
            models.add(model)
    return sorted(models)


@router.get("", response=PaginatedBooks)
def list_books(
    request,
    search: str = "",
    selected_authors: list[str] = Query(default_factory=list),
    has_recipes: bool = False,
    sort: str = "random",
    page: int = 1,
    page_size: int = 60,
):
    qs = Book.objects.annotate(recipe_count=Count("recipes"))

    if search:
        qs = qs.filter(title__icontains=search) | qs.filter(author__icontains=search)

    if selected_authors:
        qs = qs.filter(author__in=selected_authors)

    if has_recipes:
        qs = qs.filter(recipe_count__gte=1)

    if sort == "title":
        qs = qs.order_by("title")
    elif sort == "author":
        qs = qs.order_by("author", "title")
    elif sort == "recipes":
        qs = qs.order_by("-recipe_count", "title")
    elif sort == "recent":
        qs = qs.order_by("-calibre_added_at", "title")
    elif sort == "random":
        has_recipes_order = Case(
            When(recipe_count__gte=1, then=Value(0)),
            default=Value(1),
        )
        qs = qs.order_by(has_recipes_order, "?")
    else:
        qs = qs.order_by("-calibre_added_at", "title")

    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page)

    return {
        "items": [_book_to_out(b) for b in page_obj.object_list],
        "page": page_obj.number,
        "pages": paginator.num_pages,
        "total": paginator.count,
        "page_size": page_size,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }


@router.get("/authors", response=list[str])
def list_authors(request):
    return list(Book.objects.values_list("author", flat=True).distinct().order_by("author"))


@router.get("/{book_id}", response=BookDetailOut)
def get_book(request, book_id: UUID):
    book = get_object_or_404(Book.objects.annotate(recipe_count=Count("recipes")), id=book_id)

    recipe_ids = list(book.recipes.values_list("id", flat=True))
    if len(recipe_ids) > 6:
        sample_ids = random.sample(recipe_ids, 6)
    else:
        sample_ids = recipe_ids

    first_recipe = book.recipes.order_by("order").first()

    config = Config.get_solo()
    available_models = _available_models_for(config.ai_provider) if config.ai_provider else []

    data = _book_to_out(book)
    data.update(
        {
            "available_models": available_models,
            "sample_recipe_ids": sample_ids,
            "first_recipe_id": first_recipe.id if first_recipe else None,
        }
    )
    return data


@router.get("/{book_id}/cover", auth=None)
def get_book_cover(request, book_id: UUID):
    # Cover served without auth for <img> tag convenience; still gated by app
    # network access. If you want auth on covers, drop the auth=None.
    book = get_object_or_404(Book, id=book_id)
    cover_path = book.get_cover_image_path()
    if not cover_path.exists():
        raise Http404("Cover image not found")
    return FileResponse(open(cover_path, "rb"), content_type="image/jpeg")


@router.delete("/{book_id}", response=MessageOut)
def delete_book(request, book_id: UUID):
    book = get_object_or_404(Book, id=book_id)
    title = book.clean_title
    book.delete()
    return {"detail": f'Deleted "{title}" and all associated recipes.'}


@router.post("/{book_id}/extract", response=MessageOut)
def queue_extract(request, book_id: UUID, data: ExtractIn):
    book = get_object_or_404(Book, id=book_id)
    config = Config.get_solo()

    existing = book.extraction_reports.filter(started_at__isnull=True).exists()
    if not existing:
        extraction = ExtractionReport.objects.create(
            book=book,
            provider_name=config.ai_provider,
            extraction_method=data.extraction_method,
            model_name=data.model_name,
        )
        async_task("core.tasks.extract_recipes_from_book", book.id, str(extraction.id))
    else:
        async_task("core.tasks.extract_recipes_from_book", book.id)

    return {"detail": f"Queued recipe extraction for {book.title}"}


@router.post("/{book_id}/clear-images", response=MessageOut)
def clear_images(request, book_id: UUID):
    book = get_object_or_404(Book, id=book_id)
    updated_count = book.recipes.update(image="")
    plural = "s" if updated_count != 1 else ""
    return {"detail": f"Removed images from {updated_count} recipe{plural}."}


@router.post("/{book_id}/clear-recipes", response=MessageOut)
def clear_recipes(request, book_id: UUID):
    book = get_object_or_404(Book, id=book_id)
    deleted_count, _ = book.recipes.all().delete()
    plural = "s" if deleted_count != 1 else ""
    return {"detail": f"Removed {deleted_count} recipe{plural} from this book."}


@router.post("/{book_id}/generate-embeddings", response={200: MessageOut, 400: MessageOut})
def generate_embeddings(request, book_id: UUID):
    book = get_object_or_404(Book, id=book_id)
    recipe_count = book.recipes.count()
    if recipe_count == 0:
        return 400, {"detail": "No recipes to generate embeddings for."}
    async_task("core.tasks.generate_book_embeddings_task", book.id)
    return 200, {
        "detail": (
            f"Queued embedding generation for {recipe_count} recipes from {book.clean_title}"
        )
    }
