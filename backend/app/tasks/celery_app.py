import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready

from app.config import settings
from app.tasks.runs import reap_stale_runs

logger = logging.getLogger(__name__)

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
        "app.tasks.ingest",
        "app.tasks.recipe_enrichment",
    ],
)

# The vocabulary only drifts as books are ingested, and each run sweeps one candidate
# window, so a weekly beat keeps it tidy without a person remembering to press the button.
celery_app.conf.timezone = "UTC"
celery_app.conf.beat_schedule = {
    "weekly-keyword-dedup": {
        "task": "scheduled_dedup_keywords",
        "schedule": crontab(day_of_week="sun", hour=4, minute=0),
    }
}


@worker_ready.connect
def _reap_on_worker_start(**_kwargs: object) -> None:
    """A worker killed mid-job (restart, crash, OOM) leaves its runs stuck RUNNING with
    nothing left to finish them. A fresh worker is the moment those are known dead, so
    sweep them here. Best-effort: never stop the worker coming up."""
    try:
        reap_stale_runs()
    except Exception:
        logger.exception("Stale-run reaping failed at worker start")


@celery_app.task(name="ping")
def ping() -> str:
    """Smoke task; real extraction/embedding tasks are ported in a later milestone."""
    return "pong"
