import logging
from datetime import timedelta
from uuid import UUID

from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from ninja import Router

from core.api.schemas import (
    ExtractionReportsBundle,
    MessageOut,
    ResumeExtractionIn,
)
from core.models import Book, Config, ExtractionReport, Recipe
from core.services.extraction import app as extraction_app
from core.tasks import save_recipes_from_graph_state

logger = logging.getLogger(__name__)

router = Router()


def _report_to_out(report: ExtractionReport) -> dict:
    return {
        "id": report.id,
        "book_id": report.book_id,
        "book_title": report.book.title,
        "book_clean_title": report.book.clean_title,
        "book_author": report.book.author,
        "provider_name": report.provider_name,
        "model_name": report.model_name,
        "queued_at": report.queued_at,
        "started_at": report.started_at,
        "completed_at": report.completed_at,
        "total_chapters": report.total_chapters,
        "chapters_processed_count": len(report.chapters_processed or []),
        "extraction_method": report.extraction_method,
        "images_in_separate_chapters": report.images_in_separate_chapters,
        "images_can_be_matched": report.images_can_be_matched,
        "recipes_found": report.recipes_found,
        "cost_usd": report.cost_usd,
        "input_tokens": report.input_tokens,
        "output_tokens": report.output_tokens,
        "status": report.status,
        "image_count": getattr(report, "image_count", 0) or 0,
    }


@router.get("", response=ExtractionReportsBundle)
def list_reports(request):
    fourteen_days_ago = now() - timedelta(days=14)

    reports = (
        ExtractionReport.objects.select_related("book")
        .filter(created_at__gte=fourteen_days_ago)
        .annotate(
            image_count=Count(
                "book__recipes",
                filter=Q(book__recipes__image__isnull=False) & ~Q(book__recipes__image=""),
            )
        )
        .order_by("-completed_at")[:100]
    )

    total_cost = (
        ExtractionReport.objects.filter(
            created_at__gte=fourteen_days_ago, cost_usd__isnull=False
        ).aggregate(Sum("cost_usd"))["cost_usd__sum"]
        or 0
    )

    total_books = Book.objects.count()
    total_recipes = Recipe.objects.count()
    processed_books = (
        Book.objects.annotate(recipe_count=Count("recipes")).filter(recipe_count__gt=0).count()
    )
    config = Config.get_solo()

    return {
        "reports": [_report_to_out(r) for r in reports],
        "total_books": total_books,
        "total_recipes": total_recipes,
        "processed_books": processed_books,
        "total_cost": round(float(total_cost), 2),
        "provider_configured": bool(config.ai_provider and config.api_key),
    }


@router.post("/{report_id}/resume", response={200: MessageOut, 400: MessageOut, 500: MessageOut})
def resume(request, report_id: UUID, data: ResumeExtractionIn):
    report = get_object_or_404(ExtractionReport, id=report_id)

    if report.status != "review":
        return 400, {"detail": "This extraction is not awaiting review."}

    try:
        graph_config = {"configurable": {"thread_id": report.thread_id}}
        extraction_app.update_state(
            graph_config, {"human_response": data.response}, as_node="await_human"
        )
        result = extraction_app.invoke(input=None, config=graph_config)
        report.refresh_from_db()

        if report.status == "done":
            book = Book.objects.get(id=report.book_id)
            raw_recipes = result.get("raw_recipes", [])
            created = save_recipes_from_graph_state(book, report, raw_recipes)
            return 200, {"detail": f"Extraction resumed and completed. Saved {created} recipes."}

        return 200, {"detail": f"Extraction resumed with status: {report.status}"}
    except Exception as e:
        logger.error(f"Error resuming extraction: {e}")
        return 500, {"detail": f"Error resuming extraction: {e}"}
