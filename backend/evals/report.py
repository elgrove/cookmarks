"""Read the ledger and render per-task comparisons.

App-free: a report is just a fold over ``index.jsonl``. `leaderboard` ranks the
candidate models within each task (latest run); `task_history` shows one task's models
over time — the regression view.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from evals.config import LEDGER_PATH
from evals.models import LedgerRecord


def load_ledger(path: Path = LEDGER_PATH) -> list[LedgerRecord]:
    if not path.exists():
        return []
    return [
        LedgerRecord(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()
    ]


@dataclass
class _Agg:
    books: int
    f1: float
    composite: float
    precision: float
    recall: float
    cost_usd: float | None
    duration_s: float


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _aggregate(records: list[LedgerRecord]) -> _Agg:
    costs = [r.cost_usd for r in records if r.cost_usd is not None]
    return _Agg(
        books=len(records),
        f1=_mean([r.f1 for r in records]),
        composite=_mean([r.composite_mean for r in records]),
        precision=_mean([r.precision for r in records]),
        recall=_mean([r.recall for r in records]),
        cost_usd=sum(costs) if costs else None,
        duration_s=sum(r.duration_s for r in records),
    )


def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        widths = [max(w, len(cell)) for w, cell in zip(widths, row, strict=True)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))
    out = [line, "  ".join("-" * w for w in widths)]
    out.extend("  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)) for row in rows)
    return "\n".join(out)


def _cost(value: float | None) -> str:
    return f"${value:.4f}" if value is not None else "—"


def leaderboard(records: list[LedgerRecord]) -> str:
    if not records:
        return "No eval runs recorded yet."

    sections = []
    for task in sorted({r.task for r in records}):
        task_records = [r for r in records if r.task == task]
        latest_run = max(r.run_id for r in task_records)
        current = [r for r in task_records if r.run_id == latest_run]

        by_model: dict[str, list[LedgerRecord]] = defaultdict(list)
        for r in current:
            by_model[r.model_id].append(r)

        rows = []
        for model_id, model_records in by_model.items():
            agg = _aggregate(model_records)
            rows.append(
                (
                    agg.f1,
                    [
                        model_id,
                        str(agg.books),
                        f"{agg.f1:.3f}",
                        f"{agg.composite:.3f}",
                        f"{agg.precision:.3f}",
                        f"{agg.recall:.3f}",
                        _cost(agg.cost_usd),
                        f"{agg.duration_s:.0f}s",
                    ],
                )
            )
        rows.sort(key=lambda r: r[0], reverse=True)
        headers = ["Model", "Books", "F1", "Comp", "P", "R", "Cost", "Time"]
        sections.append(f"{task}  (run {latest_run})\n" + _table(headers, [r[1] for r in rows]))

    return "Leaderboard by task (latest run per task)\n\n" + "\n\n".join(sections)


def task_history(records: list[LedgerRecord], task: str) -> str:
    subset = [r for r in records if r.task == task]
    if not subset:
        known = sorted({r.task for r in records})
        return f"No runs for task {task!r}. Known: {known or '(none)'}"

    rows = [
        [
            r.run_id,
            r.timestamp[:19],
            r.git_sha or "—",
            r.model_id,
            r.book,
            f"{r.f1:.3f}",
            f"{r.composite_mean:.3f}",
            _cost(r.cost_usd),
        ]
        for r in sorted(subset, key=lambda r: (r.run_id, r.model_id))
    ]
    headers = ["Run", "Date", "SHA", "Model", "Book", "F1", "Comp", "Cost"]
    return f"{task} — history\n\n" + _table(headers, rows)
