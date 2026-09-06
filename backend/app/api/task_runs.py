from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionDep
from app.models.enums import TaskType
from app.models.task_run import TaskRun
from app.schemas.task_run import TaskRunRead

router = APIRouter(tags=["task-runs"])


@router.get("/task-runs", response_model=list[TaskRunRead])
def list_task_runs(
    session: SessionDep,
    type: TaskType | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[TaskRunRead]:
    """Every task run, newest first — the unified admin reporting index across all task
    types (extraction, book-keywords, dedup, Calibre sync). `type` filters to one kind.
    `limit` and `offset` provide optional pagination for bounded clients. Eager-loads the
    book so extraction runs read against named books without an N+1."""
    stmt = (
        select(TaskRun)
        .options(selectinload(TaskRun.book))
        .order_by(TaskRun.created_at.desc(), TaskRun.id.desc())
    )
    if type is not None:
        stmt = stmt.where(TaskRun.task_type == type)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    runs = session.scalars(stmt).all()
    return [TaskRunRead.from_run(run) for run in runs]
