import uuid

from pydantic import BaseModel, Field


class BookKeywordTaskRequest(BaseModel):
    """Options for the on-demand book-keyword task. By default only books missing
    keywords are tagged; `regenerate` re-tags every extracted book."""

    regenerate: bool = False


class TaskRunAck(BaseModel):
    """Acknowledgement of a queued maintenance task: which task, that it's queued, and
    how many units of work (here, books) it will process. Fire-and-forget — there's no
    live progress, mirroring extraction."""

    task: str
    status: str
    queued: int


class EnrichmentBackfillRequest(BaseModel):
    """Launch the Gemini Batch backfill. Requires the ID of a done MY-174 live
    pilot run, an explicit confirmation its output was reviewed, and matching
    contract versions — all checked before anything is queued."""

    pilot_run_id: uuid.UUID
    confirm_pilot_reviewed: bool = False
    max_active_jobs: int = Field(default=4, ge=1, le=10)


class EnrichmentBackfillResumeRequest(BaseModel):
    """Resume after a terminal run: a fresh parent run selects only recipes not
    yet current, so repeated resumes never redo applied work. Resuming a
    previous backfill needs no new approval; a first-ever launch through this
    endpoint requires the same reviewed pilot approval as the trigger."""

    max_active_jobs: int = Field(default=4, ge=1, le=10)
    pilot_run_id: uuid.UUID | None = None
    confirm_pilot_reviewed: bool = False
