import random

from django.db.models import Count
from django_q.tasks import async_task
from ninja import Router

from core.api.schemas import MessageOut, QueueAllIn, QueueCountIn, TasksOverview
from core.models import Book, Config, ExtractionReport

router = Router()


@router.get("", response=TasksOverview)
def get_tasks_overview(request):
    books_count = Book.objects.count()
    books_with_recipes_count = (
        Book.objects.annotate(recipe_count=Count("recipes")).filter(recipe_count__gt=0).count()
    )
    return {"books_count": books_count, "books_with_recipes_count": books_with_recipes_count}


@router.post("/load-books", response=MessageOut)
def queue_load_books(request):
    async_task("core.tasks.load_books_from_calibre_task")
    return {"detail": "Load books task has been queued successfully."}


@router.post("/dedupe-keywords", response=MessageOut)
def queue_dedupe_keywords(request):
    async_task("core.tasks.deduplicate_keywords_task")
    return {"detail": "Deduplicate keywords task has been queued successfully."}


def _queue_book_for_extraction(book: Book, method: str | None, group: str) -> None:
    config = Config.get_solo()
    queued = book.extraction_reports.filter(started_at__isnull=True).first()
    if queued:
        async_task("core.tasks.extract_recipes_from_book", book.id, str(queued.id), group=group)
        return
    extraction = ExtractionReport.objects.create(
        book=book,
        provider_name=config.ai_provider,
        extraction_method=method,
    )
    async_task(
        "core.tasks.extract_recipes_from_book",
        book.id,
        str(extraction.id),
        group=group,
    )


@router.post("/queue-all-extractions", response=MessageOut)
def queue_all_extractions(request, data: QueueAllIn):
    books = Book.objects.all().order_by("-calibre_id")
    count = books.count()
    for book in books:
        _queue_book_for_extraction(book, data.extraction_method, "queue_all_extractions")
    return {"detail": f"Queued {count} books for extraction."}


@router.post("/queue-random-extractions", response={200: MessageOut, 400: MessageOut})
def queue_random_extractions(request, data: QueueCountIn):
    count = max(1, min(data.count, 1000))
    all_books = list(Book.objects.annotate(recipe_count=Count("recipes")).filter(recipe_count=0))
    if not all_books:
        return 400, {"detail": "No books found to queue for extraction."}

    chosen = all_books if count >= len(all_books) else random.sample(all_books, count)
    for book in chosen:
        _queue_book_for_extraction(book, data.extraction_method, "queue_random_extractions")
    return 200, {"detail": f"Queued {len(chosen)} random books for extraction."}
