"""Anthropic Message Batches seam (MY-187).

Create carries the deterministic job key as Idempotency-Key, retrieve maps
processing_status onto the shared job states, cancel is best-effort, and
results stream as decoded dicts.
"""

from types import SimpleNamespace
from unittest.mock import Mock

from app.services.ai.anthropic_batch import AnthropicBatchClient, _map_status


def _client_with_mock() -> tuple[AnthropicBatchClient, Mock]:
    client = AnthropicBatchClient("test-key")
    batches_mock = Mock()
    client._client = Mock(messages=Mock(batches=batches_mock))
    return client, batches_mock


def test_map_status_covers_anthropic_lifecycle() -> None:
    assert _map_status("in_progress") == "JOB_STATE_RUNNING"
    assert _map_status("canceling") == "JOB_STATE_RUNNING"
    assert _map_status("ended") == "JOB_STATE_SUCCEEDED"


def test_create_batch_sends_idempotency_key() -> None:
    client, batches = _client_with_mock()
    batches.create.return_value = SimpleNamespace(id="msgbatch_123", processing_status="in_progress")
    requests = [{"custom_id": "k1", "params": {"model": "m"}}]

    job = client.create_batch(model="m", requests=requests, job_key="run:c001:stage2:a1")

    batches.create.assert_called_once()
    _, kwargs = batches.create.call_args
    assert kwargs["requests"] == requests
    assert kwargs["extra_headers"] == {"Idempotency-Key": "run:c001:stage2:a1"}
    assert job.name == "msgbatch_123"
    assert job.display_name == "run:c001:stage2:a1"
    assert job.state == "JOB_STATE_RUNNING"
    assert job.output_file_id is None


def test_get_job_maps_ended_to_succeeded_with_output() -> None:
    client, batches = _client_with_mock()
    batches.retrieve.return_value = SimpleNamespace(id="msgbatch_9", processing_status="ended")

    job = client.get_job("msgbatch_9")

    batches.retrieve.assert_called_once_with(message_batch_id="msgbatch_9")
    assert job.state == "JOB_STATE_SUCCEEDED"
    assert job.output_file_id == "msgbatch_9"


def test_cancel_job_is_best_effort() -> None:
    client, batches = _client_with_mock()
    batches.cancel.side_effect = RuntimeError("boom")

    client.cancel_job("msgbatch_1")

    batches.cancel.assert_called_once_with(message_batch_id="msgbatch_1")


def test_download_results_returns_decoded_dicts() -> None:
    client, batches = _client_with_mock()
    first = Mock()
    first.model_dump.return_value = {"custom_id": "a", "result": {"type": "succeeded"}}
    second = Mock()
    second.model_dump.return_value = {"custom_id": "b", "result": {"type": "errored"}}
    batches.results.return_value = [first, second]

    results = client.download_results("msgbatch_1")

    batches.results.assert_called_once_with(message_batch_id="msgbatch_1")
    assert results == [
        {"custom_id": "a", "result": {"type": "succeeded"}},
        {"custom_id": "b", "result": {"type": "errored"}},
    ]
