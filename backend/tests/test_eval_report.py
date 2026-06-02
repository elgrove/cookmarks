"""Unit tests for the ledger reader and per-task report rendering. App-free and
deterministic."""

from pathlib import Path

from evals.models import LedgerRecord
from evals.report import leaderboard, load_ledger, task_history


def _record(task: str, model_id: str, run_id: str, book: str, f1: float) -> LedgerRecord:
    provider, _, model = model_id.partition(":")
    return LedgerRecord(
        run_id=run_id,
        timestamp=f"{run_id[:4]}-01-01T00:00:00+00:00",
        git_sha="abc1234",
        task=task,
        model_id=model_id,
        provider=provider,
        model=model,
        book=book,
        num_gold=10,
        num_predicted=10,
        num_matched=int(10 * f1),
        precision=f1,
        recall=f1,
        f1=f1,
        composite_mean=f1,
        ingredients_jaccard_mean=f1,
        instructions_jaccard_mean=f1,
        cost_usd=0.01,
        input_tokens=100,
        output_tokens=20,
        duration_s=5.0,
    )


def test_load_ledger_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "index.jsonl"
    records = [_record("one_recipe_per_file", "GEMINI:flash", "20260101T000000Z", "curry-guy", 0.9)]
    path.write_text("\n".join(r.model_dump_json() for r in records) + "\n")
    loaded = load_ledger(path)
    assert len(loaded) == 1
    assert loaded[0].task == "one_recipe_per_file" and loaded[0].f1 == 0.9


def test_leaderboard_ranks_models_within_task_latest_run() -> None:
    records = [
        _record("one_recipe_per_file", "GEMINI:flash", "20260101T000000Z", "curry-guy", 0.50),
        _record("one_recipe_per_file", "GEMINI:flash", "20260102T000000Z", "curry-guy", 0.80),
        _record("one_recipe_per_file", "OPENROUTER:oss", "20260102T000000Z", "curry-guy", 0.90),
    ]
    out = leaderboard(records)
    assert out.index("OPENROUTER:oss") < out.index("GEMINI:flash")  # 0.90 ranks above 0.80
    assert "0.500" not in out  # stale run excluded


def test_leaderboard_separates_tasks() -> None:
    records = [
        _record("many_recipes_per_file", "GEMINI:flash-lite", "20260101T000000Z", "craveable", 0.95),
        _record("blocks_of_files", "GEMINI:flash", "20260101T000000Z", "nothing-fancy", 0.88),
    ]
    out = leaderboard(records)
    assert "many_recipes_per_file" in out
    assert "blocks_of_files" in out


def test_leaderboard_empty() -> None:
    assert "No eval runs" in leaderboard([])


def test_task_history_lists_runs_chronologically() -> None:
    records = [
        _record("one_recipe_per_file", "GEMINI:flash", "20260102T000000Z", "curry-guy", 0.80),
        _record("one_recipe_per_file", "GEMINI:flash", "20260101T000000Z", "curry-guy", 0.60),
    ]
    out = task_history(records, "one_recipe_per_file")
    assert "one_recipe_per_file — history" in out
    assert out.index("20260101") < out.index("20260102")


def test_task_history_unknown() -> None:
    records = [_record("blocks_of_files", "GEMINI:flash", "20260101T000000Z", "nothing-fancy", 0.8)]
    out = task_history(records, "nope")
    assert "No runs for task 'nope'" in out
    assert "blocks_of_files" in out  # lists known tasks
