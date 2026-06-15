from celery import Celery

from app.config import settings

celery_app = Celery(
    "cookmarks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    # The worker imports the task modules listed here so @celery_app.task names
    # register; without it the worker starts but knows no extraction tasks.
    include=[
        "app.tasks.extraction",
        "app.tasks.book_keywords",
        "app.tasks.keyword_dedup",
        "app.tasks.calibre_sync",
    ],
)


@celery_app.task(name="ping")
def ping() -> str:
    """Smoke task; real extraction/embedding tasks are ported in a later milestone."""
    return "pong"
