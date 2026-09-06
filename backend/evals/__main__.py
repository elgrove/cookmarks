"""Command line: ``python -m evals run`` / ``python -m evals report``."""

import argparse
import logging
import sys
from pathlib import Path

from evals import assistant, enrichment, report
from evals.config import DEFAULT_CONFIG_PATH, load_config
from evals.runner import run_eval


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evals", description="Recipe extraction eval suite.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run the extraction eval per task")
    run_p.add_argument(
        "--task",
        action="append",
        dest="tasks",
        metavar="ROLE",
        help="task role from eval.toml (repeatable; default: all)",
    )
    run_p.add_argument(
        "--model",
        action="append",
        dest="models",
        metavar="PROVIDER:MODEL",
        help="candidate model id (repeatable; default: all in each task)",
    )
    run_p.add_argument(
        "--book",
        action="append",
        dest="books",
        metavar="SLUG",
        help="book slug (repeatable; default: all for the task)",
    )
    run_p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="path to eval.toml")

    asst_p = sub.add_parser("assistant", help="run the assistant eval per prompt")
    asst_p.add_argument(
        "--model",
        action="append",
        dest="models",
        metavar="PROVIDER:MODEL",
        help="candidate model id (repeatable; default: all)",
    )
    asst_p.add_argument(
        "--prompt",
        action="append",
        dest="prompts",
        metavar="ID",
        help="prompt id from eval.toml (repeatable; default: all)",
    )
    asst_p.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_PATH, help="path to eval.toml"
    )

    enrich_p = sub.add_parser("enrichment", help="run the recipe enrichment eval against gold set")
    enrich_p.add_argument(
        "--model",
        action="append",
        dest="models",
        metavar="PROVIDER:MODEL",
        help="candidate model id (repeatable; default: all)",
    )
    enrich_p.add_argument(
        "--stage-1-model",
        metavar="PROVIDER:MODEL",
        help="ingredient-structuring model for a mixed two-stage run",
    )
    enrich_p.add_argument(
        "--stage-2-model",
        metavar="PROVIDER:MODEL",
        help="facet-and-keyword model for a mixed two-stage run",
    )
    enrich_p.add_argument(
        "--recipe",
        action="append",
        dest="recipes",
        metavar="SLUG",
        help="recipe slug (repeatable; default: all)",
    )
    enrich_p.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_PATH, help="path to eval.toml"
    )
    enrich_p.add_argument(
        "--no-description",
        action="store_true",
        help="omit recipe descriptions from Stage 2 input context",
    )
    enrich_p.add_argument(
        "--no-deterministic",
        action="store_true",
        help="send every ingredient line to the Stage 1 model",
    )

    rep_p = sub.add_parser("report", help="summarise the ledger (no run)")
    rep_p.add_argument(
        "view",
        choices=["leaderboard", "task", "assistant", "enrichment"],
        help="which view to render",
    )
    rep_p.add_argument("role", nargs="?", help="task role (required for 'task')")

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    args = _build_parser().parse_args(argv)

    if args.command == "run":
        config = load_config(args.config)
        tasks = args.tasks or [t.role for t in config.tasks]
        print(f"Running tasks: {', '.join(tasks)}\n", file=sys.stderr)
        run_eval(config, task_roles=args.tasks, model_ids=args.models, book_slugs=args.books)
        print("\n" + report.leaderboard(report.load_ledger()))
        return 0

    if args.command == "assistant":
        assistant.run_assistant_eval(args.config, args.models, args.prompts)
        print("\n" + assistant.leaderboard(assistant.load_ledger()))
        return 0

    if args.command == "enrichment":
        records = enrichment.run_enrichment_eval(
            args.config,
            args.models,
            args.recipes,
            include_description=not args.no_description,
            use_deterministic=not args.no_deterministic,
            stage1_model_id=args.stage_1_model,
            stage2_model_id=args.stage_2_model,
        )
        print("\n" + enrichment.leaderboard(records))
        return 0

    if args.command == "report":
        if args.view == "assistant":
            print(assistant.leaderboard(assistant.load_ledger()))
            return 0
        if args.view == "enrichment":
            records = []
            if enrichment.ENRICHMENT_LEDGER_PATH.exists():
                records = [
                    enrichment.EnrichmentRecipeRecord.model_validate_json(line)
                    for line in enrichment.ENRICHMENT_LEDGER_PATH.read_text().splitlines()
                    if line.strip()
                ]
            print(enrichment.leaderboard(records))
            return 0
        records = report.load_ledger()
        if args.view == "leaderboard":
            print(report.leaderboard(records))
        else:
            if not args.role:
                print("error: 'report task' needs a task role", file=sys.stderr)
                return 2
            print(report.task_history(records, args.role))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
