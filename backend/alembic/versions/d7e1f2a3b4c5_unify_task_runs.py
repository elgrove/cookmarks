"""unify extraction_runs into a generic task_runs table

Renames extraction_runs -> task_runs, adds the task_type discriminator (existing rows
backfilled to 'extraction') and a generic detail JSON column, and makes book_id nullable
so non-extraction task runs (book-keywords, dedup, Calibre sync) can be recorded too. The
recipes.extraction_run_id foreign key follows the table rename automatically.

Revision ID: d7e1f2a3b4c5
Revises: a1b2c3d4e5f6
Create Date: 2026-06-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7e1f2a3b4c5"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TASK_TYPE = sa.Enum(
    "extraction", "book_keywords", "keyword_dedup", "calibre_sync", name="tasktype"
)


def upgrade() -> None:
    # SQLite (>=3.25) rewrites the recipes.extraction_run_id FK reference to the new
    # table name as part of the rename, so the recipe link survives untouched.
    op.rename_table("extraction_runs", "task_runs")

    # Add with a server default so existing extraction rows are backfilled in place.
    op.add_column(
        "task_runs",
        sa.Column("task_type", _TASK_TYPE, nullable=False, server_default="extraction"),
    )
    op.add_column(
        "task_runs",
        sa.Column("detail", sa.JSON(), nullable=False, server_default="{}"),
    )

    with op.batch_alter_table("task_runs", schema=None) as batch_op:
        batch_op.alter_column("book_id", existing_type=sa.Uuid(), nullable=True)
        # Drop the bootstrap defaults now existing rows are populated; the app always
        # sets task_type/detail explicitly.
        batch_op.alter_column("task_type", server_default=None)
        batch_op.alter_column("detail", server_default=None)
        batch_op.create_index(batch_op.f("ix_task_runs_task_type"), ["task_type"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("task_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_task_runs_task_type"))
        batch_op.alter_column("book_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.drop_column("detail")
        batch_op.drop_column("task_type")

    op.rename_table("task_runs", "extraction_runs")
