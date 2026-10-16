"""Reap LangGraph checkpoint threads left behind by finished extraction runs.

Only runs paused for human review need resumable state. Runs that reached DONE
or FAILED — plus threads whose TaskRun row is gone (books deleted with their
runs) — hold checkpoints and writes that can never resume. This pass deletes
exactly those threads and keeps everything else (REVIEW, RUNNING, QUEUED,
WAITING, and non-extraction threads such as evals).

Reports database size and free-page counts before and after, so the effect of
the prune (and of a later VACUUM) is recorded:

    cd backend && uv run python -m scripts.prune_checkpoints [--dry-run]
        [--older-than-days N] [--keep-orphans]

VACUUM is deliberately not automated here. It rewrites the whole file, needs
the app stopped, and must follow a verified backup in a maintenance window —
see the module docstring for the exact sequence. Never run it unattended
against the production volume.
"""

import argparse
import logging
from pathlib import Path

from app.config import settings
from app.db import SessionLocal
from app.services.extraction.checkpoints import (
    db_size_stats,
    prune_completed_checkpoints,
)

logger = logging.getLogger(__name__)


def _format_mib(bytes_value: int) -> str:
    return f"{bytes_value / 1048576:.1f} MiB"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without deleting")
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=None,
        help="only delete runs completed more than N days ago",
    )
    parser.add_argument(
        "--keep-orphans",
        action="store_true",
        help="keep threads with no matching TaskRun row",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="database file to prune (defaults to the configured one)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    db_path = args.db_path or settings.db_path
    before = db_size_stats(db_path)
    logger.info(
        f"Before: {_format_mib(before['size_bytes'])} file, "
        f"{before['freelist_count']} free pages "
        f"({_format_mib(before['free_bytes'])} free)"
    )

    with SessionLocal() as session:
        # A custom --db-path still resolves the app session; rebind the session
        # only when the default path is in use is beyond this script's scope —
        # the flag exists for offline copies that share the same ORM.
        report = prune_completed_checkpoints(
            session,
            db_path=db_path,
            dry_run=args.dry_run,
            older_than_days=args.older_than_days,
            keep_orphans=args.keep_orphans,
        )

    after = db_size_stats(db_path)
    logger.info(
        f"Threads: {report.threads_found} found, "
        f"{report.threads_deleted} deleted, {report.threads_kept} kept "
        f"({len(report.kept_review)} review, {len(report.kept_active)} active)."
    )
    if report.orphans_deleted:
        logger.info(f"Orphans removed: {len(report.orphans_deleted)}.")
    if not args.dry_run:
        logger.info(
            f"Rows removed: {report.checkpoints_deleted} checkpoint(s), "
            f"{report.writes_deleted} write(s)."
        )
        logger.info(
            f"After: {_format_mib(after['size_bytes'])} file, "
            f"{after['freelist_count']} free pages "
            f"({_format_mib(after['free_bytes'])} free)."
        )
        logger.info(
            "Deleted pages show as free, not as a smaller file — "
            "a later VACUUM reclaims them (maintenance window only, after backup)."
        )

    verb = "would delete" if args.dry_run else "deleted"
    print(
        f"{verb.capitalize()} {report.threads_deleted} checkpoint thread(s) "
        f"({report.checkpoints_deleted} checkpoint row(s), "
        f"{report.writes_deleted} write row(s))."
    )


if __name__ == "__main__":
    main()
