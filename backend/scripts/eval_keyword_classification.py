"""Read-only label-quality evaluation using the configured classification model.

Run with ``uv run python -m scripts.eval_keyword_classification --output results.json``.
Expected labels are reviewable in evals/gold/keyword_classification/top100.json.
Every label must be accepted on every repeat; protocol validity alone does not pass.
"""

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import NotRequired, TypedDict

from sqlalchemy import text

from app.db import SessionLocal
from app.models.enums import KeywordCategory, ModelRole
from app.services.ai import AIResponseError, ResolvedTask, Usage
from app.services.ai.registry import resolve_task
from app.services.keyword_classification import KEYWORD_CLASSIFICATION_BATCH_SIZE
from app.services.prompts import KEYWORD_CLASSIFICATION_PROMPT


class GoldKeyword(TypedDict):
    name: str
    expected: str | None
    prompt_example: bool
    accepted: NotRequired[list[str | None]]
    recipe_count: NotRequired[int]


def evaluate(resolved: ResolvedTask, gold: list[GoldKeyword], repeats: int) -> dict[str, object]:
    results: list[dict[str, object]] = []
    usage = Usage()
    for repeat in range(repeats):
        candidates = list(gold)
        random.Random(repeat).shuffle(candidates)
        for offset in range(0, len(candidates), KEYWORD_CLASSIFICATION_BATCH_SIZE):
            batch = candidates[offset : offset + KEYWORD_CLASSIFICATION_BATCH_SIZE]
            names = [item["name"] for item in batch]
            try:
                response, batch_usage = resolved.provider.classify_keywords(names, resolved.model)
                usage += batch_usage
                labels = {item.name: item.category for item in response}
                if len(response) != len(names) or set(labels) != set(names):
                    raise ValueError("Response did not cover candidates exactly once")
                allowed = {category.value for category in KeywordCategory} | {None}
                if any(label not in allowed for label in labels.values()):
                    raise ValueError("Response contained an invalid category")
            except Exception as error:
                if isinstance(error, AIResponseError):
                    usage += error.usage
                results.extend(
                    {**item, "repeat": repeat + 1, "passed": False, "error": str(error)}
                    for item in batch
                )
                continue
            results.extend(
                {
                    **item,
                    "repeat": repeat + 1,
                    "actual": labels[item["name"]],
                    "passed": labels[item["name"]] in item.get("accepted", [item["expected"]]),
                }
                for item in batch
            )
    failures = [item for item in results if not item["passed"]]
    total_weight = sum(item.get("recipe_count", 1) for item in gold) * repeats
    weights = {item["name"]: item.get("recipe_count", 1) for item in gold}
    failed_weight = sum(weights[str(item["name"])] for item in failures)
    return {
        "provider": resolved.provider.name,
        "model": resolved.model,
        "prompt_sha256": hashlib.sha256(KEYWORD_CLASSIFICATION_PROMPT.encode()).hexdigest(),
        "gold_sha256": hashlib.sha256(json.dumps(gold, sort_keys=True).encode()).hexdigest(),
        "repeats": repeats,
        "checks": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "recipe_link_weighted_accuracy": (
            (total_weight - failed_weight) / total_weight if total_weight else None
        ),
        "false_assignments": sum(
            item["expected"] is None and item.get("actual") is not None and "error" not in item
            for item in failures
        ),
        "held_out_failures": sum(not item["prompt_example"] for item in failures),
        "cost_usd": str(usage.cost_usd),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "thinking_tokens": usage.thinking_tokens,
        "failures": failures,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gold",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "evals/gold/keyword_classification/top100.json",
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--model", help="Override the model on the configured provider for comparison"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    gold: list[GoldKeyword] = json.loads(args.gold.read_text())
    if not gold or len({item["name"] for item in gold}) != len(gold):
        parser.error("Gold sample must have non-empty, unique keyword names")
    with SessionLocal() as session:
        # Model resolution may seed missing provider rows. Reject any database write.
        session.execute(text("PRAGMA query_only=ON"))
        resolved = resolve_task(session, ModelRole.KEYWORD_CLASSIFICATION)
        if resolved is None:
            parser.error("No usable keyword-classification model is configured")
        if args.model:
            resolved = ResolvedTask(resolved.provider, args.model)
        report = evaluate(resolved, gold, args.repeats)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}))
    raise SystemExit(1 if report["failed"] else 0)


if __name__ == "__main__":
    main()
