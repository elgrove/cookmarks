from celery import Celery

from app.config import settings

celery_app = Celery(
    "cookmarks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)


@celery_app.task(name="ping")
def ping() -> str:
    """Smoke task; real extraction/embedding tasks are ported in a later milestone."""
    return "pong"
