"""Command line: ``python -m evals run`` / ``python -m evals report``."""

import argparse
import logging
import sys
from pathlib import Path

from evals import report
from evals.config import DEFAULT_CONFIG_PATH, load_config
from evals.runner import run_eval


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evals", description="Recipe extraction eval suite.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run the extraction eval per task")
    run_p.add_argument("--task", action="append", dest="tasks", metavar="ROLE",
                       help="task role from eval.toml (repeatable; default: all)")
    run_p.add_argument("--model", action="append", dest="models", metavar="PROVIDER:MODEL",
                       help="candidate model id (repeatable; default: all in each task)")
    run_p.add_argument("--book", action="append", dest="books", metavar="SLUG",
                       help="book slug (repeatable; default: all for the task)")
    run_p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH,
                       help="path to eval.toml")

    rep_p = sub.add_parser("report", help="summarise the ledger (no run)")
    rep_p.add_argument("view", choices=["leaderboard", "task"], help="which view to render")
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

    if args.command == "report":
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
