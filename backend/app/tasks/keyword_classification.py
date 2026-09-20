"""Tracked worker for classifying every pending keyword."""

import uuid

from app.db import SessionLocal
from app.models.task_run import TaskRun
from app.services.keyword_classification import (
    KeywordClassificationResult,
    classify_pending_keywords,
)
from app.tasks.celery_app import celery_app
from app.tasks.runs import complete_run, fail_run, start_run


def enqueue_classify_keywords(run_id: str) -> None:
    classify_keywords_task.delay(run_id)


def run_classification() -> KeywordClassificationResult:
    with SessionLocal() as session:
        return classify_pending_keywords(session)


@celery_app.task(name="classify_keywords")
def classify_keywords_task(run_id: str) -> dict[str, object]:
    start_run(run_id)
    try:
        result = run_classification()
    except Exception as exc:
        fail_run(run_id, exc)
        raise

    detail: dict[str, object] = {
        "pending": result.pending,
        "examined": result.examined,
        "classified_by_category": result.classified_by_category,
        "no_category": result.no_category,
        "failed_batches": result.failed_batches,
    }
    with SessionLocal() as session:
        run = session.get(TaskRun, uuid.UUID(run_id))
        if run is not None:
            run.provider_name = result.provider_name
            run.model_name = result.model_name
            session.commit()
    complete_run(run_id, detail, usage=result.usage)
    return detail
