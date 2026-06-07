from pydantic import BaseModel


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
