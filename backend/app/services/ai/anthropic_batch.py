"""Thin Anthropic Message Batches seam (MY-187): create/get/cancel/results.

All Stage 2 provider I/O for the backfill goes through `AnthropicBatchClient`
so tests can substitute a fake, mirroring `GeminiBatchClient` in
`app/services/ai/gemini_batch.py`. Creation is idempotent via the
deterministic `batch.job_key` in the `Idempotency-Key` header, so no remote
search step is needed.
"""

import logging
from typing import Any, cast

from anthropic import Anthropic

from app.services.ai.gemini_batch import RemoteBatchJob

logger = logging.getLogger(__name__)


def _map_status(processing_status: str) -> str:
    """Map Anthropic processing_status onto the shared job-state vocabulary.

    The worker's poll loop understands the Gemini `JOB_STATE_*` names, so
    Anthropic states reuse them: in-flight maps to RUNNING, terminal maps to
    SUCCEEDED (per-item failures are recorded at ingest, as with Gemini's
    PARTIALLY_SUCCEEDED).
    """
    if processing_status == "ended":
        return "JOB_STATE_SUCCEEDED"
    return "JOB_STATE_RUNNING"


class AnthropicBatchClient:
    """Anthropic Message Batches I/O behind a fakeable seam."""

    def __init__(self, api_key: str) -> None:
        self._client = Anthropic(api_key=api_key)

    def create_batch(
        self, *, model: str, requests: list[dict[str, Any]], job_key: str
    ) -> RemoteBatchJob:
        """Create one remote batch; idempotent on `job_key`.

        `requests` are per-request dicts as built by
        `anthropic_stage2_request` (each carrying its own `params.model`).
        The `model` argument records the wave model for the run row.
        """
        _ = model
        batch = self._client.messages.batches.create(
            requests=cast(Any, requests),
            extra_headers={"Idempotency-Key": job_key},
        )
        return self._wrap(batch, display_name=job_key)

    def get_job(self, provider_batch_id: str) -> RemoteBatchJob:
        """Refresh one remote batch by ID (e.g. `msgbatch_...`)."""
        batch = self._client.messages.batches.retrieve(
            message_batch_id=provider_batch_id
        )
        return self._wrap(batch, display_name=None)

    def cancel_job(self, provider_batch_id: str) -> None:
        """Best-effort cancel of a remote batch; never raises."""
        try:
            self._client.messages.batches.cancel(message_batch_id=provider_batch_id)
        except Exception:
            logger.warning("Best-effort cancel of batch %s failed", provider_batch_id)

    def download_results(self, provider_batch_id: str) -> list[dict[str, Any]]:
        """Stream the result JSONL as decoded dicts (one per request)."""
        items: list[dict[str, Any]] = []
        for item in self._client.messages.batches.results(
            message_batch_id=provider_batch_id
        ):
            dump = item.model_dump(mode="json")
            if isinstance(dump, dict):
                items.append(dump)
        return items

    def _wrap(self, batch: object, *, display_name: str | None) -> RemoteBatchJob:
        batch_id = str(getattr(batch, "id", "") or "")
        if not batch_id:
            raise RuntimeError("Anthropic Batches API returned a batch with no id")
        processing_status = str(getattr(batch, "processing_status", "") or "")
        state = _map_status(processing_status)
        resolved_display = display_name or str(
            getattr(batch, "id", "") or ""
        )
        output_file_id = batch_id if state == "JOB_STATE_SUCCEEDED" else None
        return RemoteBatchJob(
            name=batch_id,
            display_name=resolved_display,
            state=state,
            error=None,
            output_file_id=output_file_id,
        )
