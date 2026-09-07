"""Thin Gemini Batch seam (MY-175): file upload, job create/get/list/cancel, output download.

All provider I/O for the backfill goes through `GeminiBatchClient` so tests can
substitute a fake. Only Gemini supports Batch — no methods are added to providers
that cannot support it, and the admin trigger returns 422 otherwise.
"""

import io
import logging
from dataclasses import dataclass

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# JobState values that still count as remote work in flight.
ACTIVE_STATES = frozenset(
    {
        "JOB_STATE_UNSPECIFIED",
        "JOB_STATE_QUEUED",
        "JOB_STATE_PENDING",
        "JOB_STATE_RUNNING",
        "JOB_STATE_UPDATING",
        "JOB_STATE_PAUSED",
        "JOB_STATE_CANCELLING",
    }
)
SUCCEEDED_STATES = frozenset({"JOB_STATE_SUCCEEDED", "JOB_STATE_PARTIALLY_SUCCEEDED"})


@dataclass
class RemoteBatchJob:
    """Provider-agnostic view of one remote batch job."""

    name: str
    display_name: str | None
    state: str
    error: str | None = None
    output_file_id: str | None = None


def _state_name(job: object) -> str:
    state = getattr(job, "state", None)
    name = getattr(state, "name", state)
    return str(name) if name is not None else "JOB_STATE_UNSPECIFIED"


def _job_error(job: object) -> str | None:
    error = getattr(job, "error", None)
    if error is None:
        return None
    message = getattr(error, "message", None)
    return str(message or error)[:1000]


class GeminiBatchClient:
    """File-based Gemini Batch I/O behind a fakeable seam."""

    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    def upload_jsonl(self, content: str, *, display_name: str) -> str:
        """Upload one chunk's JSONL; returns the Files API file ID (files/...)."""
        uploaded = self._client.files.upload(
            file=io.BytesIO(content.encode()),
            config=types.UploadFileConfig(display_name=display_name, mime_type="jsonl"),
        )
        if not uploaded.name:
            raise RuntimeError("Files API upload returned no file name")
        return uploaded.name

    def create_job(self, *, model: str, input_file_id: str, display_name: str) -> RemoteBatchJob:
        """Create one remote job for an uploaded input file."""
        job = self._client.batches.create(
            model=model,
            src={"file_name": input_file_id, "format": "jsonl"},
            config={"display_name": display_name},
        )
        return self._wrap(job)

    def find_by_display_name(self, display_name: str) -> list[RemoteBatchJob]:
        """List remote jobs carrying exactly this display name (reconciliation)."""
        matches = [
            self._wrap(job)
            for job in self._client.batches.list()
            if getattr(job, "display_name", None) == display_name
        ]
        return matches

    def get_job(self, name: str) -> RemoteBatchJob:
        """Refresh one remote job by resource name (batches/...)."""
        return self._wrap(self._client.batches.get(name=name))

    def cancel_job(self, name: str) -> None:
        """Best-effort cancel of a duplicate/extra remote job; never raises."""
        try:
            self._client.batches.cancel(name=name)
        except Exception:
            logger.warning("Best-effort cancel of batch %s failed", name)

    def download_lines(self, output_file_id: str) -> list[str]:
        """Download and stream the result JSONL as text lines."""
        raw = self._client.files.download(file=output_file_id)
        return raw.decode().splitlines()

    def _wrap(self, job: object) -> RemoteBatchJob:
        name = str(getattr(job, "name", "") or "")
        if not name:
            raise RuntimeError("Batch API returned a job with no resource name")
        dest = getattr(job, "dest", None)
        output_file_id = getattr(dest, "file_name", None) or None
        return RemoteBatchJob(
            name=name,
            display_name=getattr(job, "display_name", None),
            state=_state_name(job),
            error=_job_error(job),
            output_file_id=output_file_id,
        )
