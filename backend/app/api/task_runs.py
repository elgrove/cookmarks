from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionDep
from app.models.enums import TaskType
from app.models.task_run import TaskRun
from app.schemas.task_run import TaskRunRead

router = APIRouter(tags=["task-runs"])


@router.get("/task-runs", response_model=list[TaskRunRead])
def list_task_runs(session: SessionDep, type: TaskType | None = None) -> list[TaskRunRead]:
    """Every task run, newest first — the unified admin reporting index across all task
    types (extraction, book-keywords, dedup, Calibre sync). `type` filters to one kind.
    Eager-loads the book so extraction runs read against named books without an N+1."""
    stmt = select(TaskRun).options(selectinload(TaskRun.book)).order_by(TaskRun.created_at.desc())
    if type is not None:
        stmt = stmt.where(TaskRun.task_type == type)
    runs = session.scalars(stmt).all()
    return [TaskRunRead.from_run(run) for run in runs]
